"""Paper qualification errors."""

from __future__ import annotations


class QualificationError(Exception):
    def __init__(self, message: str, *, code: str = "qualification_error") -> None:
        super().__init__(message)
        self.code = code


class IllegalTransitionError(QualificationError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="illegal_transition")


class UnauthorizedApprovalError(QualificationError):
    def __init__(self, message: str = "unauthorized approval") -> None:
        super().__init__(message, code="unauthorized")


class HardBlockerError(QualificationError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="hard_blocker")


class ConcurrentStateError(QualificationError):
    def __init__(self, message: str = "concurrent state conflict") -> None:
        super().__init__(message, code="concurrent_conflict")


class StaleApprovalError(QualificationError):
    def __init__(self, message: str = "stale approval cannot be reused") -> None:
        super().__init__(message, code="stale_approval")
