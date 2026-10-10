"""Risk Engine decision and check result models."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class CheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_EVALUATED = "not_evaluated"
    NOT_EVALUATED_MARKET_PRICE_REQUIRED = "not_evaluated_market_price_required"


class RiskCheckResult(BaseModel):
    name: str
    status: CheckStatus
    reason_code: str | None = None
    message: str = ""


class RiskDecision(BaseModel):
    """Structured Risk Engine output. Fail-closed: approved only when all
    critical checks pass and no unexpected error occurred.
    """

    approved: bool
    reason_code: str | None = None
    message: str = ""
    checks: list[RiskCheckResult] = Field(default_factory=list)

    @classmethod
    def reject(
        cls,
        *,
        reason_code: str,
        message: str,
        checks: list[RiskCheckResult] | None = None,
    ) -> RiskDecision:
        return cls(
            approved=False,
            reason_code=reason_code,
            message=message,
            checks=list(checks or []),
        )

    @classmethod
    def approve(
        cls,
        *,
        message: str = "Risk checks passed",
        checks: list[RiskCheckResult] | None = None,
    ) -> RiskDecision:
        return cls(approved=True, reason_code=None, message=message, checks=list(checks or []))
