"""Deterministic SMA crossover reference strategy (test/framework only).

NOT A PROFITABILITY CLAIM. Used to prove Strategy Engine + Backtest wiring.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.models.enums import AssetClass, OrderType
from app.strategies.context import StrategyContext
from app.strategies.decision import DecisionAction, StrategyDecision, no_action
from app.strategies.errors import StrategyParameterError
from app.strategies.protocol import Strategy


class SMACrossoverStrategy(Strategy):
    """Enter long when fast SMA crosses above slow SMA; exit when opposite.

    Short entries are supported when ``allow_short`` is true.
    """

    def __init__(self) -> None:
        pass

    @property
    def strategy_id(self) -> str:
        return "sma_crossover"

    @property
    def name(self) -> str:
        return "SMA Crossover (Reference)"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def supported_asset_classes(self) -> frozenset[AssetClass]:
        return frozenset({AssetClass.EQUITY, AssetClass.CRYPTO, AssetClass.FOREX})

    @property
    def required_timeframes(self) -> frozenset[str]:
        return frozenset({"1Day"})

    def default_parameters(self) -> dict[str, Any]:
        return {
            "fast_period": 3,
            "slow_period": 5,
            "allow_short": False,
            "quantity": "1",
        }

    def _validate_parameters(self, parameters: dict[str, Any]) -> None:
        try:
            fast = int(parameters["fast_period"])
            slow = int(parameters["slow_period"])
        except (KeyError, TypeError, ValueError) as exc:
            raise StrategyParameterError(
                "fast_period and slow_period must be integers",
                code="invalid_periods",
            ) from exc
        if fast < 1 or slow < 1:
            raise StrategyParameterError(
                "periods must be >= 1",
                code="invalid_periods",
            )
        if fast >= slow:
            raise StrategyParameterError(
                "fast_period must be < slow_period",
                code="invalid_period_order",
            )
        try:
            qty = Decimal(str(parameters.get("quantity", "1")))
        except Exception as exc:
            raise StrategyParameterError(
                "quantity must be a positive decimal",
                code="invalid_quantity",
            ) from exc
        if qty <= 0:
            raise StrategyParameterError(
                "quantity must be positive",
                code="invalid_quantity",
            )
        if not isinstance(parameters.get("allow_short", False), bool):
            raise StrategyParameterError(
                "allow_short must be a boolean",
                code="invalid_allow_short",
            )

    def evaluate(self, context: StrategyContext) -> StrategyDecision:
        params = context.parameters or self.default_parameters()
        # Re-validate if caller supplied raw params
        params = self.validate_parameters(params)
        fast_n = int(params["fast_period"])
        slow_n = int(params["slow_period"])
        allow_short = bool(params["allow_short"])
        quantity = Decimal(str(params["quantity"]))

        closes = context.closes
        if len(closes) < slow_n + 1:
            return no_action(rationale_code="insufficient_bars")

        fast_now = _sma(closes, fast_n)
        slow_now = _sma(closes, slow_n)
        fast_prev = _sma(closes[:-1], fast_n)
        slow_prev = _sma(closes[:-1], slow_n)

        crossed_up = fast_prev <= slow_prev and fast_now > slow_now
        crossed_down = fast_prev >= slow_prev and fast_now < slow_now

        pos = context.position
        is_long = pos is not None and pos.is_long
        is_short = pos is not None and pos.is_short
        is_flat = pos is None or pos.is_flat

        meta = {
            "fast_sma": str(fast_now),
            "slow_sma": str(slow_now),
            "fast_sma_prev": str(fast_prev),
            "slow_sma_prev": str(slow_prev),
        }

        if crossed_up:
            if is_short:
                return StrategyDecision(
                    action=DecisionAction.EXIT_SHORT,
                    symbol=context.symbol,
                    asset_class=context.asset_class,
                    quantity=abs(pos.quantity) if pos else quantity,
                    order_type=OrderType.MARKET,
                    rationale_code="sma_cross_up_exit_short",
                    rationale="Fast SMA crossed above slow SMA; exit short",
                    signal_metadata=meta,
                )
            if is_flat:
                return StrategyDecision(
                    action=DecisionAction.ENTER_LONG,
                    symbol=context.symbol,
                    asset_class=context.asset_class,
                    quantity=quantity,
                    order_type=OrderType.MARKET,
                    rationale_code="sma_cross_up_enter_long",
                    rationale="Fast SMA crossed above slow SMA; enter long",
                    signal_metadata=meta,
                )
            return no_action(rationale_code="already_long", rationale="Already long")

        if crossed_down:
            if is_long:
                return StrategyDecision(
                    action=DecisionAction.EXIT_LONG,
                    symbol=context.symbol,
                    asset_class=context.asset_class,
                    quantity=abs(pos.quantity) if pos else quantity,
                    order_type=OrderType.MARKET,
                    rationale_code="sma_cross_down_exit_long",
                    rationale="Fast SMA crossed below slow SMA; exit long",
                    signal_metadata=meta,
                )
            if is_flat and allow_short:
                return StrategyDecision(
                    action=DecisionAction.ENTER_SHORT,
                    symbol=context.symbol,
                    asset_class=context.asset_class,
                    quantity=quantity,
                    order_type=OrderType.MARKET,
                    rationale_code="sma_cross_down_enter_short",
                    rationale="Fast SMA crossed below slow SMA; enter short",
                    signal_metadata=meta,
                )
            return no_action(
                rationale_code="cross_down_no_entry",
                rationale="Cross down without short entry enabled or nothing to exit",
            )

        return no_action(rationale_code="no_crossover")


def _sma(closes: list[Decimal], period: int) -> Decimal:
    window = closes[-period:]
    if len(window) < period:
        raise StrategyParameterError("insufficient closes for SMA", code="insufficient_bars")
    return sum(window, Decimal("0")) / Decimal(period)
