"""Map Alpaca order statuses → internal OrderStatus values."""

from __future__ import annotations

from app.models.enums import OrderStatus

# Alpaca → internal
_ALPACA_STATUS_MAP: dict[str, OrderStatus] = {
    "new": OrderStatus.SUBMITTED,
    "accepted": OrderStatus.SUBMITTED,
    "pending_new": OrderStatus.SUBMITTED,
    "accepted_for_bidding": OrderStatus.SUBMITTED,
    "pending_replace": OrderStatus.SUBMITTED,
    "pending_cancel": OrderStatus.SUBMITTED,
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


def map_alpaca_order_status(raw: str) -> OrderStatus:
    key = (raw or "").strip().lower()
    if key not in _ALPACA_STATUS_MAP:
        # Unknown broker status — keep as submitted (do not invent)
        return OrderStatus.SUBMITTED
    return _ALPACA_STATUS_MAP[key]
