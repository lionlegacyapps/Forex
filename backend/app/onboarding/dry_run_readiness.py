"""Read-only DRY_RUN readiness checklist — never starts a session."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.broker_account import BrokerAccount
from app.models.enums import QualificationState, TradingMode
from app.models.strategy_paper_qualification import StrategyPaperQualification
from app.onboarding.market_data_check import verify_alpaca_market_data_access
from app.onboarding.owner import owner_allowlist_status
from app.pilot.config import default_pilot_config


@dataclass
class ReadinessCheck:
    name: str
    ok: bool
    detail: str


@dataclass
class DryRunReadinessReport:
    ready: bool
    generated_at: datetime
    checks: list[ReadinessCheck] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "generated_at": self.generated_at.isoformat(),
            "checks": [c.__dict__ for c in self.checks],
            "notes": self.notes,
        }


async def assess_dry_run_readiness(
    db: Session,
    *,
    settings: Settings | None = None,
    qualification_id: str | None = "b46aa6ab-dcb4-41d7-b3e0-d4d5667d0573",
    now: datetime | None = None,
    check_live_market_data: bool = True,
) -> DryRunReadinessReport:
    """Fail-closed readiness. Does not start sessions or submit orders."""
    cfg = settings or get_settings()
    now = now or datetime.now(UTC)
    checks: list[ReadinessCheck] = []
    notes = [
        "DRY_RUN readiness does not authorize PAPER_EXECUTE",
        "PAPER_SESSION_EXECUTE_ENABLED must remain false",
        "Historical bars from a prior session day are not automatically fresh",
    ]

    allow = owner_allowlist_status(cfg)
    checks.append(
        ReadinessCheck(
            name="owner_allowlist_configured",
            ok=allow.configured,
            detail=f"subject_count={allow.subject_count}",
        )
    )

    checks.append(
        ReadinessCheck(
            name="execute_flag_disabled",
            ok=not cfg.paper_session_execute_enabled,
            detail=f"PAPER_SESSION_EXECUTE_ENABLED={cfg.paper_session_execute_enabled}",
        )
    )

    # Registered paper account (present; enablement is a separate later decision)
    papers = db.scalars(
        select(BrokerAccount).where(
            BrokerAccount.broker == "alpaca",
            BrokerAccount.trading_mode == TradingMode.PAPER,
        )
    ).all()
    checks.append(
        ReadinessCheck(
            name="paper_broker_account_registered",
            ok=len(papers) >= 1,
            detail=f"paper_accounts={len(papers)}",
        )
    )
    enabled = [a for a in papers if a.is_enabled]
    checks.append(
        ReadinessCheck(
            name="paper_account_enablement_decision",
            ok=True,  # informational — not required yet for this milestone stop point
            detail=(
                f"enabled={len(enabled)} disabled={len(papers) - len(enabled)}; "
                "enablement requires separate owner decision"
            ),
        )
    )

    # Approved qualification
    approved = False
    qual_detail = "qualification_id not checked"
    if qualification_id:
        import uuid

        row = db.get(StrategyPaperQualification, uuid.UUID(qualification_id))
        if row is None:
            qual_detail = "qualification record missing"
        else:
            approved = row.qualification_state == QualificationState.APPROVED_FOR_PAPER
            expired = row.expires_at is not None and now >= row.expires_at
            qual_detail = (
                f"state={row.qualification_state.value} expired={expired} "
                f"param={row.parameter_hash[:12]}…"
            )
            if expired:
                approved = False
    checks.append(
        ReadinessCheck(
            name="qualification_approved",
            ok=approved,
            detail=qual_detail,
        )
    )

    # Market data / IEX
    if check_live_market_data:
        try:
            md = await verify_alpaca_market_data_access(settings=cfg)
            # Freshness: for daily bars, "fresh" means latest completed bar is
            # not older than market_data_max_age from pilot config (default 1 day).
            # Do NOT treat multi-day-old history as automatically fresh for session start.
            pilot = default_pilot_config()
            latest = md.latest_bar_timestamp
            fresh = False
            age_s = None
            if latest is not None:
                age_s = (now - latest).total_seconds()
                fresh = age_s <= pilot.market_data_max_age_seconds
            checks.append(
                ReadinessCheck(
                    name="iex_market_data_access",
                    ok=md.ok,
                    detail=md.detail,
                )
            )
            checks.append(
                ReadinessCheck(
                    name="fresh_completed_bars",
                    ok=bool(fresh),
                    detail=(
                        f"latest={latest.isoformat() if latest else None} "
                        f"age_seconds={age_s} "
                        f"max_age={pilot.market_data_max_age_seconds}"
                    ),
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                ReadinessCheck(
                    name="iex_market_data_access",
                    ok=False,
                    detail=str(exc),
                )
            )
            checks.append(
                ReadinessCheck(
                    name="fresh_completed_bars",
                    ok=False,
                    detail="skipped — market data check failed",
                )
            )
    else:
        checks.append(
            ReadinessCheck(
                name="iex_market_data_access",
                ok=False,
                detail="live check skipped",
            )
        )

    # Risk limits / session config presence (config object validates itself)
    try:
        cfg_pilot = default_pilot_config()
        checks.append(
            ReadinessCheck(
                name="session_configuration",
                ok=cfg_pilot.max_orders_per_session == 1
                and cfg_pilot.allow_real_paper_submit is False,
                detail=(
                    f"strategy={cfg_pilot.strategy_id}@{cfg_pilot.strategy_version} "
                    f"max_orders={cfg_pilot.max_orders_per_session}"
                ),
            )
        )
        checks.append(
            ReadinessCheck(
                name="risk_limits_configured",
                ok=cfg_pilot.max_quantity > 0 and cfg_pilot.max_notional > 0,
                detail=(
                    f"max_qty={cfg_pilot.max_quantity} max_notional={cfg_pilot.max_notional} "
                    f"max_daily_loss={cfg_pilot.max_daily_loss}"
                ),
            )
        )
    except Exception as exc:  # noqa: BLE001
        checks.append(
            ReadinessCheck(
                name="session_configuration",
                ok=False,
                detail=str(exc),
            )
        )

    # Conflicting orders — without an enabled account + live broker pull we only
    # note that no local open-order inventory is checked until preflight.
    checks.append(
        ReadinessCheck(
            name="no_conflicting_orders",
            ok=False,
            detail=(
                "not verified yet — run PilotPreflightService after approval + "
                "account enablement (read-only broker open-order check)"
            ),
        )
    )

    # Required checks for READY
    required_ok = {
        "owner_allowlist_configured",
        "execute_flag_disabled",
        "paper_broker_account_registered",
        "qualification_approved",
        "iex_market_data_access",
        "fresh_completed_bars",
        "session_configuration",
        "risk_limits_configured",
        "no_conflicting_orders",
    }
    by_name = {c.name: c for c in checks}
    ready = all(by_name[n].ok for n in required_ok if n in by_name)

    return DryRunReadinessReport(
        ready=ready, generated_at=now, checks=checks, notes=notes
    )
