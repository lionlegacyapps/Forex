"""Strategy engine errors."""

from __future__ import annotations


class StrategyError(Exception):
    """Base strategy-engine error."""

    def __init__(self, message: str, *, code: str = "strategy_error") -> None:
        super().__init__(message)
        self.code = code


class StrategyRegistrationError(StrategyError):
    """Invalid or duplicate strategy registration."""


class StrategyParameterError(StrategyError):
    """Strategy parameters failed validation."""


class StrategyDecisionError(StrategyError):
    """Decision is malformed or cannot be adapted."""
