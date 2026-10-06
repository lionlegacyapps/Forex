"""Deterministic fill eligibility for simulated order types."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import OrderType, TradeSide
from app.models.order import Order


class FillDecision(BaseModel):
    eligible: bool
    fill_price: Decimal | None = None
    reason_code: str | None = None
    message: str = ""


def evaluate_fill(order: Order, market_price: Decimal | None) -> FillDecision:
    """Return whether ``order`` may fill at ``market_price``.

    No slip, depth, or randomness. Full quantity only when eligible.
    """
    if market_price is None:
        return FillDecision(
            eligible=False,
            reason_code="PRICE_UNAVAILABLE",
            message="No deterministic simulation price configured",
        )

    side = order.side
    otype = order.order_type

    if otype == OrderType.MARKET:
        return FillDecision(
            eligible=True,
            fill_price=market_price,
            message="Market order fills at simulation price",
        )

    if otype == OrderType.LIMIT:
        if order.limit_price is None:
            return FillDecision(
                eligible=False,
                reason_code="LIMIT_PRICE_REQUIRED",
                message="Limit order missing limit_price",
            )
        if side == TradeSide.BUY and market_price <= order.limit_price:
            return FillDecision(eligible=True, fill_price=market_price)
        if side == TradeSide.SELL and market_price >= order.limit_price:
            return FillDecision(eligible=True, fill_price=market_price)
        return FillDecision(
            eligible=False,
            reason_code="LIMIT_NOT_MARKETABLE",
            message="Limit order not marketable at simulation price",
        )

    if otype == OrderType.STOP:
        if order.stop_price is None:
            return FillDecision(
                eligible=False,
                reason_code="STOP_PRICE_REQUIRED",
                message="Stop order missing stop_price",
            )
        triggered = (
            market_price >= order.stop_price
            if side == TradeSide.BUY
            else market_price <= order.stop_price
        )
        if not triggered:
            return FillDecision(
                eligible=False,
                reason_code="STOP_NOT_TRIGGERED",
                message="Stop not triggered at simulation price",
            )
        return FillDecision(eligible=True, fill_price=market_price)

    if otype == OrderType.STOP_LIMIT:
        if order.stop_price is None or order.limit_price is None:
            return FillDecision(
                eligible=False,
                reason_code="STOP_LIMIT_PRICES_REQUIRED",
                message="Stop-limit requires stop_price and limit_price",
            )
        triggered = (
            market_price >= order.stop_price
            if side == TradeSide.BUY
            else market_price <= order.stop_price
        )
        if not triggered:
            return FillDecision(
                eligible=False,
                reason_code="STOP_NOT_TRIGGERED",
                message="Stop-limit stop not triggered",
            )
        # After trigger, limit must be marketable.
        if side == TradeSide.BUY and market_price <= order.limit_price:
            return FillDecision(eligible=True, fill_price=market_price)
        if side == TradeSide.SELL and market_price >= order.limit_price:
            return FillDecision(eligible=True, fill_price=market_price)
        return FillDecision(
            eligible=False,
            reason_code="STOP_LIMIT_NOT_MARKETABLE",
            message="Stop triggered but limit not marketable",
        )

    return FillDecision(
        eligible=False,
        reason_code="UNSUPPORTED_ORDER_TYPE",
        message=f"Unsupported order type {otype}",
    )
