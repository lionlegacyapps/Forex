"""Backtest Execution Model V1 — deterministic fill rules.

ASSUMPTIONS (document clearly; do not pretend perfect execution):

1. Strategy signal is generated at bar **close** (using bars up to and
   including the current bar only — no lookahead).
2. **Market** orders fill at the **next** bar's **open**, with optional
   adverse slippage.
3. **Limit** orders fill only if a *subsequent* bar's range crosses the
   limit price. Buy limit fills when ``low <= limit``; sell limit when
   ``high >= limit``. Fill price is the limit (± slippage).
4. **Stop** orders trigger only if a subsequent bar's range crosses the
   stop. Buy stop when ``high >= stop``; sell stop when ``low <= stop``.
   Fill at stop (± slippage) for V1 simplicity.
5. Same-bar future information (intra-bar after signal) is never used
   for fills of orders generated at that bar's close.
6. Backtests never route to Alpaca or any external broker.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from app.backtesting.costs import BacktestCostModel
from app.market_data.models import Bar
from app.models.enums import OrderType, TradeSide
from app.strategies.decision import DecisionAction, StrategyDecision


class FillReason(StrEnum):
    MARKET_NEXT_OPEN = "market_next_open"
    LIMIT_TOUCHED = "limit_touched"
    STOP_TRIGGERED = "stop_triggered"


@dataclass(frozen=True)
class PendingOrder:
    decision: StrategyDecision
    signal_time: datetime
    signal_bar_index: int
    quantity: Decimal
    created_at_bar_index: int


@dataclass(frozen=True)
class SimulatedFill:
    symbol: str
    side: TradeSide
    quantity: Decimal
    price: Decimal
    fill_time: datetime
    fill_bar_index: int
    commission: Decimal
    slippage_component: Decimal
    reason: FillReason
    decision_action: DecisionAction
    rationale_code: str | None


class BacktestExecutionModel:
    """Apply V1 deterministic fill rules."""

    def __init__(self, costs: BacktestCostModel | None = None) -> None:
        self.costs = costs or BacktestCostModel()

    def try_fill(
        self,
        order: PendingOrder,
        bar: Bar,
        bar_index: int,
    ) -> SimulatedFill | None:
        # Never fill on the signal bar (no same-bar lookahead).
        if bar_index <= order.created_at_bar_index:
            return None

        decision = order.decision
        assert decision.side is not None
        assert decision.symbol is not None
        side = decision.side
        qty = order.quantity

        if decision.order_type == OrderType.MARKET:
            raw = bar.open
            reason = FillReason.MARKET_NEXT_OPEN
        elif decision.order_type == OrderType.LIMIT:
            if decision.limit_price is None:
                return None
            if side == TradeSide.BUY and bar.low <= decision.limit_price:
                raw = decision.limit_price
                reason = FillReason.LIMIT_TOUCHED
            elif side == TradeSide.SELL and bar.high >= decision.limit_price:
                raw = decision.limit_price
                reason = FillReason.LIMIT_TOUCHED
            else:
                return None
        elif decision.order_type == OrderType.STOP:
            if decision.stop_price is None:
                return None
            if side == TradeSide.BUY and bar.high >= decision.stop_price:
                raw = decision.stop_price
                reason = FillReason.STOP_TRIGGERED
            elif side == TradeSide.SELL and bar.low <= decision.stop_price:
                raw = decision.stop_price
                reason = FillReason.STOP_TRIGGERED
            else:
                return None
        else:
            # STOP_LIMIT simplified: require stop trigger then fill at limit if touched
            if decision.stop_price is None or decision.limit_price is None:
                return None
            triggered = (
                (side == TradeSide.BUY and bar.high >= decision.stop_price)
                or (side == TradeSide.SELL and bar.low <= decision.stop_price)
            )
            if not triggered:
                return None
            if side == TradeSide.BUY and bar.low <= decision.limit_price:
                raw = decision.limit_price
                reason = FillReason.LIMIT_TOUCHED
            elif side == TradeSide.SELL and bar.high >= decision.limit_price:
                raw = decision.limit_price
                reason = FillReason.LIMIT_TOUCHED
            else:
                return None

        slipped = self.costs.apply_slippage(raw, side=side.value)
        slippage_component = abs(slipped - raw) * qty
        commission = self.costs.commission(qty)
        return SimulatedFill(
            symbol=decision.symbol,
            side=side,
            quantity=qty,
            price=slipped,
            fill_time=bar.timestamp,
            fill_bar_index=bar_index,
            commission=commission,
            slippage_component=slippage_component,
            reason=reason,
            decision_action=decision.action,
            rationale_code=decision.rationale_code,
        )
