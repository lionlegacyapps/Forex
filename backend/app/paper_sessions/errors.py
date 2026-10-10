"""Paper session runner errors."""

from __future__ import annotations


class PaperSessionError(Exception):
    def __init__(self, message: str, *, code: str = "paper_session_error") -> None:
        super().__init__(message)
        self.code = code


class IllegalSessionTransitionError(PaperSessionError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="illegal_session_transition")


class ActivationRejectedError(PaperSessionError):
    def __init__(self, message: str, *, code: str = "activation_rejected") -> None:
        super().__init__(message, code=code)


class PaperExecuteDisabledError(PaperSessionError):
    def __init__(self) -> None:
        super().__init__(
            "PAPER_EXECUTE mode is disabled in Controlled Paper Session Runner V1",
            code="paper_execute_disabled",
        )


class ConcurrentSessionError(PaperSessionError):
    def __init__(self, message: str = "concurrent session conflict") -> None:
        super().__init__(message, code="concurrent_session")


class LeaseError(PaperSessionError):
    def __init__(self, message: str = "worker lease conflict") -> None:
        super().__init__(message, code="lease_conflict")
