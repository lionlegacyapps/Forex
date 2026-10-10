"""Convert FinRL-X inspired policy evaluation into StrategyDecision.

Configurable thresholds. Supports NO_ACTION.
Never places broker orders. Never auto paper-trades.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.models.enums import AssetClass, OrderType
from app.research.models import ResearchOutput
from app.research.rl.finrlx_intake import finrlx_approved_adaptation_manifest
from app.strategies.context import StrategyContext
from app.strategies.decision import DecisionAction, StrategyDecision, no_action
from app.strategies.errors import StrategyParameterError
from app.strategy_intake.adapter import ExternalStrategyAdapter
from app.strategy_intake.manifest import RepositoryManifest


class FinRLXBaselineSignalAdapter(ExternalStrategyAdapter):
    """Maps evaluation scores (+1 buy / -1 sell / 0 hold) to StrategyDecision."""

    def __init__(
        self,
        manifest: RepositoryManifest | None = None,
        *,
        research_output: ResearchOutput | None = None,
    ) -> None:
        super().__init__(manifest or finrlx_approved_adaptation_manifest())
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
        return "finrlx_baseline_signal"

    @property
    def name(self) -> str:
        return "FinRL-X Inspired Baseline Signal (Research Demo)"

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
            "buy_score": "1",
            "sell_score": "-1",
            "quantity": "1",
        }

    def _validate_parameters(self, parameters: dict[str, Any]) -> None:
        try:
            Decimal(str(parameters.get("buy_score", "1")))
            Decimal(str(parameters.get("sell_score", "-1")))
            qty = Decimal(str(parameters["quantity"]))
        except Exception as exc:
            raise StrategyParameterError("invalid parameters", code="invalid_params") from exc
        if qty <= 0:
            raise StrategyParameterError("quantity must be positive", code="invalid_quantity")

    def map_context(self, context: StrategyContext) -> dict[str, Any]:
        params = self.validate_parameters(context.parameters or {})
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
            "buy_score": str(params["buy_score"]),
            "sell_score": str(params["sell_score"]),
            "quantity": str(params["quantity"]),
            "symbol": context.symbol,
            "asset_class": context.asset_class,
            "position_qty": str(context.position.quantity if context.position else 0),
        }

    def run_algorithm(self, algorithm_input: dict[str, Any]) -> dict[str, Any]:
        if algorithm_input["score"] is None:
            return {"signal": "none", "reason": "no_prediction"}
        score = Decimal(algorithm_input["score"])
        buy = Decimal(algorithm_input["buy_score"])
        sell = Decimal(algorithm_input["sell_score"])
        pos = Decimal(algorithm_input["position_qty"])
        if pos == 0 and score >= buy:
            return {"signal": "enter_long", "score": str(score)}
        if pos > 0 and score <= sell:
            return {"signal": "exit_long", "score": str(score)}
        return {"signal": "none", "score": str(score), "reason": "hold"}

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
            "auto_trade": False,
            "trained_rl": False,
        }
        if signal == "enter_long":
            return StrategyDecision(
                action=DecisionAction.ENTER_LONG,
                symbol=context.symbol,
                asset_class=context.asset_class,
                quantity=qty,
                order_type=OrderType.MARKET,
                rationale_code="finrlx_baseline_enter_long",
                signal_metadata=meta,
            )
        if signal == "exit_long":
            return StrategyDecision(
                action=DecisionAction.EXIT_LONG,
                symbol=context.symbol,
                asset_class=context.asset_class,
                quantity=abs(context.position.quantity) if context.position else qty,
                order_type=OrderType.MARKET,
                rationale_code="finrlx_baseline_exit_long",
                signal_metadata=meta,
            )
        return no_action(rationale_code=algorithm_output.get("reason") or "finrlx_no_action")
