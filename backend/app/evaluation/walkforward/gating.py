"""Strategy wrapper that blocks actionable decisions before score_start.

Warm-up bars remain visible for indicators; no positions open during warm-up.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models.enums import AssetClass
from app.strategies.context import StrategyContext
from app.strategies.decision import StrategyDecision, no_action
from app.strategies.protocol import Strategy


class ScoreWindowGateStrategy(Strategy):
    """Delegate to an inner strategy only during the scored window."""

    def __init__(
        self,
        inner: Strategy,
        *,
        score_start: datetime,
        score_end: datetime,
    ) -> None:
        self._inner = inner
        self._score_start = score_start
        self._score_end = score_end

    @property
    def strategy_id(self) -> str:
        return self._inner.strategy_id

    @property
    def name(self) -> str:
        return self._inner.name

    @property
    def version(self) -> str:
        return self._inner.version

    @property
    def supported_asset_classes(self) -> frozenset[AssetClass]:
        return self._inner.supported_asset_classes

    @property
    def required_timeframes(self) -> frozenset[str]:
        return self._inner.required_timeframes

    def default_parameters(self) -> dict[str, Any]:
        return self._inner.default_parameters()

    def validate_parameters(self, parameters: dict[str, Any]) -> dict[str, Any]:
        return self._inner.validate_parameters(parameters)

    def evaluate(self, context: StrategyContext) -> StrategyDecision:
        ts = context.timestamp
        if ts < self._score_start or ts >= self._score_end:
            return no_action()
        return self._inner.evaluate(context)
