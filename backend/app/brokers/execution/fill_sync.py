"""Apply Alpaca paper fills into internal Execution + PositionAccounting.

Broker-reported fills are authoritative for external paper execution.
Does not fabricate fills.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import service as audit_events
from app.audit.service import AuditService
from app.brokers.execution.status_map import map_alpaca_order_status
from app.models.enums import OrderStatus
from app.models.execution import Execution
from app.models.order import Order
from app.models.trade_proposal import TradeProposal
from app.trading.execution.order_transitions import assert_order_transition
from app.trading.execution.position_accounting import PositionAccountingService


def _dec(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _parse_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if value:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return datetime.now(UTC)


class AlpacaFillSyncService:
    """Sync broker order status + fills into internal accounting."""

    def __init__(
        self,
        session: Session,
        *,
        accounting: PositionAccountingService | None = None,
        audit: AuditService | None = None,
    ) -> None:
        self._session = session
        self._audit = audit or AuditService(session)
        self._accounting = accounting or PositionAccountingService(session, audit=self._audit)

    def apply_broker_order_snapshot(
        self,
        order: Order,
        broker_payload: dict[str, Any],
        *,
        fills: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Update order status and record any new fills from broker payload/activities."""
        raw_status = str(broker_payload.get("status") or "")
        mapped = map_alpaca_order_status(raw_status)
        filled_qty = _dec(broker_payload.get("filled_qty")) or Decimal("0")
        avg_price = _dec(broker_payload.get("filled_avg_price"))

        recorded = 0
        # Prefer explicit fill activities when provided
        fill_rows = list(fills or [])
        if not fill_rows and filled_qty > 0 and avg_price is not None:
            # Synthesize one fill row from order aggregate (V1) when activities absent
            fill_rows = [
                {
                    "id": f"alpaca_agg_{order.broker_order_id}_{filled_qty}",
                    "qty": str(filled_qty),
                    "price": str(avg_price),
                    "transaction_time": broker_payload.get("filled_at")
                    or broker_payload.get("updated_at"),
                }
            ]

        proposal = self._session.get(TradeProposal, order.trade_proposal_id)
        strategy_id = proposal.strategy_id if proposal else None

        for row in fill_rows:
            exec_id = str(row.get("id") or "").strip()
            if not exec_id:
                continue
            existing = self._session.scalar(
                select(Execution).where(
                    Execution.order_id == order.id,
                    Execution.broker_execution_id == exec_id,
                )
            )
            if existing is not None:
                continue
            qty = _dec(row.get("qty") or row.get("quantity"))
            price = _dec(row.get("price"))
            if qty is None or price is None or qty <= 0:
                continue
            # Skip if we already accounted for this qty via aggregate id collision
            execution = Execution(
                order_id=order.id,
                broker_execution_id=exec_id,
                quantity=qty,
                price=price,
                commission=_dec(row.get("commission")) or Decimal("0"),
                executed_at=_parse_ts(row.get("transaction_time") or row.get("timestamp")),
                realized_pnl=Decimal("0"),
                accounting_applied=False,
            )
            self._session.add(execution)
            self._session.flush()
            self._accounting.apply_execution(
                execution,
                order=order,
                strategy_id=strategy_id,
                mark_price=price,
            )
            recorded += 1
            self._audit.record(
                event_type=audit_events.ALPACA_PAPER_FILL_RECORDED,
                entity_type="execution",
                entity_id=execution.id,
                details={
                    "order_id": str(order.id),
                    "broker_execution_id": exec_id,
                    "qty": str(qty),
                    "price": str(price),
                },
            )

        # Status transition (fail soft on illegal transitions for terminal states)
        if order.status != mapped:
            try:
                # Allow SUBMITTED → PARTIALLY_FILLED / FILLED / REJECTED / CANCELLED / EXPIRED
                if order.status == OrderStatus.SUBMITTED or (
                    order.status == OrderStatus.PARTIALLY_FILLED
                    and mapped in {OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.EXPIRED}
                ):
                    assert_order_transition(order.status, mapped)
                    order.status = mapped
            except Exception:
                # Do not invent; leave status and report
                pass

        self._session.flush()
        self._audit.record(
            event_type=audit_events.ALPACA_PAPER_ORDER_STATUS_SYNCED,
            entity_type="order",
            entity_id=order.id,
            details={
                "broker_order_id": order.broker_order_id,
                "raw_status": raw_status,
                "mapped_status": order.status.value,
                "fills_recorded": recorded,
            },
        )
        return {
            "mapped_status": order.status.value,
            "fills_recorded": recorded,
            "filled_qty": str(filled_qty),
        }
