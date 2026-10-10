"""Walk-forward evaluation errors."""

from __future__ import annotations


class WalkForwardError(Exception):
    def __init__(self, message: str, *, code: str = "walk_forward_error") -> None:
        super().__init__(message)
        self.code = code


class InvalidSplitError(WalkForwardError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="invalid_split")


class InsufficientHistoryError(WalkForwardError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="insufficient_history")


class DataLeakageError(WalkForwardError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="data_leakage")


class UnsupportedStrategyError(WalkForwardError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="unsupported_strategy")
