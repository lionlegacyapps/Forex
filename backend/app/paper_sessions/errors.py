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
    def __init__(
        self,
        message: str = (
            "PAPER_EXECUTE is disabled; set PAPER_SESSION_EXECUTE_ENABLED=true "
            "and grant session-scoped consent"
        ),
    ) -> None:
        super().__init__(message, code="paper_execute_disabled")


class ConsentError(PaperSessionError):
    def __init__(self, message: str, *, code: str = "consent_error") -> None:
        super().__init__(message, code=code)


class ConcurrentSessionError(PaperSessionError):
    def __init__(self, message: str = "concurrent session conflict") -> None:
        super().__init__(message, code="concurrent_session")


class LeaseError(PaperSessionError):
    def __init__(self, message: str = "worker lease conflict") -> None:
        super().__init__(message, code="lease_conflict")


class UncertainOrderAcknowledgmentError(PaperSessionError):
    def __init__(self, message: str, *, code: str = "uncertain_order_ack") -> None:
        super().__init__(message, code=code)
