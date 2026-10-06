"""Explicit Order status transitions for paper execution."""

from __future__ import annotations

from app.core.exceptions import TradingPipelineError
from app.models.enums import OrderStatus
from app.trading.risk.codes import INVALID_STATE_TRANSITION

# V1 schema vocabulary (no separate "accepted" value).
# Conceptual "accepted" maps to SUBMITTED after broker accept.
ALLOWED_ORDER_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.NEW: frozenset(
        {OrderStatus.SUBMITTED, OrderStatus.REJECTED, OrderStatus.CANCELLED}
    ),
    OrderStatus.SUBMITTED: frozenset(
        {
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        }
    ),
    OrderStatus.PARTIALLY_FILLED: frozenset(
        {
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.EXPIRED,
        }
    ),
    OrderStatus.FILLED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
    OrderStatus.REJECTED: frozenset(),
    OrderStatus.EXPIRED: frozenset(),
}


def assert_order_transition(current: OrderStatus, target: OrderStatus) -> None:
    allowed = ALLOWED_ORDER_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise TradingPipelineError(
            f"Illegal order status transition: {current.value} → {target.value}",
            code=INVALID_STATE_TRANSITION,
        )


def can_order_transition(current: OrderStatus, target: OrderStatus) -> bool:
    return target in ALLOWED_ORDER_TRANSITIONS.get(current, frozenset())
