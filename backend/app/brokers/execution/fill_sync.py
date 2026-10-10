"""Apply Alpaca paper fills into internal Execution + PositionAccounting.

Broker-reported fills are authoritative for external paper execution.
Partial fills create separate Execution rows with durable broker IDs.
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
from app.brokers.execution.status_map import (
    conceptual_label,
    is_terminal_status,
    map_alpaca_order_status,
)
from app.models.enums import OrderStatus
from app.models.execution import Execution
from app.models.order import Order
from app.models.trade_proposal import TradeProposal
from app.trading.execution.order_transitions import assert_order_transition, can_order_transition
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


def internal_filled_quantity(session: Session, order_id) -> Decimal:
    rows = session.scalars(select(Execution).where(Execution.order_id == order_id)).all()
    total = Decimal("0")
    for row in rows:
        total += row.quantity
    return total


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
        emit_status_audit: bool = True,
    ) -> dict[str, Any]:
        """Update order status and record any new fills from broker payload/activities.

        When ``fills`` provides durable activity IDs, those are used.
        Otherwise a **delta** aggregate fill is recorded for newly filled qty only
        (avoids double-counting across partial → full transitions).
        """
        if not isinstance(broker_payload, dict):
            return {
                "ok": False,
                "error": "MALFORMED_RESPONSE",
                "mapped_status": order.status.value,
                "fills_recorded": 0,
                "status_changed": False,
                "illegal_transition": False,
            }

        raw_status = str(broker_payload.get("status") or "")
        mapped = map_alpaca_order_status(raw_status)
        filled_qty = _dec(broker_payload.get("filled_qty")) or Decimal("0")
        avg_price = _dec(broker_payload.get("filled_avg_price"))
        prior_status = order.status

        recorded = 0
        fill_rows = list(fills or [])
        if not fill_rows and filled_qty > 0 and avg_price is not None:
            already = internal_filled_quantity(self._session, order.id)
            delta = filled_qty - already
            if delta > 0:
                fill_rows = [
                    {
                        "id": f"alpaca_agg_{order.broker_order_id}_{filled_qty}",
                        "qty": str(delta),
                        "price": str(avg_price),
                        "transaction_time": broker_payload.get("filled_at")
                        or broker_payload.get("updated_at"),
                    }
                ]

        proposal = self._session.get(TradeProposal, order.trade_proposal_id)
        strategy_id = proposal.strategy_id if proposal else None

        for row in fill_rows:
            exec_id = str(row.get("id") or row.get("execution_id") or "").strip()
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
            price = _dec(row.get("price") or row.get("price_per_unit"))
            if qty is None or price is None or qty <= 0:
                continue
            execution = Execution(
                order_id=order.id,
                broker_execution_id=exec_id,
                quantity=qty,
                price=price,
                commission=_dec(row.get("commission")) or Decimal("0"),
                executed_at=_parse_ts(
                    row.get("transaction_time") or row.get("timestamp") or row.get("date")
                ),
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
                event_type=audit_events.ALPACA_FILL_RECORDED,
                entity_type="execution",
                entity_id=execution.id,
                details={
                    "order_id": str(order.id),
                    "broker_execution_id": exec_id,
                    "qty": str(qty),
                    "price": str(price),
                },
            )
            # Keep legacy alias event for prior tests/docs
            self._audit.record(
                event_type=audit_events.ALPACA_PAPER_FILL_RECORDED,
                entity_type="execution",
                entity_id=execution.id,
                details={"broker_execution_id": exec_id, "alias": True},
            )

        illegal_transition = False
        status_changed = False
        if order.status != mapped:
            if can_order_transition(order.status, mapped):
                assert_order_transition(order.status, mapped)
                order.status = mapped
                status_changed = True
                if mapped == OrderStatus.CANCELLED and order.cancelled_at is None:
                    order.cancelled_at = _parse_ts(
                        broker_payload.get("canceled_at")
                        or broker_payload.get("cancelled_at")
                        or broker_payload.get("updated_at")
                    )
            elif is_terminal_status(order.status):
                # Do not move backward from terminal — leave intact
                illegal_transition = True
            elif order.status == OrderStatus.PARTIALLY_FILLED and mapped == OrderStatus.SUBMITTED:
                illegal_transition = True
            else:
                illegal_transition = True

        self._session.flush()

        if status_changed:
            if mapped == OrderStatus.PARTIALLY_FILLED:
                self._audit.record(
                    event_type=audit_events.ALPACA_ORDER_PARTIALLY_FILLED,
                    entity_type="order",
                    entity_id=order.id,
                    details={"filled_qty": str(filled_qty), "raw_status": raw_status},
                )
            elif mapped == OrderStatus.FILLED:
                self._audit.record(
                    event_type=audit_events.ALPACA_ORDER_FILLED,
                    entity_type="order",
                    entity_id=order.id,
                    details={"filled_qty": str(filled_qty), "raw_status": raw_status},
                )
            elif mapped == OrderStatus.CANCELLED:
                self._audit.record(
                    event_type=audit_events.ALPACA_ORDER_CANCELLED,
                    entity_type="order",
                    entity_id=order.id,
                    details={"raw_status": raw_status},
                )
            elif mapped == OrderStatus.REJECTED:
                self._audit.record(
                    event_type=audit_events.ALPACA_ORDER_REJECTED,
                    entity_type="order",
                    entity_id=order.id,
                    details={
                        "raw_status": raw_status,
                        "reason": str(broker_payload.get("reject_reason") or "")[:200],
                    },
                )
            elif mapped == OrderStatus.EXPIRED:
                self._audit.record(
                    event_type=audit_events.ALPACA_ORDER_EXPIRED,
                    entity_type="order",
                    entity_id=order.id,
                    details={"raw_status": raw_status},
                )

        if emit_status_audit and (status_changed or recorded > 0 or illegal_transition):
            self._audit.record(
                event_type=audit_events.ALPACA_ORDER_STATUS_SYNCED,
                entity_type="order",
                entity_id=order.id,
                details={
                    "broker_order_id": order.broker_order_id,
                    "raw_status": raw_status,
                    "conceptual": conceptual_label(mapped, alpaca_raw=raw_status),
                    "prior_status": prior_status.value,
                    "mapped_status": order.status.value,
                    "fills_recorded": recorded,
                    "illegal_transition": illegal_transition,
                },
            )
            self._audit.record(
                event_type=audit_events.ALPACA_PAPER_ORDER_STATUS_SYNCED,
                entity_type="order",
                entity_id=order.id,
                details={"alias": True, "mapped_status": order.status.value},
            )

        return {
            "ok": True,
            "mapped_status": order.status.value,
            "prior_status": prior_status.value,
            "fills_recorded": recorded,
            "filled_qty": str(filled_qty),
            "internal_filled_qty": str(internal_filled_quantity(self._session, order.id)),
            "status_changed": status_changed,
            "illegal_transition": illegal_transition,
            "terminal": is_terminal_status(order.status),
        }
