"""GitHub strategy intake errors."""

from __future__ import annotations


class IntakeError(Exception):
    def __init__(self, message: str, *, code: str = "intake_error") -> None:
        super().__init__(message)
        self.code = code


class LicenseReviewError(IntakeError):
    """License review failed or blocked adaptation."""


class SecurityReviewError(IntakeError):
    """Security review failed or blocked adaptation."""


class ManifestError(IntakeError):
    """Invalid or incomplete repository manifest."""


class AdapterGateError(IntakeError):
    """Adapter/registry gate rejected untrusted or unapproved material."""
