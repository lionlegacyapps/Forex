"""Repeatable paper-pilot onboarding workflow — fail closed, no auto-approval."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.market_data.models import Bar
from app.models.enums import QualificationState as QS
from app.models.strategy_paper_qualification import StrategyPaperQualification
from app.onboarding.account import (
    PaperAccountRegistrationResult,
    verify_and_register_alpaca_paper_account,
)
from app.onboarding.errors import OnboardingBlockedError
from app.onboarding.market_data_check import (
    MarketDataAccessResult,
    verify_alpaca_market_data_access,
)
from app.onboarding.owner import (
    OWNER_ALLOWLIST_SETUP_PROCEDURE,
    OwnerAllowlistStatus,
    owner_allowlist_status,
    require_authenticated_owner,
)
from app.onboarding.qualification_evidence import (
    QualificationEvidenceBundle,
    prepare_sma_crossover_qualification,
)
from app.qualification.auth import AuthenticatedOwner

logger = logging.getLogger(__name__)


class OnboardingStepResult(BaseModel):
    step: str
    ok: bool
    detail: str = ""
    blocked: bool = False


class OnboardingWorkflowReport(BaseModel):
    ok: bool
    blocked: bool
    generated_at: datetime
    steps: list[OnboardingStepResult] = Field(default_factory=list)
    owner_allowlist: dict[str, Any] = Field(default_factory=dict)
    account: dict[str, Any] | None = None
    qualification: dict[str, Any] | None = None
    market_data_feed: str | None = None
    market_data: dict[str, Any] | None = None
    preflight_ok: bool | None = None
    dry_run_decision: str | None = None
    manual_approval_status: str = "PENDING"
    owner_actions_required: list[str] = Field(default_factory=list)
    real_orders_created: int = 0
    notes: list[str] = Field(default_factory=list)


class PaperPilotOnboardingWorkflow:
    """Orchestrates safe onboarding steps without enabling execution."""

    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self._orders_created = 0

    def check_owner_allowlist(self) -> tuple[OwnerAllowlistStatus, OnboardingStepResult]:
        status = owner_allowlist_status(self.settings)
        if not status.configured:
            return status, OnboardingStepResult(
                step="verify_authenticated_owner",
                ok=False,
                blocked=True,
                detail="PAPER_QUALIFICATION_OWNER_SUBJECTS empty",
            )
        return status, OnboardingStepResult(
            step="verify_authenticated_owner",
            ok=True,
            detail=f"allowlist_subjects={status.subject_count}",
        )

    def authenticate_owner(
        self, *, subject: str | None, credential_verified: bool
    ) -> AuthenticatedOwner:
        return require_authenticated_owner(
            subject=subject,
            credential_verified=credential_verified,
            settings=self.settings,
        )

    async def register_paper_account(
        self,
        *,
        owner: AuthenticatedOwner,
        enable_account: bool = False,
    ) -> PaperAccountRegistrationResult:
        if self.settings.paper_session_execute_enabled:
            raise OnboardingBlockedError(
                "Refuse onboarding registration while PAPER_SESSION_EXECUTE_ENABLED=true "
                "during remediation; disable execution first",
                code="execute_enabled_during_onboarding",
            )
        return await verify_and_register_alpaca_paper_account(
            self.db,
            owner=owner,
            settings=self.settings,
            enable_account=enable_account,
        )

    async def verify_market_data(self) -> MarketDataAccessResult:
        return await verify_alpaca_market_data_access(settings=self.settings)

    async def prepare_qualification(
        self,
        *,
        bars: list[Bar] | None = None,
    ) -> QualificationEvidenceBundle:
        return await prepare_sma_crossover_qualification(
            self.db, settings=self.settings, bars=bars
        )

    async def run(
        self,
        *,
        owner_subject: str | None,
        credential_verified: bool,
        enable_account: bool = False,
        skip_live_market_data: bool = False,
        evaluation_bars: list[Bar] | None = None,
        now: datetime | None = None,
    ) -> OnboardingWorkflowReport:
        """Execute steps 1–8; steps 9–10 remain blocked until manual approval.

        Never auto-approves qualification. Never submits orders.
        Never enables PAPER_SESSION_EXECUTE_ENABLED.
        """
        now = now or datetime.now(UTC)
        steps: list[OnboardingStepResult] = []
        actions: list[str] = []
        notes: list[str] = [
            "PAPER_SESSION_EXECUTE_ENABLED must remain false",
            "Manual qualification approval is required before paper execute",
            "Onboarding never auto-approves and never submits orders",
            OWNER_ALLOWLIST_SETUP_PROCEDURE.splitlines()[0],
        ]
        report = OnboardingWorkflowReport(
            ok=False,
            blocked=False,
            generated_at=now,
            market_data_feed=self.settings.alpaca_data_feed,
            real_orders_created=0,
        )

        # 1–2 Owner
        allow_status, step = self.check_owner_allowlist()
        steps.append(step)
        report.owner_allowlist = {
            "configured": allow_status.configured,
            "subject_count": allow_status.subject_count,
        }
        owner: AuthenticatedOwner | None = None
        if not allow_status.configured:
            actions.append(
                "Set PAPER_QUALIFICATION_OWNER_SUBJECTS in private .env to the "
                "exact server-resolved authenticated subject (e.g. verified email), "
                "then restart. Do not invent a subject; do not disable checks."
            )
            report.steps = steps
            report.blocked = True
            report.owner_actions_required = actions
            report.notes = notes
            return report

        try:
            owner = self.authenticate_owner(
                subject=owner_subject, credential_verified=credential_verified
            )
            steps.append(
                OnboardingStepResult(
                    step="configure_owner_allowlist",
                    ok=True,
                    detail="owner authenticated against allowlist",
                )
            )
        except Exception as exc:  # noqa: BLE001
            steps.append(
                OnboardingStepResult(
                    step="configure_owner_allowlist",
                    ok=False,
                    blocked=True,
                    detail=str(exc),
                )
            )
            actions.append(
                "Authenticate with a subject present in PAPER_QUALIFICATION_OWNER_SUBJECTS "
                "and credential_verified=True."
            )
            report.steps = steps
            report.blocked = True
            report.owner_actions_required = actions
            report.notes = notes
            return report

        # 3–4 Paper account
        try:
            acct = await self.register_paper_account(
                owner=owner, enable_account=enable_account
            )
            steps.append(
                OnboardingStepResult(
                    step="verify_and_register_alpaca_paper_account",
                    ok=True,
                    detail=(
                        f"masked={acct.external_account_id_masked} "
                        f"enabled={acct.is_enabled} new={acct.created_new}"
                    ),
                )
            )
            report.account = {
                "account_id": acct.account_id,
                "external_account_id_masked": acct.external_account_id_masked,
                "is_enabled": acct.is_enabled,
                "trading_mode": acct.trading_mode,
            }
            if not acct.is_enabled:
                actions.append(
                    "Explicitly enable the paper BrokerAccount (is_enabled=true) "
                    "when ready — connecting alone does not authorize trading."
                )
        except Exception as exc:  # noqa: BLE001
            steps.append(
                OnboardingStepResult(
                    step="verify_and_register_alpaca_paper_account",
                    ok=False,
                    blocked=True,
                    detail=str(exc),
                )
            )
            actions.append(f"Resolve Alpaca paper registration: {exc}")
            report.steps = steps
            report.blocked = True
            report.owner_actions_required = actions
            report.notes = notes
            return report

        # 5 Market-data access
        if skip_live_market_data:
            steps.append(
                OnboardingStepResult(
                    step="verify_market_data_access",
                    ok=True,
                    detail=f"skipped_live check; configured_feed={self.settings.alpaca_data_feed}",
                )
            )
            report.market_data = {"skipped": True, "feed": self.settings.alpaca_data_feed}
        else:
            try:
                md = await self.verify_market_data()
                steps.append(
                    OnboardingStepResult(
                        step="verify_market_data_access",
                        ok=True,
                        detail=md.detail,
                    )
                )
                report.market_data = {
                    "feed": md.feed,
                    "host": md.host,
                    "bars_returned": md.bars_returned,
                    "latest_bar_timestamp": (
                        md.latest_bar_timestamp.isoformat()
                        if md.latest_bar_timestamp
                        else None
                    ),
                }
            except Exception as exc:  # noqa: BLE001
                steps.append(
                    OnboardingStepResult(
                        step="verify_market_data_access",
                        ok=False,
                        blocked=True,
                        detail=str(exc),
                    )
                )
                actions.append(
                    f"Resolve market-data access (feed={self.settings.alpaca_data_feed}): {exc}"
                )
                report.steps = steps
                report.blocked = True
                report.owner_actions_required = actions
                report.notes = notes
                return report

        # 6–7 Qualification evidence (no approve)
        try:
            bundle = await self.prepare_qualification(bars=evaluation_bars)
            eligible = bool(
                bundle.report_summary.get("eligible_for_manual_approval")
            )
            steps.append(
                OnboardingStepResult(
                    step="generate_qualification_evidence",
                    ok=True,
                    detail=(
                        f"state={bundle.qualification_state} "
                        f"recommendation={bundle.recommendation} "
                        f"oos_trades={bundle.oos_trade_count} "
                        f"blockers={bundle.hard_blockers}"
                    ),
                )
            )
            report.qualification = {
                "qualification_id": str(bundle.qualification_id),
                "strategy_id": bundle.strategy_id,
                "strategy_version": bundle.strategy_version,
                "parameter_hash": bundle.parameter_hash,
                "evidence_fingerprint": bundle.evidence_fingerprint,
                "state": bundle.qualification_state,
                "recommendation": bundle.recommendation,
                "hard_blockers": bundle.hard_blockers,
                "warnings": bundle.warnings,
                "oos_trade_count": bundle.oos_trade_count,
                "oos_windows": bundle.oos_windows,
                "auto_approved": bundle.auto_approved,
            }
            steps.append(
                OnboardingStepResult(
                    step="present_qualification_findings",
                    ok=True,
                    detail="report persisted; approval NOT performed",
                )
            )
            report.manual_approval_status = "PENDING"
            actions.append(
                "Review qualification findings and call "
                "PaperQualificationService.approve(...) only after explicit owner decision. "
                f"qualification_id={bundle.qualification_id}"
            )
            if not eligible:
                actions.append(
                    "Qualification is not eligible_for_review yet — address hard blockers "
                    "before approval (e.g. insufficient OOS trades)."
                )
        except Exception as exc:  # noqa: BLE001
            steps.append(
                OnboardingStepResult(
                    step="generate_qualification_evidence",
                    ok=False,
                    blocked=True,
                    detail=str(exc),
                )
            )
            actions.append(f"Resolve evaluation/qualification evidence: {exc}")
            report.steps = steps
            report.blocked = True
            report.owner_actions_required = actions
            report.notes = notes
            return report

        # 8 Manual approval — never automated
        steps.append(
            OnboardingStepResult(
                step="obtain_explicit_manual_qualification_approval",
                ok=False,
                blocked=False,
                detail="PENDING owner approval — not automated",
            )
        )

        # 9–10 Fail closed until APPROVED_FOR_PAPER
        qual_row = (
            self.db.get(StrategyPaperQualification, bundle.qualification_id)
            if bundle.qualification_id
            else None
        )
        approved = (
            qual_row is not None
            and qual_row.qualification_state == QS.APPROVED_FOR_PAPER
        )
        if not approved:
            steps.append(
                OnboardingStepResult(
                    step="run_read_only_pilot_preflight",
                    ok=False,
                    blocked=True,
                    detail="blocked until manual qualification approval",
                )
            )
            steps.append(
                OnboardingStepResult(
                    step="run_one_dry_run_session",
                    ok=False,
                    blocked=True,
                    detail="blocked until manual qualification approval",
                )
            )
            report.steps = steps
            report.blocked = True
            report.owner_actions_required = actions
            report.notes = notes
            report.ok = False
            report.preflight_ok = False
            report.dry_run_decision = None
            assert report.real_orders_created == 0
            assert self._orders_created == 0
            return report

        # Approved path reserved for a future operator-driven call after approve().
        steps.append(
            OnboardingStepResult(
                step="run_read_only_pilot_preflight",
                ok=False,
                blocked=True,
                detail=(
                    "qualification approved in DB, but onboarding workflow does not "
                    "auto-run preflight — invoke PilotPreflightService separately"
                ),
            )
        )
        steps.append(
            OnboardingStepResult(
                step="run_one_dry_run_session",
                ok=False,
                blocked=True,
                detail=(
                    "invoke ControlledDryRunPilot separately after preflight PASS; "
                    "keep PAPER_SESSION_EXECUTE_ENABLED=false"
                ),
            )
        )
        report.steps = steps
        report.owner_actions_required = actions
        report.notes = notes
        report.ok = False
        report.blocked = True
        report.manual_approval_status = "APPROVED"
        assert self._orders_created == 0
        report.real_orders_created = 0
        return report
