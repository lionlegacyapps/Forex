"""Convert approved research predictions into StrategyDecision.

Configurable thresholds. Supports NO_ACTION.
Never places broker orders. Never auto-promotes strategies.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.models.enums import AssetClass, OrderType
from app.research.models import ResearchOutput, ResearchPrediction
from app.research.qlib_intake import qlib_approved_adaptation_manifest
from app.strategies.context import StrategyContext
from app.strategies.decision import DecisionAction, StrategyDecision, no_action
from app.strategies.errors import StrategyParameterError
from app.strategy_intake.adapter import ExternalStrategyAdapter
from app.strategy_intake.manifest import RepositoryManifest


class QlibFactorSignalAdapter(ExternalStrategyAdapter):
    """Demonstration adapter: research score → StrategyDecision.

    Predictions may be injected via context.parameters['research_predictions']
    (timestamp ISO → score) for backtests, or via ``bind_research_output``.
    """

    def __init__(
        self,
        manifest: RepositoryManifest | None = None,
        *,
        research_output: ResearchOutput | None = None,
    ) -> None:
        super().__init__(manifest or qlib_approved_adaptation_manifest())
        self._bound_output = research_output
        self._score_by_ts: dict[str, Decimal] = {}
        if research_output is not None:
            self.bind_research_output(research_output)

    def bind_research_output(self, output: ResearchOutput) -> None:
        self._bound_output = output
        self._score_by_ts = {
            p.prediction_timestamp.isoformat(): p.score for p in output.predictions
        }

    @property
    def strategy_id(self) -> str:
        return "qlib_factor_signal"

    @property
    def name(self) -> str:
        return "Qlib-Inspired Factor Signal (Research Demo)"

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
        return {
            "entry_threshold": "0.02",
            "exit_threshold": "-0.01",
            "quantity": "1",
            "allow_short": False,
        }

    def _validate_parameters(self, parameters: dict[str, Any]) -> None:
        try:
            Decimal(str(parameters["entry_threshold"]))
            Decimal(str(parameters["exit_threshold"]))
            qty = Decimal(str(parameters["quantity"]))
        except Exception as exc:
            raise StrategyParameterError(
                "entry_threshold, exit_threshold, quantity must be decimals",
                code="invalid_params",
            ) from exc
        if qty <= 0:
            raise StrategyParameterError("quantity must be positive", code="invalid_quantity")
        if not isinstance(parameters.get("allow_short", False), bool):
            raise StrategyParameterError("allow_short must be bool", code="invalid_allow_short")

    def map_context(self, context: StrategyContext) -> dict[str, Any]:
        params = self.validate_parameters(context.parameters or {})
        # Allow per-context prediction map override for harness/backtests
        pred_map = params.get("research_predictions") or {}
        ts_key = context.timestamp.isoformat()
        score = None
        if ts_key in self._score_by_ts:
            score = self._score_by_ts[ts_key]
        elif ts_key in pred_map:
            score = Decimal(str(pred_map[ts_key]))
        elif "research_score" in params:
            score = Decimal(str(params["research_score"]))
        return {
            "score": None if score is None else str(score),
            "entry_threshold": str(params["entry_threshold"]),
            "exit_threshold": str(params["exit_threshold"]),
            "quantity": str(params["quantity"]),
            "allow_short": bool(params["allow_short"]),
            "symbol": context.symbol,
            "asset_class": context.asset_class,
            "position_qty": str(context.position.quantity if context.position else 0),
            "timestamp": ts_key,
        }

    def run_algorithm(self, algorithm_input: dict[str, Any]) -> dict[str, Any]:
        if algorithm_input["score"] is None:
            return {"signal": "none", "reason": "no_prediction"}
        score = Decimal(algorithm_input["score"])
        entry = Decimal(algorithm_input["entry_threshold"])
        exit_th = Decimal(algorithm_input["exit_threshold"])
        pos = Decimal(algorithm_input["position_qty"])
        allow_short = algorithm_input["allow_short"]

        if pos == 0 and score >= entry:
            return {"signal": "enter_long", "score": str(score)}
        if pos > 0 and score <= exit_th:
            return {"signal": "exit_long", "score": str(score)}
        if pos == 0 and allow_short and score <= -entry:
            return {"signal": "enter_short", "score": str(score)}
        if pos < 0 and score >= -exit_th:
            return {"signal": "exit_short", "score": str(score)}
        return {"signal": "none", "score": str(score), "reason": "below_threshold"}

    def to_decision(
        self,
        algorithm_output: dict[str, Any],
        context: StrategyContext,
    ) -> StrategyDecision:
        params = self.validate_parameters(context.parameters or {})
        qty = Decimal(str(params["quantity"]))
        signal = algorithm_output.get("signal")
        meta = {
            "research_score": algorithm_output.get("score"),
            "source_repository": (
                self._bound_output.source_repository if self._bound_output else None
            ),
            "pinned_commit": self._bound_output.pinned_commit if self._bound_output else None,
            "research_model_id": (
                self._bound_output.research_model_id if self._bound_output else None
            ),
            "auto_trade": False,
        }
        if signal == "enter_long":
            return StrategyDecision(
                action=DecisionAction.ENTER_LONG,
                symbol=context.symbol,
                asset_class=context.asset_class,
                quantity=qty,
                order_type=OrderType.MARKET,
                rationale_code="qlib_factor_enter_long",
                signal_metadata=meta,
            )
        if signal == "exit_long":
            return StrategyDecision(
                action=DecisionAction.EXIT_LONG,
                symbol=context.symbol,
                asset_class=context.asset_class,
                quantity=abs(context.position.quantity) if context.position else qty,
                order_type=OrderType.MARKET,
                rationale_code="qlib_factor_exit_long",
                signal_metadata=meta,
            )
        if signal == "enter_short":
            return StrategyDecision(
                action=DecisionAction.ENTER_SHORT,
                symbol=context.symbol,
                asset_class=context.asset_class,
                quantity=qty,
                order_type=OrderType.MARKET,
                rationale_code="qlib_factor_enter_short",
                signal_metadata=meta,
            )
        if signal == "exit_short":
            return StrategyDecision(
                action=DecisionAction.EXIT_SHORT,
                symbol=context.symbol,
                asset_class=context.asset_class,
                quantity=abs(context.position.quantity) if context.position else qty,
                order_type=OrderType.MARKET,
                rationale_code="qlib_factor_exit_short",
                signal_metadata=meta,
            )
        return no_action(
            rationale_code=algorithm_output.get("reason") or "qlib_factor_no_action"
        )


def prediction_map_from_output(output: ResearchOutput) -> dict[str, str]:
    """Helper for injecting scores into backtest parameters."""
    return {p.prediction_timestamp.isoformat(): str(p.score) for p in output.predictions}
