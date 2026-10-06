"""Standardized Strategy interface.

Strategies evaluate market context and emit StrategyDecision only.
They must never receive BrokerExecutionAdapter, BrokerRouter write access,
Alpaca trading clients, or raw credentials.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.models.enums import AssetClass
from app.strategies.context import StrategyContext
from app.strategies.decision import StrategyDecision
from app.strategies.errors import StrategyParameterError


class Strategy(ABC):
    """Base contract for all registered strategies."""

    @property
    @abstractmethod
    def strategy_id(self) -> str:
        """Stable identifier (e.g. 'sma_crossover')."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name."""

    @property
    @abstractmethod
    def version(self) -> str:
        """Semver-like strategy implementation version."""

    @property
    @abstractmethod
    def supported_asset_classes(self) -> frozenset[AssetClass]:
        ...

    @property
    @abstractmethod
    def required_timeframes(self) -> frozenset[str]:
        """Timeframes the strategy expects bars for (e.g. {'1Day'})."""

    def default_parameters(self) -> dict[str, Any]:
        """Typed/configurable defaults; override in subclasses."""
        return {}

    def validate_parameters(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """Validate and normalize parameters. Raises StrategyParameterError."""
        defaults = self.default_parameters()
        merged = {**defaults, **parameters}
        self._validate_parameters(merged)
        return merged

    def _validate_parameters(self, parameters: dict[str, Any]) -> None:
        """Subclass hook for parameter rules."""
        _ = parameters

    @abstractmethod
    def evaluate(self, context: StrategyContext) -> StrategyDecision:
        """Produce a decision from lookahead-safe context.

        Must not call brokers, place orders, or access future market data.
        """


def assert_strategy_metadata(strategy: Strategy) -> None:
    """Validate required metadata fields on a strategy instance."""
    if not strategy.strategy_id or not strategy.strategy_id.strip():
        raise StrategyParameterError("strategy_id must be non-empty", code="missing_strategy_id")
    if not strategy.name or not strategy.name.strip():
        raise StrategyParameterError("name must be non-empty", code="missing_name")
    if not strategy.version or not strategy.version.strip():
        raise StrategyParameterError("version must be non-empty", code="missing_version")
    if not strategy.supported_asset_classes:
        raise StrategyParameterError(
            "supported_asset_classes must be non-empty",
            code="missing_asset_classes",
        )
    if not strategy.required_timeframes:
        raise StrategyParameterError(
            "required_timeframes must be non-empty",
            code="missing_timeframes",
        )
