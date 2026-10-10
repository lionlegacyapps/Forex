"""Controlled DRY_RUN pilot cycle — one decision, zero broker orders."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.evaluation.hashing import configuration_hash
from app.models.enums import PaperSessionExecutionMode, PaperSessionState
from app.models.paper_trading_session import PaperTradingSession
from app.paper_sessions.market_data import InMemorySessionBarSource, SessionBarSource
from app.paper_sessions.reconciliation import BrokerSnapshotSource, StaticBrokerSnapshotSource
from app.paper_sessions.runner import IterationResult, PaperSessionRunner
from app.paper_sessions.service import PaperSessionService
from app.pilot.config import PilotConfig, assert_deployment_execute_disabled
from app.pilot.preflight import PilotPreflightService, PreflightReport, assert_preflight_ready
from app.qualification.auth import AuthenticatedOwner
from app.strategies.protocol import Strategy
from app.strategies.reference import SMACrossoverStrategy
from app.strategies.registry import StrategyRegistry

logger = logging.getLogger(__name__)


class DryRunPilotResult(BaseModel):
    preflight_ok: bool
    session_id: uuid.UUID | None = None
    session_state: str | None = None
    iteration: IterationResult | None = None
    decision_action: str | None = None
    proposal_id: uuid.UUID | None = None
    risk_approved: bool | None = None
    validated: bool | None = None
    submitted: bool = False
    broker_orders_created: int = 0
    market_data_timestamp: datetime | None = None
    market_memory_events: int = 0
    audit_events: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    preflight: PreflightReport | None = None


class ControlledDryRunPilot:
    """Manual one-shot DRY_RUN using the real session runner."""

    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        broker_source: BrokerSnapshotSource | None = None,
        registry: StrategyRegistry | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.broker_source = broker_source or StaticBrokerSnapshotSource()
        self.registry = registry or StrategyRegistry()
        if not self.registry.contains("sma_crossover", "1.0.0"):
            self.registry.register(SMACrossoverStrategy())
        self.preflight = PilotPreflightService(
            db,
            settings=self.settings,
            broker_source=self.broker_source,
            registry=self.registry,
        )

    async def run(
        self,
        *,
        owner: AuthenticatedOwner,
        config: PilotConfig,
        broker_account_id: uuid.UUID,
        qualification_id: uuid.UUID,
        evidence_fingerprint: str,
        strategy_db_id: uuid.UUID | None,
        bar_source: SessionBarSource,
        strategy: Strategy | None = None,
        now: datetime | None = None,
    ) -> DryRunPilotResult:
        now = now or datetime.now(UTC)
        assert_deployment_execute_disabled(self.settings)
        notes: list[str] = []

        report = await self.preflight.run(
            owner=owner,
            config=config,
            broker_account_id=broker_account_id,
            qualification_id=qualification_id,
            evidence_fingerprint=evidence_fingerprint,
            bar_source=bar_source,
            now=now,
            require_consent=False,
        )
        if not report.ok:
            return DryRunPilotResult(
                preflight_ok=False,
                preflight=report,
                notes=["preflight failed; dry-run aborted"],
            )
        assert_preflight_ready(report)

        svc = PaperSessionService(
            self.db,
            settings=self.settings,
            allow_paper_execute=False,
            broker_source=self.broker_source,
        )
        param_hash = configuration_hash(config.parameters)
        session = svc.create_session(
            owner=owner,
            engine_strategy_id=config.strategy_id,
            strategy_version=config.strategy_version,
            parameter_hash=param_hash,
            parameters=dict(config.parameters),
            qualification_approval_id=qualification_id,
            evidence_fingerprint=evidence_fingerprint,
            broker_account_id=broker_account_id,
            instrument=config.symbol,
            timeframe=config.timeframe,
            risk_limits=config.to_session_risk_limits(),
            strategy_db_id=strategy_db_id,
            execution_mode=PaperSessionExecutionMode.DRY_RUN,
            max_orders_per_session=config.max_orders_per_session,
        )
        await svc.activate(session.id, owner=owner, now=now)
        notes.append("session activated in DRY_RUN")

        strat = strategy or self.registry.get(config.strategy_id, config.strategy_version)
        runner = PaperSessionRunner(
            self.db,
            bar_source=bar_source,
            strategy=strat,
            worker_id="pilot-dry-run",
            paper_execute_enabled=False,
            max_outstanding_orders=config.max_outstanding_orders,
        )
        iteration = await runner.run_once(session.id, now=now)

        self.db.refresh(session)
        audit = (
            self.db.execute(
                text(
                    "SELECT event_type FROM audit_events"
                    " WHERE entity_id = :eid ORDER BY created_at"
                ),
                {"eid": session.id},
            )
            .scalars()
            .all()
        )
        mem = self.db.execute(
            text(
                "SELECT count(*) FROM market_memory_events"
                " WHERE event_type = 'paper_session_event'"
                " AND market_context->>'session_id' = :sid"
            ),
            {"sid": str(session.id)},
        ).scalar()
        if not mem:
            mem = self.db.execute(
                text(
                    "SELECT count(*) FROM market_memory_events"
                    " WHERE event_type = 'paper_session_event'"
                )
            ).scalar()

        if iteration.decision_action == "no_action":
            notes.append("strategy returned NO_ACTION — recorded honestly; not manufactured")

        assert iteration.submitted is False
        assert runner.broker_orders_created == 0
        assert svc.broker_orders_created == 0

        return DryRunPilotResult(
            preflight_ok=True,
            session_id=session.id,
            session_state=session.session_state.value,
            iteration=iteration,
            decision_action=iteration.decision_action,
            proposal_id=iteration.proposal_id,
            risk_approved=iteration.risk_approved,
            validated=iteration.validated,
            submitted=False,
            broker_orders_created=0,
            market_data_timestamp=iteration.bar_timestamp,
            market_memory_events=int(mem or 0),
            audit_events=list(audit),
            notes=notes,
            preflight=report,
        )


def in_memory_bars(bars: list) -> InMemorySessionBarSource:
    return InMemorySessionBarSource(bars)
