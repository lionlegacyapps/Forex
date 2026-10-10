"""Read-only paper-session eligibility check (no execution / no activation)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.broker_account import BrokerAccount
from app.models.enums import TradingMode
from app.qualification.repository import QualificationRepository
from app.qualification.states import ApprovalScope, QualificationState, is_approved


class EligibilityCheckResult(BaseModel):
    eligible: bool
    reasons: list[str] = Field(default_factory=list)
    qualification_id: uuid.UUID | None = None
    qualification_state: str | None = None
    approval_scope: str | None = None
    expires_at: datetime | None = None
    account_is_enabled: bool | None = None
    # Explicit non-activation contract
    account_enabled_by_check: bool = False
    orders_authorized_by_check: bool = False
    live_trading_authorized: bool = False


class PaperEligibilityService:
    """Future paper-session runner calls this — it never places orders."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = QualificationRepository(session)

    def check(
        self,
        *,
        engine_strategy_id: str,
        strategy_version: str,
        parameter_hash: str,
        evidence_fingerprint: str,
        broker_account_id: uuid.UUID,
        now: datetime | None = None,
    ) -> EligibilityCheckResult:
        now = now or datetime.now(UTC)
        reasons: list[str] = []
        row = self.repo.find_by_evidence_binding(
            engine_strategy_id=engine_strategy_id,
            strategy_version=strategy_version,
            parameter_hash=parameter_hash,
            evidence_fingerprint=evidence_fingerprint,
        )
        if row is None:
            return EligibilityCheckResult(
                eligible=False,
                reasons=["no_qualification_record"],
            )

        if not is_approved(row.qualification_state):
            reasons.append(f"state_not_approved:{row.qualification_state.value}")

        if row.approval_scope != ApprovalScope.PAPER_ONLY:
            reasons.append("approval_scope_not_paper_only")

        if row.strategy_version != strategy_version:
            reasons.append("strategy_version_mismatch")
        if row.parameter_hash != parameter_hash:
            reasons.append("parameter_hash_mismatch")
        if row.evidence_fingerprint != evidence_fingerprint:
            reasons.append("evidence_fingerprint_mismatch")
        if row.engine_strategy_id != engine_strategy_id:
            reasons.append("strategy_id_mismatch")

        if row.expires_at is not None and now >= row.expires_at:
            reasons.append("approval_expired")

        account_enabled: bool | None = None
        account = self.session.get(BrokerAccount, broker_account_id)
        if account is None:
            reasons.append("broker_account_not_found")
        else:
            account_enabled = bool(account.is_enabled)
            if account.trading_mode != TradingMode.PAPER:
                reasons.append("live_account_rejected")
            # Never flip is_enabled; surface status for the future runner.
            if not account.is_enabled:
                reasons.append("account_not_enabled")

        # Qualification eligibility requires paper mode + valid approval.
        # Account enablement remains a separate operator action (not auto-flipped).
        blocking = [
            r
            for r in reasons
            if r
            not in {
                "account_not_enabled",
            }
        ]
        eligible = (
            len(blocking) == 0
            and row.qualification_state == QualificationState.APPROVED_FOR_PAPER
        )

        return EligibilityCheckResult(
            eligible=eligible,
            reasons=reasons,
            qualification_id=row.id,
            qualification_state=row.qualification_state.value,
            approval_scope=row.approval_scope.value,
            expires_at=row.expires_at,
            account_is_enabled=account_enabled,
            account_enabled_by_check=False,
            orders_authorized_by_check=False,
            live_trading_authorized=False,
        )
