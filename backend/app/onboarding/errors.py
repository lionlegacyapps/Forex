"""Paper pilot onboarding errors — fail closed."""

from __future__ import annotations


class OnboardingError(Exception):
    def __init__(self, message: str, *, code: str = "onboarding_error") -> None:
        super().__init__(message)
        self.code = code


class OnboardingBlockedError(OnboardingError):
    def __init__(self, message: str, *, code: str = "onboarding_blocked") -> None:
        super().__init__(message, code=code)
