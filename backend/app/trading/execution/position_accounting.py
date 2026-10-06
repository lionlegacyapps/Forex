"""Position accounting from executions — Decimal only, strategy-aware.

SIMULATION RESULTS DO NOT REPRESENT REAL MARKET EXECUTION.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import service as audit_events
from app.audit.service import AuditService
from app.models.enums import AssetClass, PositionStatus, TradeSide
from app.models.execution import Execution
from app.models.order import Order
from app.models.position import Position
from app.models.trade_proposal import TradeProposal


@dataclass
class AccountingResult:
    applied: bool
    already_applied: bool = False
    realized_pnl: Decimal = Decimal("0")
    position_id: uuid.UUID | None = None
    event: str | None = None
    message: str = ""


class PositionAccountingService:
    """Apply fills to positions with weighted averages, PnL, and reversals."""

    def __init__(self, session: Session, *, audit: AuditService | None = None) -> None:
        self._session = session
        self._audit = audit or AuditService(session)

    def apply_execution(
        self,
        execution: Execution,
        *,
        order: Order,
        strategy_id: uuid.UUID | None,
        mark_price: Decimal | None = None,
    ) -> AccountingResult:
        """Apply one execution idempotently (``accounting_applied`` flag)."""
        if execution.accounting_applied:
            return AccountingResult(
                applied=False,
                already_applied=True,
                realized_pnl=execution.realized_pnl,
                message="Execution already applied; no position change",
            )

        signed_qty = (
            execution.quantity
            if order.side == TradeSide.BUY
            else -execution.quantity
        )
        commission = execution.commission or Decimal("0")
        position = self._find_open_position(
            broker_account_id=order.broker_account_id,
            strategy_id=strategy_id,
            symbol=order.symbol,
            asset_class=order.asset_class,
        )

        realized = Decimal("0")
        event = "POSITION_OPENED"

        if position is None:
            position = Position(
                broker_account_id=order.broker_account_id,
                strategy_id=strategy_id,
                symbol=order.symbol,
                asset_class=order.asset_class,
                quantity=signed_qty,
                average_entry_price=execution.price,
                current_price=mark_price,
                realized_pnl=Decimal("0"),
                unrealized_pnl=Decimal("0"),
                status=PositionStatus.OPEN,
                opened_at=datetime.now(UTC),
            )
            self._session.add(position)
            self._session.flush()
            event = "POSITION_OPENED"
            realized = -commission
        else:
            realized, event = self._apply_to_existing(
                position=position,
                signed_qty=signed_qty,
                fill_price=execution.price,
                commission=commission,
            )
            if mark_price is not None:
                position.current_price = mark_price
                self._refresh_unrealized(position)
            elif position.status == PositionStatus.OPEN:
                position.current_price = None
                position.unrealized_pnl = Decimal("0")

        execution.realized_pnl = realized
        execution.accounting_applied = True
        self._session.flush()

        self._audit.record(
            event_type=event,
            entity_type="position",
            entity_id=position.id,
            details={
                "execution_id": str(execution.id),
                "broker_execution_id": execution.broker_execution_id,
                "symbol": order.symbol,
                "signed_qty_delta": str(signed_qty),
                "fill_price": str(execution.price),
                "realized_pnl": str(realized),
                "position_qty": str(position.quantity),
                "position_status": position.status.value,
            },
        )
        self._audit.record(
            event_type=audit_events.EXECUTION_RECORDED,
            entity_type="execution",
            entity_id=execution.id,
            details={
                "order_id": str(order.id),
                "quantity": str(execution.quantity),
                "price": str(execution.price),
                "realized_pnl": str(realized),
            },
        )
        return AccountingResult(
            applied=True,
            realized_pnl=realized,
            position_id=position.id,
            event=event,
            message="Execution applied to position",
        )

    def _find_open_position(
        self,
        *,
        broker_account_id: uuid.UUID,
        strategy_id: uuid.UUID | None,
        symbol: str,
        asset_class: AssetClass,
    ) -> Position | None:
        stmt = select(Position).where(
            Position.broker_account_id == broker_account_id,
            Position.symbol == symbol,
            Position.asset_class == asset_class,
            Position.status == PositionStatus.OPEN,
        )
        if strategy_id is None:
            stmt = stmt.where(Position.strategy_id.is_(None))
        else:
            stmt = stmt.where(Position.strategy_id == strategy_id)
        return self._session.scalars(stmt).first()

    def _apply_to_existing(
        self,
        *,
        position: Position,
        signed_qty: Decimal,
        fill_price: Decimal,
        commission: Decimal,
    ) -> tuple[Decimal, str]:
        old_qty = position.quantity
        new_qty = old_qty + signed_qty

        # Same direction increase
        if old_qty > 0 and signed_qty > 0:
            position.average_entry_price = (
                old_qty * position.average_entry_price + signed_qty * fill_price
            ) / new_qty
            position.quantity = new_qty
            return -commission, "POSITION_INCREASED"

        if old_qty < 0 and signed_qty < 0:
            abs_old = abs(old_qty)
            abs_add = abs(signed_qty)
            position.average_entry_price = (
                abs_old * position.average_entry_price + abs_add * fill_price
            ) / (abs_old + abs_add)
            position.quantity = new_qty
            return -commission, "POSITION_INCREASED"

        # Reduce / close / reverse
        if old_qty > 0 and signed_qty < 0:
            return self._reduce_or_reverse_long(
                position, signed_qty=signed_qty, fill_price=fill_price, commission=commission
            )
        if old_qty < 0 and signed_qty > 0:
            return self._reduce_or_reverse_short(
                position, signed_qty=signed_qty, fill_price=fill_price, commission=commission
            )

        # Should not reach (zero old qty is invalid for open)
        position.quantity = new_qty
        position.average_entry_price = fill_price
        return -commission, "POSITION_OPENED"

    def _reduce_or_reverse_long(
        self,
        position: Position,
        *,
        signed_qty: Decimal,
        fill_price: Decimal,
        commission: Decimal,
    ) -> tuple[Decimal, str]:
        sell_qty = abs(signed_qty)
        old_qty = position.quantity
        if sell_qty < old_qty:
            realized = (fill_price - position.average_entry_price) * sell_qty - commission
            position.quantity = old_qty - sell_qty
            position.realized_pnl += realized
            return realized, "POSITION_REDUCED"
        if sell_qty == old_qty:
            realized = (fill_price - position.average_entry_price) * sell_qty - commission
            position.quantity = Decimal("0")
            position.realized_pnl += realized
            position.status = PositionStatus.CLOSED
            position.closed_at = datetime.now(UTC)
            position.unrealized_pnl = Decimal("0")
            return realized, "POSITION_CLOSED"
        # Reversal: close long, open short
        closed = old_qty
        realized = (fill_price - position.average_entry_price) * closed - commission
        short_qty = sell_qty - closed
        position.realized_pnl += realized
        position.quantity = -short_qty
        position.average_entry_price = fill_price
        position.status = PositionStatus.OPEN
        position.closed_at = None
        return realized, "POSITION_REVERSED"

    def _reduce_or_reverse_short(
        self,
        position: Position,
        *,
        signed_qty: Decimal,
        fill_price: Decimal,
        commission: Decimal,
    ) -> tuple[Decimal, str]:
        buy_qty = signed_qty
        old_abs = abs(position.quantity)
        if buy_qty < old_abs:
            realized = (position.average_entry_price - fill_price) * buy_qty - commission
            position.quantity = position.quantity + buy_qty
            position.realized_pnl += realized
            return realized, "POSITION_REDUCED"
        if buy_qty == old_abs:
            realized = (position.average_entry_price - fill_price) * buy_qty - commission
            position.quantity = Decimal("0")
            position.realized_pnl += realized
            position.status = PositionStatus.CLOSED
            position.closed_at = datetime.now(UTC)
            position.unrealized_pnl = Decimal("0")
            return realized, "POSITION_CLOSED"
        # Reversal: close short, open long
        closed = old_abs
        realized = (position.average_entry_price - fill_price) * closed - commission
        long_qty = buy_qty - closed
        position.realized_pnl += realized
        position.quantity = long_qty
        position.average_entry_price = fill_price
        position.status = PositionStatus.OPEN
        position.closed_at = None
        return realized, "POSITION_REVERSED"

    @staticmethod
    def _refresh_unrealized(position: Position) -> None:
        if position.status != PositionStatus.OPEN or position.current_price is None:
            position.unrealized_pnl = Decimal("0")
            return
        if position.quantity > 0:
            position.unrealized_pnl = (
                position.current_price - position.average_entry_price
            ) * position.quantity
        else:
            position.unrealized_pnl = (
                position.average_entry_price - position.current_price
            ) * abs(position.quantity)

    def mark_position(
        self,
        position: Position,
        mark_price: Decimal | None,
    ) -> Decimal | None:
        """Update mark / unrealized. Returns unrealized or None if unknown."""
        if mark_price is None:
            position.current_price = None
            position.unrealized_pnl = Decimal("0")
            return None
        position.current_price = mark_price
        self._refresh_unrealized(position)
        return position.unrealized_pnl

    def strategy_id_for_order(self, order: Order) -> uuid.UUID | None:
        proposal = self._session.get(TradeProposal, order.trade_proposal_id)
        return proposal.strategy_id if proposal else None
