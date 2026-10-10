"""First-party example adapters for framework tests only.

These are NOT imported external GitHub strategies.
No external repository code executes here.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.models.enums import AssetClass, OrderType
from app.strategies.context import StrategyContext
from app.strategies.decision import DecisionAction, StrategyDecision, no_action
from app.strategies.errors import StrategyParameterError
from app.strategy_intake.adapter import ExternalStrategyAdapter
from app.strategy_intake.manifest import RepositoryManifest


class ThresholdMomentumAdapter(ExternalStrategyAdapter):
    """Tiny deterministic algorithm wrapped as ExternalStrategyAdapter.

    Simulates an 'extracted' algorithm: enter long when last close >
    simple mean of prior closes by threshold; exit when below.
    """

    def __init__(self, manifest: RepositoryManifest) -> None:
        super().__init__(manifest)

    @property
    def strategy_id(self) -> str:
        return "threshold_momentum_adapted"

    @property
    def name(self) -> str:
        return "Threshold Momentum (Adapted Example)"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def supported_asset_classes(self) -> frozenset[AssetClass]:
        return frozenset({AssetClass.EQUITY})

    @property
    def required_timeframes(self) -> frozenset[str]:
        return frozenset({"1Day"})

    def default_parameters(self) -> dict[str, Any]:
        return {"lookback": 3, "threshold": "0.02", "quantity": "1"}

    def _validate_parameters(self, parameters: dict[str, Any]) -> None:
        lookback = int(parameters["lookback"])
        if lookback < 2:
            raise StrategyParameterError("lookback must be >= 2", code="invalid_lookback")
        Decimal(str(parameters["threshold"]))
        if Decimal(str(parameters["quantity"])) <= 0:
            raise StrategyParameterError("quantity must be positive", code="invalid_quantity")

    def map_context(self, context: StrategyContext) -> dict[str, Any]:
        params = self.validate_parameters(context.parameters or {})
        closes = [float(c) for c in context.closes]
        return {
            "closes": closes,
            "lookback": int(params["lookback"]),
            "threshold": float(params["threshold"]),
            "quantity": str(params["quantity"]),
            "symbol": context.symbol,
            "asset_class": context.asset_class,
            "position_qty": str(context.position.quantity if context.position else 0),
        }

    def run_algorithm(self, algorithm_input: dict[str, Any]) -> dict[str, Any]:
        closes = algorithm_input["closes"]
        lookback = algorithm_input["lookback"]
        threshold = algorithm_input["threshold"]
        if len(closes) < lookback + 1:
            return {"signal": "none"}
        window = closes[-(lookback + 1) : -1]
        mean = sum(window) / len(window)
        last = closes[-1]
        edge = (last - mean) / mean if mean else 0.0
        pos = Decimal(str(algorithm_input["position_qty"]))
        if pos == 0 and edge > threshold:
            return {"signal": "enter_long", "edge": edge}
        if pos > 0 and edge < -threshold:
            return {"signal": "exit_long", "edge": edge}
        return {"signal": "none", "edge": edge}

    def to_decision(
        self,
        algorithm_output: dict[str, Any],
        context: StrategyContext,
    ) -> StrategyDecision:
        signal = algorithm_output.get("signal")
        params = self.validate_parameters(context.parameters or {})
        qty = Decimal(str(params["quantity"]))
        meta = {"edge": algorithm_output.get("edge"), "source": "threshold_momentum_adapted"}
        if signal == "enter_long":
            return StrategyDecision(
                action=DecisionAction.ENTER_LONG,
                symbol=context.symbol,
                asset_class=context.asset_class,
                quantity=qty,
                order_type=OrderType.MARKET,
                rationale_code="threshold_enter_long",
                signal_metadata=meta,
            )
        if signal == "exit_long":
            return StrategyDecision(
                action=DecisionAction.EXIT_LONG,
                symbol=context.symbol,
                asset_class=context.asset_class,
                quantity=abs(context.position.quantity) if context.position else qty,
                order_type=OrderType.MARKET,
                rationale_code="threshold_exit_long",
                signal_metadata=meta,
            )
        return no_action(rationale_code="threshold_none")
