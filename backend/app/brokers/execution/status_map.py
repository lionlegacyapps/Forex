"""Alpaca → internal OrderStatus mapping (provider-independent lifecycle).

Conceptual lifecycle terms → existing schema ``OrderStatus``:

| Conceptual           | Internal OrderStatus   | Alpaca examples                          |
|----------------------|------------------------|------------------------------------------|
| pending / submitted  | SUBMITTED              | new, pending_new                         |
| accepted             | SUBMITTED              | accepted, accepted_for_bidding           |
| cancel_pending       | SUBMITTED              | pending_cancel (still open until broker) |
| partially_filled     | PARTIALLY_FILLED       | partially_filled                         |
| filled               | FILLED                 | filled                                   |
| cancelled            | CANCELLED              | canceled, cancelled, replaced            |
| rejected             | REJECTED               | rejected                                 |
| expired              | EXPIRED                | expired                                  |

Schema has no separate ``accepted`` / ``cancel_pending`` columns — those map to
SUBMITTED until the broker reports a terminal or fill state.

ALL EXTERNAL EXECUTION REMAINS ALPACA PAPER ONLY.
"""

from __future__ import annotations

from app.models.enums import OrderStatus

_ALPACA_STATUS_MAP: dict[str, OrderStatus] = {
    "new": OrderStatus.SUBMITTED,
    "accepted": OrderStatus.SUBMITTED,
    "pending_new": OrderStatus.SUBMITTED,
    "accepted_for_bidding": OrderStatus.SUBMITTED,
    "pending_replace": OrderStatus.SUBMITTED,
    "pending_cancel": OrderStatus.SUBMITTED,  # conceptual cancel_pending
    "partially_filled": OrderStatus.PARTIALLY_FILLED,
    "filled": OrderStatus.FILLED,
    "canceled": OrderStatus.CANCELLED,
    "cancelled": OrderStatus.CANCELLED,
    "expired": OrderStatus.EXPIRED,
    "rejected": OrderStatus.REJECTED,
    "suspended": OrderStatus.SUBMITTED,
    "calculated": OrderStatus.SUBMITTED,
    "done_for_day": OrderStatus.SUBMITTED,
    "replaced": OrderStatus.CANCELLED,
}

TERMINAL_STATUSES: frozenset[OrderStatus] = frozenset(
    {
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.REJECTED,
        OrderStatus.EXPIRED,
    }
)

CANCELLABLE_STATUSES: frozenset[OrderStatus] = frozenset(
    {
        OrderStatus.NEW,
        OrderStatus.SUBMITTED,
        OrderStatus.PARTIALLY_FILLED,
    }
)


def map_alpaca_order_status(raw: str) -> OrderStatus:
    key = (raw or "").strip().lower()
    if key not in _ALPACA_STATUS_MAP:
        # Unknown broker status — do not invent a terminal state
        return OrderStatus.SUBMITTED
    return _ALPACA_STATUS_MAP[key]


def is_terminal_status(status: OrderStatus) -> bool:
    return status in TERMINAL_STATUSES


def is_cancellable_status(status: OrderStatus) -> bool:
    return status in CANCELLABLE_STATUSES


def conceptual_label(status: OrderStatus, *, alpaca_raw: str | None = None) -> str:
    """Human-readable lifecycle label for docs/audit."""
    raw = (alpaca_raw or "").lower()
    if raw == "pending_cancel":
        return "cancel_pending"
    if raw in {"accepted", "accepted_for_bidding"}:
        return "accepted"
    if raw in {"new", "pending_new"}:
        return "pending"
    return status.value
