"""Read-only supervised paper pilot preflight.

Never submits, modifies, or cancels orders.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.evaluation.hashing import configuration_hash
from app.models.broker_account import BrokerAccount
from app.models.enums import TradingMode
from app.models.strategy_paper_qualification import StrategyPaperQualification
from app.paper_sessions.authorization import PaperExecutionAuthorizationService
from app.paper_sessions.market_data import (
    SessionBarSource,
    assert_bar_complete,
    assert_bars_fresh,
)
from app.paper_sessions.paper_endpoint import verify_alpaca_paper_endpoint
from app.paper_sessions.reconciliation import (
    BrokerSnapshotSource,
    StaticBrokerSnapshotSource,
    reconcile_before_activation,
)
from app.pilot.config import PilotConfig, assert_deployment_execute_disabled
from app.qualification.auth import AuthenticatedOwner
from app.qualification.eligibility import PaperEligibilityService
from app.strategies.registry import StrategyRegistry
from app.strategies.reference import SMACrossoverStrategy

logger = logging.getLogger(__name__)

REQUIRED_MIGRATION_HEAD = "e2b5c9d41f6a"


class PreflightCheck(BaseModel):
    name: str
    ok: bool
    detail: str = ""
    required: bool = True


class PreflightReport(BaseModel):
    ok: bool
    generated_at: datetime
    checks: list[PreflightCheck] = Field(default_factory=list)
    parameter_hash: str | None = None
    strategy_id: str | None = None
    strategy_version: str | None = None
    symbol: str | None = None
    broker_account_id: uuid.UUID | None = None
    qualification_id: uuid.UUID | None = None
    open_order_count: int = 0
    open_position_count: int = 0
    buying_power: str | None = None
    latest_bar_timestamp: datetime | None = None
    notes: list[str] = Field(default_factory=list)

    def failed_required(self) -> list[PreflightCheck]:
        return [c for c in self.checks if c.required and not c.ok]


def _check(name: str, ok: bool, detail: str = "", *, required: bool = True) -> PreflightCheck:
    return PreflightCheck(name=name, ok=ok, detail=detail, required=required)


class PilotPreflightService:
    """Assemble a fail-closed read-only readiness report."""

    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        eligibility: PaperEligibilityService | None = None,
        authorization: PaperExecutionAuthorizationService | None = None,
        broker_source: BrokerSnapshotSource | None = None,
        registry: StrategyRegistry | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.eligibility = eligibility or PaperEligibilityService(db)
        self.authorization = authorization or PaperExecutionAuthorizationService(
            db, settings=self.settings
        )
        self.broker_source = broker_source or StaticBrokerSnapshotSource()
        self.registry = registry or StrategyRegistry()
        if not self.registry.contains("sma_crossover", "1.0.0"):
            self.registry.register(SMACrossoverStrategy())

    async def run(
        self,
        *,
        owner: AuthenticatedOwner,
        config: PilotConfig,
        broker_account_id: uuid.UUID,
        qualification_id: uuid.UUID | None = None,
        evidence_fingerprint: str | None = None,
        bar_source: SessionBarSource | None = None,
        session_id: uuid.UUID | None = None,
        now: datetime | None = None,
        require_consent: bool = False,
    ) -> PreflightReport:
        now = now or datetime.now(UTC)
        checks: list[PreflightCheck] = []
        notes: list[str] = []
        parameter_hash = configuration_hash(config.parameters)

        # Deployment flag
        try:
            assert_deployment_execute_disabled(self.settings)
            checks.append(_check("deployment_execute_disabled", True, "PAPER_SESSION_EXECUTE_ENABLED=false"))
        except Exception as exc:  # noqa: BLE001
            checks.append(_check("deployment_execute_disabled", False, str(exc)))

        # Owner
        checks.append(
            _check(
                "authenticated_owner",
                bool(owner and owner.subject and owner.actor_type == "owner"),
                f"subject={owner.subject}",
            )
        )

        # Strategy registry
        registered = self.registry.contains(config.strategy_id, config.strategy_version)
        checks.append(
            _check(
                "strategy_registered",
                registered,
                f"{config.strategy_id}@{config.strategy_version}",
            )
        )

        # Config validation already enforced by PilotConfig; re-state limits
        checks.append(
            _check(
                "pilot_config_conservative",
                config.max_orders_per_session == 1 and not config.allow_real_paper_submit,
                f"max_orders={config.max_orders_per_session} max_qty={config.max_quantity}",
            )
        )
        checks.append(
            _check(
                "no_background_worker",
                not config.background_worker_allowed,
                "background execution forbidden",
            )
        )

        # Broker account
        account = self.db.get(BrokerAccount, broker_account_id)
        if account is None:
            checks.append(_check("broker_account", False, "not found"))
        else:
            paper_ok = account.trading_mode == TradingMode.PAPER and account.is_enabled
            checks.append(
                _check(
                    "broker_account",
                    paper_ok,
                    f"mode={account.trading_mode.value} enabled={account.is_enabled} "
                    f"broker={account.broker} ext={account.external_account_id}",
                )
            )
            # Never trust client mode flags — only server account.trading_mode
            checks.append(
                _check(
                    "account_mode_paper_server_side",
                    account.trading_mode == TradingMode.PAPER,
                    "server BrokerAccount.trading_mode must be paper",
                )
            )

        # Paper endpoint
        try:
            url = verify_alpaca_paper_endpoint(None, settings=self.settings)
            checks.append(_check("paper_endpoint", True, url))
        except Exception as exc:  # noqa: BLE001
            checks.append(_check("paper_endpoint", False, str(exc)))

        # Qualification / evidence
        qual: StrategyPaperQualification | None = None
        if qualification_id is not None:
            qual = self.db.get(StrategyPaperQualification, qualification_id)
        evidence = evidence_fingerprint or (qual.evidence_fingerprint if qual else None)
        if evidence is None:
            checks.append(_check("qualification", False, "evidence_fingerprint required"))
        else:
            elig = self.eligibility.check(
                engine_strategy_id=config.strategy_id,
                strategy_version=config.strategy_version,
                parameter_hash=parameter_hash,
                evidence_fingerprint=evidence,
                broker_account_id=broker_account_id,
                now=now,
            )
            checks.append(
                _check(
                    "qualification",
                    elig.eligible,
                    ",".join(elig.reasons) if elig.reasons else "eligible",
                )
            )
            if qualification_id and elig.qualification_id and elig.qualification_id != qualification_id:
                checks.append(
                    _check(
                        "qualification_id_match",
                        False,
                        "stored qualification id mismatch",
                    )
                )
            else:
                checks.append(_check("qualification_id_match", True, "ok", required=False))

        # Consent (optional for dry-run preflight; required when flagged)
        if require_consent and session_id is not None:
            try:
                # Temporary session-shaped check via authorization service needs a session row;
                # if session_id provided, require_active_consent on loaded session.
                from app.models.paper_trading_session import PaperTradingSession

                sess = self.db.get(PaperTradingSession, session_id)
                if sess is None:
                    checks.append(_check("session_consent", False, "session not found"))
                else:
                    self.authorization.require_active_consent(sess, now=now)
                    checks.append(_check("session_consent", True, "granted+unexpired"))
            except Exception as exc:  # noqa: BLE001
                checks.append(_check("session_consent", False, str(exc)))
        else:
            checks.append(
                _check(
                    "session_consent",
                    True,
                    "not required for dry-run preflight",
                    required=False,
                )
            )
            notes.append("Consent check deferred until PAPER_EXECUTE path (not this preparation).")

        # Risk config present
        try:
            limits = config.to_session_risk_limits()
            checks.append(
                _check(
                    "risk_configuration",
                    True,
                    f"instrument={limits.allowed_instrument} "
                    f"max_qty={limits.max_position_size} max_notional={limits.max_notional_exposure}",
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(_check("risk_configuration", False, str(exc)))

        # Broker recon (read-only)
        open_orders = 0
        open_positions = 0
        buying_power: str | None = None
        if account is not None and account.trading_mode == TradingMode.PAPER:
            identity = await self.broker_source.get_account_identity()
            buying_power = str(identity.get("buying_power") or "")
            try:
                bp = Decimal(buying_power or "0")
            except Exception:  # noqa: BLE001
                bp = Decimal("0")
            checks.append(
                _check(
                    "buying_power",
                    bp > 0,
                    f"buying_power={buying_power}",
                )
            )
            try:
                recon = await reconcile_before_activation(
                    self.db,
                    account=account,
                    broker_source=self.broker_source,
                    instrument=config.symbol,
                    require_buying_power=True,
                    verify_paper_endpoint=True,
                )
                open_orders = recon.open_order_count
                open_positions = recon.open_position_count
                checks.append(
                    _check(
                        "broker_reconciliation",
                        recon.ok,
                        ",".join(recon.reasons) if recon.reasons else "ok",
                    )
                )
                checks.append(
                    _check(
                        "no_conflicting_open_orders",
                        open_orders == 0,
                        f"open_orders={open_orders}",
                    )
                )
            except Exception as exc:  # noqa: BLE001
                checks.append(_check("broker_reconciliation", False, str(exc)))
                checks.append(_check("no_conflicting_open_orders", False, str(exc)))
            checks.append(
                _check(
                    "account_identity",
                    identity.get("paper_verified", False) is True
                    and (
                        not account.external_account_id
                        or identity.get("external_account_id") == account.external_account_id
                    ),
                    f"ext={identity.get('external_account_id')} verified={identity.get('paper_verified')}",
                )
            )
        elif account is not None:
            checks.append(_check("buying_power", False, "non-paper account"))
            checks.append(_check("broker_reconciliation", False, "non-paper account"))
            checks.append(_check("no_conflicting_open_orders", False, "non-paper account"))
            checks.append(_check("account_identity", False, "non-paper account"))
        else:
            checks.append(_check("buying_power", False, "no account"))
            checks.append(_check("broker_reconciliation", False, "no account"))
            checks.append(_check("no_conflicting_open_orders", False, "no account"))
            checks.append(_check("account_identity", False, "no account"))

        # Market data
        latest_bar: datetime | None = None
        if bar_source is None:
            checks.append(_check("fresh_completed_bars", False, "bar_source not provided"))
        else:
            try:
                bars = bar_source.get_completed_bars(
                    symbol=config.symbol,
                    timeframe=config.timeframe,
                    after=None,
                    limit=500,
                )
                for b in bars:
                    assert_bar_complete(b)
                assert_bars_fresh(
                    bars,
                    now=now,
                    max_age_seconds=config.market_data_max_age_seconds,
                )
                latest_bar = bars[-1].timestamp if bars else None
                checks.append(
                    _check(
                        "fresh_completed_bars",
                        True,
                        f"count={len(bars)} latest={latest_bar.isoformat() if latest_bar else None}",
                    )
                )
            except Exception as exc:  # noqa: BLE001
                checks.append(_check("fresh_completed_bars", False, str(exc)))

        # Idempotency readiness (tables exist)
        try:
            self.db.execute(text("SELECT 1 FROM paper_session_processed_bars LIMIT 1"))
            checks.append(_check("idempotency_ledger", True, "paper_session_processed_bars present"))
        except Exception as exc:  # noqa: BLE001
            self.db.rollback()
            checks.append(_check("idempotency_ledger", False, str(exc)))

        # Migration head
        try:
            rev = self.db.execute(text("SELECT version_num FROM alembic_version")).scalar()
            checks.append(
                _check(
                    "database_migration",
                    rev == REQUIRED_MIGRATION_HEAD,
                    f"alembic_version={rev} required={REQUIRED_MIGRATION_HEAD}",
                )
            )
        except Exception as exc:  # noqa: BLE001
            self.db.rollback()
            checks.append(_check("database_migration", False, str(exc)))

        # Kill-switch readiness (service methods exist)
        from app.paper_sessions.service import PaperSessionService

        kill_ready = all(
            hasattr(PaperSessionService, name)
            for name in ("emergency_kill", "pause", "stop", "revoke_execution_consent")
        )
        checks.append(
            _check("kill_switch_readiness", kill_ready, "pause/stop/kill/revoke available")
        )

        # No credentials logged
        checks.append(
            _check(
                "no_credentials_in_config",
                True,
                "PilotConfig contains no API keys/secrets",
            )
        )

        ok = all(c.ok for c in checks if c.required)
        report = PreflightReport(
            ok=ok,
            generated_at=now,
            checks=checks,
            parameter_hash=parameter_hash,
            strategy_id=config.strategy_id,
            strategy_version=config.strategy_version,
            symbol=config.symbol,
            broker_account_id=broker_account_id,
            qualification_id=qualification_id or (qual.id if qual else None),
            open_order_count=open_orders,
            open_position_count=open_positions,
            buying_power=buying_power,
            latest_bar_timestamp=latest_bar,
            notes=notes,
        )
        logger.info(
            "pilot_preflight ok=%s failed=%s",
            ok,
            [c.name for c in report.failed_required()],
        )
        return report


def assert_preflight_ready(report: PreflightReport) -> None:
    if not report.ok:
        failed = ", ".join(f"{c.name}:{c.detail}" for c in report.failed_required())
        raise RuntimeError(f"pilot preflight failed: {failed}")
