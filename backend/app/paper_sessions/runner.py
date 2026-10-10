"""Bounded deterministic paper-session iteration.

DRY_RUN default. PAPER_EXECUTE submits only through BrokerRouter after
Risk → Validator, with session-scoped consent rechecked immediately before submit.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.brokers.execution.client_order_id import build_client_order_id
from app.brokers.execution.errors import (
    AMBIGUOUS_IDEMPOTENCY_STATE,
    NETWORK_TIMEOUT,
)
from app.models.enums import (
    AssetClass,
    OrderStatus,
    PaperSessionExecutionMode,
    PaperSessionState,
    PositionStatus,
)
from app.models.mixins import utc_now
from app.models.order import Order
from app.models.paper_trading_session import PaperTradingSession
from app.models.position import Position
from app.paper_sessions.authorization import PaperExecutionAuthorizationService
from app.paper_sessions.errors import (
    ConsentError,
    LeaseError,
    PaperExecuteDisabledError,
    PaperSessionError,
    UncertainOrderAcknowledgmentError,
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

logger = logging.getLogger(__name__)

# Module default remains fail-closed. Constructor may enable when settings + consent allow.
PAPER_EXECUTE_ENABLED = False

_UNCERTAIN_CODES = frozenset({NETWORK_TIMEOUT, AMBIGUOUS_IDEMPOTENCY_STATE})
_OPEN_ORDER_STATUSES = frozenset(
    {
        OrderStatus.NEW,
        OrderStatus.SUBMITTED,
        OrderStatus.PARTIALLY_FILLED,
    }
)


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
    uncertain: bool = False
    warnings: list[str] = Field(default_factory=list)
    bar_timestamp: datetime | None = None
    route_reason_code: str | None = None


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
        authorization: PaperExecutionAuthorizationService | None = None,
        worker_id: str = "paper-session-worker",
        lease_seconds: int = 60,
        paper_execute_enabled: bool = PAPER_EXECUTE_ENABLED,
        max_outstanding_orders: int = 1,
    ) -> None:
        self.db = db
        self.bar_source = bar_source
        self.strategy = strategy
        self.proposals = proposal_service or TradeProposalService(db)
        self.eligibility = eligibility or PaperEligibilityService(db)
        self.memory = memory or PaperSessionMemoryRecorder(db)
        self.authorization = authorization or PaperExecutionAuthorizationService(db)
        self.repo = PaperSessionRepository(db)
        self.adapter = StrategyProposalAdapter()
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.paper_execute_enabled = paper_execute_enabled
        self.max_outstanding_orders = max_outstanding_orders
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

        try:
            row = self.repo.acquire_lease(
                row,
                owner=self.worker_id,
                expires_at=now + timedelta(seconds=self.lease_seconds),
                now=now,
            )
        except Exception as exc:
            raise LeaseError(str(exc)) from exc

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

        open_count = self._open_position_count(row.broker_account_id)
        if (
            decision.action in {DecisionAction.ENTER_LONG, DecisionAction.ENTER_SHORT}
            and open_count >= limits.max_concurrent_positions
        ):
            return self._reject_and_advance(
                row,
                bar.timestamp,
                dec_id,
                idem,
                decision,
                now,
                "max_concurrent_positions",
            )

        qty = decision.quantity or Decimal("0")
        if qty > limits.max_position_size:
            return self._reject_and_advance(
                row, bar.timestamp, dec_id, idem, decision, now, "max_position_size"
            )

        notional = qty * bar.close
        if notional > limits.max_notional_exposure:
            return self._reject_and_advance(
                row, bar.timestamp, dec_id, idem, decision, now, "max_notional_exposure"
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

        proposal = self.proposals.create_proposal(proposal_input)
        risk = self.proposals.evaluate_risk(proposal)
        validation = None
        submitted = False
        uncertain = False
        route_reason: str | None = None
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
            if row.submissions_blocked:
                raise ConsentError(
                    f"submissions blocked: {row.submissions_block_reason}",
                    code="submissions_blocked",
                )

            # Recheck authorization immediately before submission.
            auth = self.authorization.require_active_consent(row, now=now)

            outstanding = self._outstanding_order_count(row.broker_account_id)
            if outstanding >= self.max_outstanding_orders:
                return self._reject_and_advance(
                    row,
                    bar.timestamp,
                    dec_id,
                    idem,
                    decision,
                    now,
                    "max_outstanding_orders",
                    proposal_id=proposal.id,
                    risk_approved=risk.approved,
                    validated=validation.valid,
                )

            route = await self.proposals.route(proposal)
            route_reason = route.reason_code
            if route.success:
                submitted = True
                self._broker_orders_created += 1
                row = self.repo.update_atomic(
                    row,
                    expected_version=row.state_version,
                    orders_submitted_count=row.orders_submitted_count + 1,
                )
                self.authorization.consume_if_one_time(auth, now=now)
            elif route.reason_code in _UNCERTAIN_CODES:
                uncertain = True
                row = self.repo.update_atomic(
                    row,
                    expected_version=row.state_version,
                    submissions_blocked=True,
                    submissions_block_reason=f"uncertain_ack:{route.reason_code}",
                )
                reconciled = await self.reconcile_uncertain_orders(row)
                outcome_u: dict[str, Any] = {
                    "action": decision.action.value,
                    "dry_run": False,
                    "risk_approved": True,
                    "validated": True,
                    "submitted": False,
                    "uncertain": True,
                    "reconciled": reconciled,
                    "proposal_status": proposal.status.value,
                    "route_reason_code": route.reason_code,
                }
                self.repo.record_processed(
                    session_id=row.id,
                    bar_timestamp=bar.timestamp,
                    decision_identity=dec_id,
                    idempotency_key=idem,
                    proposal_id=proposal.id,
                    outcome=outcome_u,
                )
                self.memory.record(
                    session_id=row.id,
                    symbol=row.instrument,
                    event_time=now,
                    event_kind="uncertain_order_ack",
                    payload={
                        "reason_code": route.reason_code,
                        "proposal_id": str(proposal.id),
                        "message": route.message,
                        "reconciled": reconciled,
                    },
                    strategy_db_id=row.strategy_db_id,
                )
                row = self.repo.update_atomic(
                    row,
                    expected_version=row.state_version,
                    last_processed_bar_at=bar.timestamp,
                    last_heartbeat_at=now,
                )
                if not reconciled:
                    raise UncertainOrderAcknowledgmentError(
                        f"uncertain broker ack: {route.reason_code}; "
                        "new submissions blocked until reconciled",
                        code=route.reason_code or "uncertain_order_ack",
                    )
                return IterationResult(
                    session_id=session_id,
                    processed=True,
                    decision_action=decision.action.value,
                    proposal_id=proposal.id,
                    risk_approved=True,
                    validated=True,
                    submitted=False,
                    uncertain=True,
                    dry_run=False,
                    bar_timestamp=bar.timestamp,
                    route_reason_code=route.reason_code,
                    warnings=["uncertain_ack_reconciled_block_remains"],
                )

        outcome: dict[str, Any] = {
            "action": decision.action.value,
            "dry_run": dry_run,
            "risk_approved": risk.approved,
            "validated": None if validation is None else validation.valid,
            "submitted": submitted,
            "uncertain": uncertain,
            "proposal_status": proposal.status.value,
            "route_reason_code": route_reason,
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
            uncertain=uncertain,
            bar_timestamp=bar.timestamp,
            route_reason_code=route_reason,
        )

    async def reconcile_uncertain_orders(
        self, session: PaperTradingSession
    ) -> bool:
        """Reconcile local NEW orders via client_order_id before any retry.

        Never blindly resubmits. Returns True when all uncertain locals resolved.
        """
        router = self.proposals.broker_router
        assert router is not None
        account = session.broker_account_id
        locals_ = (
            self.db.execute(
                select(Order).where(
                    Order.broker_account_id == account,
                    Order.status.in_(
                        [OrderStatus.NEW, OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED]
                    ),
                )
            )
            .scalars()
            .all()
        )
        if not locals_:
            return False

        adapter = router.get_execution_adapter("alpaca")
        if adapter is None:
            return False

        all_resolved = True
        for order in locals_:
            if order.broker_order_id:
                continue
            client_id = build_client_order_id(order.id)
            payload = None
            if hasattr(adapter, "get_order_by_client_order_id"):
                payload = await adapter.get_order_by_client_order_id(client_id)  # type: ignore[attr-defined]
            if not payload:
                all_resolved = False
                continue
            order.broker_order_id = str(payload.get("id") or "")
            status = str(payload.get("status") or "accepted").lower()
            if status in {"accepted", "new", "pending_new"}:
                order.status = OrderStatus.SUBMITTED
            elif status == "partially_filled":
                order.status = OrderStatus.PARTIALLY_FILLED
            elif status == "filled":
                order.status = OrderStatus.FILLED
            elif status in {"canceled", "cancelled"}:
                order.status = OrderStatus.CANCELLED
            elif status == "rejected":
                order.status = OrderStatus.REJECTED
            else:
                order.status = OrderStatus.SUBMITTED
            order.submitted_at = order.submitted_at or utc_now()
            self.db.flush()
            self.memory.record(
                session_id=session.id,
                symbol=session.instrument,
                event_time=utc_now(),
                event_kind="uncertain_order_reconciled",
                payload={
                    "order_id": str(order.id),
                    "broker_order_id": order.broker_order_id,
                    "client_order_id": client_id,
                    "status": order.status.value,
                },
                strategy_db_id=session.strategy_db_id,
            )

        if all_resolved and session.submissions_blocked:
            # Keep block until operator clears — do not auto-unblock after recovery
            # of uncertain state; recovery means we found the order, not that it's safe
            # to continue submitting. Operator must clear_submission_block.
            pass
        return all_resolved

    def _reject_and_advance(
        self,
        row: PaperTradingSession,
        bar_ts: datetime,
        dec_id: str,
        idem: str,
        decision: StrategyDecision,
        now: datetime,
        reason: str,
        *,
        proposal_id: uuid.UUID | None = None,
        risk_approved: bool | None = None,
        validated: bool | None = None,
    ) -> IterationResult:
        self.repo.record_processed(
            session_id=row.id,
            bar_timestamp=bar_ts,
            decision_identity=dec_id,
            idempotency_key=idem,
            proposal_id=proposal_id,
            outcome={"rejected": reason},
        )
        row = self.repo.update_atomic(
            row,
            expected_version=row.state_version,
            last_processed_bar_at=bar_ts,
            last_heartbeat_at=now,
        )
        return IterationResult(
            session_id=row.id,
            processed=True,
            decision_action=decision.action.value,
            proposal_id=proposal_id,
            risk_approved=risk_approved,
            validated=validated,
            bar_timestamp=bar_ts,
            warnings=[reason],
            dry_run=row.execution_mode == PaperSessionExecutionMode.DRY_RUN,
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

    def _outstanding_order_count(self, broker_account_id: uuid.UUID) -> int:
        rows = (
            self.db.execute(
                select(Order).where(
                    Order.broker_account_id == broker_account_id,
                    Order.status.in_(list(_OPEN_ORDER_STATUSES)),
                )
            )
            .scalars()
            .all()
        )
        return len(rows)
