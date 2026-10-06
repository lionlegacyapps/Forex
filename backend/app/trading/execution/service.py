"""Paper execution orchestrator — fill + execution + accounting atomically."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import service as audit_events
from app.audit.service import AuditService
from app.models.enums import OrderStatus
from app.models.execution import Execution
from app.models.order import Order
from app.models.trade_proposal import TradeProposal
from app.trading.execution.cash_ledger import SimulatedCashLedger, default_cash_ledger
from app.trading.execution.fill_logic import evaluate_fill
from app.trading.execution.market_data import SimulationMarketData, default_simulation_market_data
from app.trading.execution.order_transitions import assert_order_transition
from app.trading.execution.position_accounting import PositionAccountingService


class PaperExecutionResult(BaseModel):
    filled: bool
    reason_code: str | None = None
    message: str = ""
    broker_execution_id: str | None = None
    execution_id: str | None = None
    fill_price: Decimal | None = None
    realized_pnl: Decimal | None = None
    details: dict = Field(default_factory=dict)


class PaperExecutionService:
    """Process submitted simulation orders into fills and portfolio updates."""

    def __init__(
        self,
        session: Session,
        *,
        market_data: SimulationMarketData | None = None,
        cash_ledger: SimulatedCashLedger | None = None,
        accounting: PositionAccountingService | None = None,
        audit: AuditService | None = None,
    ) -> None:
        self._session = session
        self._market = market_data or default_simulation_market_data
        self._cash = cash_ledger or default_cash_ledger
        self._audit = audit or AuditService(session)
        self._accounting = accounting or PositionAccountingService(session, audit=self._audit)

    def process_submitted_order(self, order: Order) -> PaperExecutionResult:
        """Attempt a deterministic full fill for a SUBMITTED simulation order.

        Fail-closed: any unexpected error propagates for caller rollback.
        """
        if order.status != OrderStatus.SUBMITTED:
            return PaperExecutionResult(
                filled=False,
                reason_code="INVALID_ORDER_STATE",
                message=f"Expected submitted, got {order.status.value}",
            )

        self._audit.record(
            event_type="SIM_ORDER_ACCEPTED",
            entity_type="order",
            entity_id=order.id,
            details={"broker_order_id": order.broker_order_id, "simulated": True},
        )

        market_price = self._market.get_price(order.symbol)
        decision = evaluate_fill(order, market_price)
        if not decision.eligible or decision.fill_price is None:
            return PaperExecutionResult(
                filled=False,
                reason_code=decision.reason_code or "NOT_FILLED",
                message=decision.message or "Order not filled",
            )

        broker_execution_id = f"sim_exec_{uuid.uuid4()}"
        execution = Execution(
            order_id=order.id,
            broker_execution_id=broker_execution_id,
            quantity=order.quantity,
            price=decision.fill_price,
            commission=Decimal("0"),
            executed_at=datetime.now(UTC),
            realized_pnl=Decimal("0"),
            accounting_applied=False,
        )
        self._session.add(execution)
        self._session.flush()

        proposal = self._session.get(TradeProposal, order.trade_proposal_id)
        strategy_id = proposal.strategy_id if proposal else None
        accounting = self._accounting.apply_execution(
            execution,
            order=order,
            strategy_id=strategy_id,
            mark_price=decision.fill_price,
        )

        self._cash.apply_fill(
            order.broker_account_id,
            side=order.side.value,
            quantity=order.quantity,
            price=decision.fill_price,
            commission=execution.commission or Decimal("0"),
        )

        assert_order_transition(order.status, OrderStatus.FILLED)
        order.status = OrderStatus.FILLED
        self._session.flush()

        self._audit.record(
            event_type="SIM_ORDER_FILLED",
            entity_type="order",
            entity_id=order.id,
            details={
                "broker_execution_id": broker_execution_id,
                "fill_price": str(decision.fill_price),
                "quantity": str(order.quantity),
                "realized_pnl": str(accounting.realized_pnl),
                "simulated": True,
            },
        )

        return PaperExecutionResult(
            filled=True,
            message="Simulated order filled",
            broker_execution_id=broker_execution_id,
            execution_id=str(execution.id),
            fill_price=decision.fill_price,
            realized_pnl=accounting.realized_pnl,
            details={"accounting_event": accounting.event},
        )
