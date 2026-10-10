"""Backtesting errors."""

from __future__ import annotations


class BacktestError(Exception):
    def __init__(self, message: str, *, code: str = "backtest_error") -> None:
        super().__init__(message)
        self.code = code


class HistoricalDataError(BacktestError):
    """Invalid or missing historical market data."""


class LookaheadError(BacktestError):
    """Attempt to access future information during simulation."""
