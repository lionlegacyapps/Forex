"""Bounded deterministic paper-session iteration (DRY_RUN default)."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.enums import (
    AssetClass,
    PaperSessionExecutionMode,
    PaperSessionState,
    PositionStatus,
)
from app.models.mixins import utc_now
from app.models.paper_trading_session import PaperTradingSession
from app.models.position import Position
from app.paper_sessions.errors import (
    LeaseError,
    PaperExecuteDisabledError,
    PaperSessionError,
)
from app.paper_sessions.idempotency import build_idempotency_key, decision_identity
from app.paper_sessions.market_data import (
    SessionBarSource,
    assert_bar_complete,
    assert_bars_fresh,
)
from app.paper_sessions.memory import PaperSessionMemoryRecorder
from app.paper_sessions.repository import PaperSessionRepository
from app.paper_sessions.risk_limits import SessionRiskLimits
from app.qualification.eligibility import PaperEligibilityService
from app.strategies.context import PortfolioContextView, StrategyContext, StrategyPositionView
from app.strategies.decision import DecisionAction, StrategyDecision
from app.strategies.proposal_adapter import StrategyProposalAdapter
from app.strategies.protocol import Strategy
from app.trading.proposals.service import TradeProposalService
from sqlalchemy import select

logger = logging.getLogger(__name__)

# V1 hard disable — PAPER_EXECUTE path structure exists but cannot submit.
PAPER_EXECUTE_ENABLED = False


class IterationResult(BaseModel):
    session_id: uuid.UUID
    processed: bool
    skipped_duplicate: bool = False
    decision_action: str | None = None
    proposal_id: uuid.UUID | None = None
    risk_approved: bool | None = None
    validated: bool | None = None
    submitted: bool = False
    broker_orders_created: int = 0
    dry_run: bool = True
    warnings: list[str] = Field(default_factory=list)
    bar_timestamp: datetime | None = None


class PaperSessionRunner:
    """One iteration of the controlled paper session loop."""

    def __init__(
        self,
        db: Session,
        *,
        bar_source: SessionBarSource,
        strategy: Strategy,
        proposal_service: TradeProposalService | None = None,
        eligibility: PaperEligibilityService | None = None,
        memory: PaperSessionMemoryRecorder | None = None,
        worker_id: str = "paper-session-worker",
        lease_seconds: int = 60,
        paper_execute_enabled: bool = PAPER_EXECUTE_ENABLED,
    ) -> None:
        self.db = db
        self.bar_source = bar_source
        self.strategy = strategy
        self.proposals = proposal_service or TradeProposalService(db)
        self.eligibility = eligibility or PaperEligibilityService(db)
        self.memory = memory or PaperSessionMemoryRecorder(db)
        self.repo = PaperSessionRepository(db)
        self.adapter = StrategyProposalAdapter()
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.paper_execute_enabled = paper_execute_enabled
        self._broker_orders_created = 0

    @property
    def broker_orders_created(self) -> int:
        return self._broker_orders_created

    async def run_once(
        self,
        session_id: uuid.UUID,
        *,
        now: datetime | None = None,
    ) -> IterationResult:
        now = now or datetime.now(UTC)
        row = self.repo.get(session_id)
        if row is None:
            raise PaperSessionError("session not found", code="not_found")

        if row.session_state == PaperSessionState.PAUSED:
            return IterationResult(
                session_id=session_id,
                processed=False,
                warnings=["session_paused"],
            )
        if row.session_state != PaperSessionState.RUNNING:
            return IterationResult(
                session_id=session_id,
                processed=False,
                warnings=[f"session_not_running:{row.session_state.value}"],
            )

        # Lease
        try:
            row = self.repo.acquire_lease(
                row,
                owner=self.worker_id,
                expires_at=now + timedelta(seconds=self.lease_seconds),
                now=now,
            )
        except Exception as exc:
            raise LeaseError(str(exc)) from exc

        # Re-check eligibility
        elig = self.eligibility.check(
            engine_strategy_id=row.engine_strategy_id,
            strategy_version=row.strategy_version,
            parameter_hash=row.parameter_hash,
            evidence_fingerprint=row.evidence_fingerprint,
            broker_account_id=row.broker_account_id,
            now=now,
        )
        if not elig.eligible:
            self._fail(row, "eligibility_lost:" + ",".join(elig.reasons))
            raise PaperSessionError(
                "paper eligibility failed during iteration",
                code="eligibility_lost",
            )

        limits = SessionRiskLimits.from_storage(row.risk_limits)
        if row.instrument.upper() != limits.allowed_instrument:
            self._fail(row, "instrument_not_allowed")
            raise PaperSessionError("instrument not allowed", code="instrument_mismatch")

        if row.started_at and (
            (now - row.started_at).total_seconds() > limits.max_session_duration_seconds
        ):
            self._fail(row, "session_duration_exceeded")
            raise PaperSessionError("session expired", code="session_expired")

        if row.orders_submitted_count >= row.max_orders_per_session:
            self._fail(row, "max_orders_per_session")
            raise PaperSessionError("max orders reached", code="max_orders")

        # Market data — completed bars after cursor
        history = self.bar_source.get_completed_bars(
            symbol=row.instrument,
            timeframe=row.timeframe,
            after=None,
            limit=500,
        )
        if not history:
            raise PaperSessionError("missing market data", code="missing_market_data")
        for b in history:
            assert_bar_complete(b)

        # Next unprocessed completed bar
        cursor = row.last_processed_bar_at
        candidates = [b for b in history if cursor is None or b.timestamp > cursor]
        if not candidates:
            row = self.repo.update_atomic(
                row,
                expected_version=row.state_version,
                last_heartbeat_at=now,
            )
            return IterationResult(
                session_id=session_id,
                processed=False,
                warnings=["no_new_completed_bars"],
            )

        bar = candidates[0]
        assert_bar_complete(bar)
        # Freshness against latest available completed bar
        assert_bars_fresh(
            history,
            now=now,
            max_age_seconds=limits.market_data_max_age_seconds,
        )

        visible = [b for b in history if b.timestamp <= bar.timestamp]
        position = self._position_view(row.broker_account_id, row.instrument)
        ctx = StrategyContext(
            symbol=row.instrument,
            asset_class=AssetClass.EQUITY,
            timestamp=bar.timestamp,
            timeframe=row.timeframe,
            bars=visible,
            reference_price=bar.close,
            position=position,
            portfolio=PortfolioContextView(
                cash=None,
                equity=None,
                buying_power=None,
            ),
            parameters=dict(row.parameters or {}),
            strategy_id=row.engine_strategy_id,
            strategy_version=row.strategy_version,
        )
        params = self.strategy.validate_parameters(dict(row.parameters or {}))
        ctx.parameters = params
        decision = self.strategy.evaluate(ctx)
        dec_id = decision_identity(decision)
        idem = build_idempotency_key(
            session_id=row.id,
            strategy_id=row.engine_strategy_id,
            strategy_version=row.strategy_version,
            broker_account_id=row.broker_account_id,
            instrument=row.instrument,
            bar_timestamp=bar.timestamp,
            decision_id=dec_id,
        )

        if self.repo.find_processed(row.id, idem) is not None:
            row = self.repo.update_atomic(
                row,
                expected_version=row.state_version,
                last_processed_bar_at=bar.timestamp,
                last_heartbeat_at=now,
            )
            return IterationResult(
                session_id=session_id,
                processed=False,
                skipped_duplicate=True,
                decision_action=decision.action.value,
                bar_timestamp=bar.timestamp,
                warnings=["duplicate_bar_decision"],
            )

        self.memory.record(
            session_id=row.id,
            symbol=row.instrument,
            event_time=now,
            event_kind="strategy_decision",
            payload={
                "action": decision.action.value,
                "bar_timestamp": bar.timestamp.isoformat(),
                "idempotency_key": idem,
                "session_state": row.session_state.value,
            },
            strategy_db_id=row.strategy_db_id,
        )

        if not decision.is_actionable:
            self.repo.record_processed(
                session_id=row.id,
                bar_timestamp=bar.timestamp,
                decision_identity=dec_id,
                idempotency_key=idem,
                proposal_id=None,
                outcome={"action": decision.action.value, "dry_run": True},
            )
            row = self.repo.update_atomic(
                row,
                expected_version=row.state_version,
                last_processed_bar_at=bar.timestamp,
                last_heartbeat_at=now,
            )
            return IterationResult(
                session_id=session_id,
                processed=True,
                decision_action=decision.action.value,
                bar_timestamp=bar.timestamp,
                dry_run=row.execution_mode == PaperSessionExecutionMode.DRY_RUN,
            )

        # Concurrent positions guard
        open_count = self._open_position_count(row.broker_account_id)
        if (
            decision.action in {DecisionAction.ENTER_LONG, DecisionAction.ENTER_SHORT}
            and open_count >= limits.max_concurrent_positions
        ):
            self.repo.record_processed(
                session_id=row.id,
                bar_timestamp=bar.timestamp,
                decision_identity=dec_id,
                idempotency_key=idem,
                proposal_id=None,
                outcome={"rejected": "max_concurrent_positions"},
            )
            row = self.repo.update_atomic(
                row,
                expected_version=row.state_version,
                last_processed_bar_at=bar.timestamp,
                last_heartbeat_at=now,
            )
            return IterationResult(
                session_id=session_id,
                processed=True,
                decision_action=decision.action.value,
                bar_timestamp=bar.timestamp,
                warnings=["max_concurrent_positions"],
            )

        # Size check
        qty = decision.quantity or Decimal("0")
        if qty > limits.max_position_size:
            self.repo.record_processed(
                session_id=row.id,
                bar_timestamp=bar.timestamp,
                decision_identity=dec_id,
                idempotency_key=idem,
                proposal_id=None,
                outcome={"rejected": "max_position_size"},
            )
            row = self.repo.update_atomic(
                row,
                expected_version=row.state_version,
                last_processed_bar_at=bar.timestamp,
                last_heartbeat_at=now,
            )
            return IterationResult(
                session_id=session_id,
                processed=True,
                decision_action=decision.action.value,
                warnings=["max_position_size"],
                bar_timestamp=bar.timestamp,
            )

        notional = qty * bar.close
        if notional > limits.max_notional_exposure:
            self.repo.record_processed(
                session_id=row.id,
                bar_timestamp=bar.timestamp,
                decision_identity=dec_id,
                idempotency_key=idem,
                proposal_id=None,
                outcome={"rejected": "max_notional_exposure"},
            )
            row = self.repo.update_atomic(
                row,
                expected_version=row.state_version,
                last_processed_bar_at=bar.timestamp,
                last_heartbeat_at=now,
            )
            return IterationResult(
                session_id=session_id,
                processed=True,
                decision_action=decision.action.value,
                warnings=["max_notional_exposure"],
                bar_timestamp=bar.timestamp,
            )

        proposal_input = self.adapter.to_proposal_input(
            decision,
            broker_account_id=row.broker_account_id,
            strategy_db_id=row.strategy_db_id,
            idempotency_key=idem,
            strategy_id=row.engine_strategy_id,
            strategy_version=row.strategy_version,
            metadata={
                "paper_session_id": str(row.id),
                "bar_timestamp": bar.timestamp.isoformat(),
                "execution_mode": row.execution_mode.value,
            },
        )
        if limits.require_stop_loss and proposal_input.stop_loss_price is None:
            # Align with risk policy default — still let Risk Engine decide, but warn
            pass

        proposal = self.proposals.create_proposal(proposal_input)
        risk = self.proposals.evaluate_risk(proposal)
        validation = None
        submitted = False
        if risk.approved:
            validation = self.proposals.validate_order(proposal)

        dry_run = row.execution_mode == PaperSessionExecutionMode.DRY_RUN
        if (
            risk.approved
            and validation is not None
            and validation.valid
            and not dry_run
        ):
            if not self.paper_execute_enabled:
                raise PaperExecuteDisabledError()
            # Future PAPER_EXECUTE: reconcile uncertain orders before submit.
            # Intentionally unreachable in V1.
            route = await self.proposals.route(proposal)
            submitted = route.success
            if submitted:
                self._broker_orders_created += 1
                row = self.repo.update_atomic(
                    row,
                    expected_version=row.state_version,
                    orders_submitted_count=row.orders_submitted_count + 1,
                )

        outcome: dict[str, Any] = {
            "action": decision.action.value,
            "dry_run": dry_run,
            "risk_approved": risk.approved,
            "validated": None if validation is None else validation.valid,
            "submitted": submitted,
            "proposal_status": proposal.status.value,
        }
        self.repo.record_processed(
            session_id=row.id,
            bar_timestamp=bar.timestamp,
            decision_identity=dec_id,
            idempotency_key=idem,
            proposal_id=proposal.id,
            outcome=outcome,
        )
        self.memory.record(
            session_id=row.id,
            symbol=row.instrument,
            event_time=now,
            event_kind="pipeline_result",
            payload={**outcome, "idempotency_key": idem, "proposal_id": str(proposal.id)},
            strategy_db_id=row.strategy_db_id,
        )
        row = self.repo.update_atomic(
            row,
            expected_version=row.state_version,
            last_processed_bar_at=bar.timestamp,
            last_heartbeat_at=now,
        )
        assert self._broker_orders_created == 0 or not dry_run
        return IterationResult(
            session_id=session_id,
            processed=True,
            decision_action=decision.action.value,
            proposal_id=proposal.id,
            risk_approved=risk.approved,
            validated=None if validation is None else validation.valid,
            submitted=submitted,
            broker_orders_created=self._broker_orders_created,
            dry_run=dry_run,
            bar_timestamp=bar.timestamp,
        )

    def _fail(self, row: PaperTradingSession, detail: str) -> None:
        from app.paper_sessions.states import assert_transition

        try:
            assert_transition(row.session_state, PaperSessionState.FAILED)
            self.repo.transition_atomic(
                row,
                expected_version=row.state_version,
                new_state=PaperSessionState.FAILED,
                failure_detail=detail,
                stopped_at=utc_now(),
                stop_reason=detail,
            )
        except Exception:  # noqa: BLE001
            logger.exception("failed to mark session failed")

    def _position_view(
        self, broker_account_id: uuid.UUID, symbol: str
    ) -> StrategyPositionView | None:
        pos = self.db.execute(
            select(Position).where(
                Position.broker_account_id == broker_account_id,
                Position.symbol == symbol.strip().upper(),
                Position.status == PositionStatus.OPEN,
            )
        ).scalars().first()
        if pos is None:
            return StrategyPositionView(
                symbol=symbol, quantity=Decimal("0"), side="flat"
            )
        side = "long" if pos.quantity > 0 else "short" if pos.quantity < 0 else "flat"
        return StrategyPositionView(
            symbol=symbol,
            quantity=pos.quantity,
            average_entry_price=pos.average_entry_price,
            side=side,
        )

    def _open_position_count(self, broker_account_id: uuid.UUID) -> int:
        rows = self.db.execute(
            select(Position).where(
                Position.broker_account_id == broker_account_id,
                Position.status == PositionStatus.OPEN,
            )
        ).scalars().all()
        return len(rows)
