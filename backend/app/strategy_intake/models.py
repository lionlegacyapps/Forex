"""Typed models for external repository intake evaluation.

EXTERNAL GITHUB CODE IS NEVER TRUSTED BY DEFAULT.
Fields are optional when unknown — incomplete metadata is not approval.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class RepoClassification(StrEnum):
    STRATEGY_ALGORITHM = "strategy_algorithm"
    BACKTESTING_LIBRARY = "backtesting_library"
    INDICATOR_LIBRARY = "indicator_library"
    PORTFOLIO_RISK_LIBRARY = "portfolio_risk_library"
    MARKET_DATA_TOOL = "market_data_tool"
    EXECUTION_BROKER_TOOL = "execution_broker_tool"
    ML_AI_RESEARCH = "ml_ai_research"
    FULL_TRADING_BOT = "full_trading_bot"
    REFERENCE_ONLY = "reference_only"
    UNKNOWN = "unknown"


class IntegrationRecommendation(StrEnum):
    ADAPT_ALGORITHM = "adapt_algorithm"
    WRAP_LIBRARY = "wrap_library"
    USE_AS_DEPENDENCY = "use_as_dependency"
    REFERENCE_ONLY = "reference_only"
    REJECT = "reject"


class LicenseKind(StrEnum):
    MIT = "mit"
    APACHE_2_0 = "apache-2.0"
    BSD = "bsd"
    GPL = "gpl"
    AGPL = "agpl"
    LGPL = "lgpl"
    MPL = "mpl"
    PROPRIETARY_CUSTOM = "proprietary_custom"
    NO_LICENSE = "no_license"
    UNKNOWN = "unknown"


class LicenseFlag(StrEnum):
    NO_LICENSE = "NO_LICENSE"
    UNKNOWN_LICENSE = "UNKNOWN_LICENSE"
    COPYLEFT_REVIEW_REQUIRED = "COPYLEFT_REVIEW_REQUIRED"
    AGPL_REVIEW_REQUIRED = "AGPL_REVIEW_REQUIRED"
    PERMISSIVE_OK = "PERMISSIVE_OK"
    CUSTOM_REVIEW_REQUIRED = "CUSTOM_REVIEW_REQUIRED"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ManifestStatus(StrEnum):
    CANDIDATE = "candidate"
    REVIEWING = "reviewing"
    APPROVED_FOR_ADAPTATION = "approved_for_adaptation"
    REJECTED = "rejected"
    INTEGRATED = "integrated"
    RETIRED = "retired"


class SecurityFindingSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    HIGH = "high"
    CRITICAL = "critical"


class SecurityFinding(BaseModel):
    rule_id: str
    message: str
    severity: SecurityFindingSeverity
    path: str | None = None
    line: int | None = None
    evidence: str | None = None


class LicenseReviewResult(BaseModel):
    license_kind: LicenseKind
    raw_license: str | None = None
    flags: list[LicenseFlag] = Field(default_factory=list)
    adaptation_allowed: bool = False
    notes: list[str] = Field(default_factory=list)


class SecurityReviewResult(BaseModel):
    findings: list[SecurityFinding] = Field(default_factory=list)
    broker_order_submission_detected: bool = False
    network_access_detected: bool = False
    dynamic_execution_detected: bool = False
    requires_isolation: bool = False
    passed_static_gates: bool = False
    disclaimer: str = (
        "Static scanning does not prove safety. Manual review remains required."
    )


class ClassificationResult(BaseModel):
    classifications: list[RepoClassification] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)

    @field_validator("classifications")
    @classmethod
    def _unique(cls, value: list[RepoClassification]) -> list[RepoClassification]:
        seen: list[RepoClassification] = []
        for item in value:
            if item not in seen:
                seen.append(item)
        return seen or [RepoClassification.UNKNOWN]


class IntegrationDecision(BaseModel):
    recommendation: IntegrationRecommendation
    reasons: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.HIGH
    broker_isolation_required: bool = True
    preferred_method: str | None = None


class ExternalRepositoryIntake(BaseModel):
    """Intake metadata for evaluating an external repository.

    Populated by reviewers / operators. Does not clone or execute code.
    """

    repository_url: str
    repository_name: str | None = None
    owner: str | None = None
    license: str | None = None
    last_update: datetime | None = None
    language: str | None = None
    dependency_files: list[str] = Field(default_factory=list)
    strategy_files: list[str] = Field(default_factory=list)
    backtesting_framework: str | None = None
    broker_integrations: list[str] = Field(default_factory=list)
    market_data_integrations: list[str] = Field(default_factory=list)
    ai_ml_components: list[str] = Field(default_factory=list)
    network_access: bool | None = None
    filesystem_access: bool | None = None
    shell_subprocess_usage: bool | None = None
    dynamic_code_execution: bool | None = None
    security_warnings: list[str] = Field(default_factory=list)
    integration_recommendation: IntegrationRecommendation | None = None
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("repository_url")
    @classmethod
    def _non_empty_url(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("repository_url must be non-empty")
        return stripped


class SourceSnippet(BaseModel):
    """In-memory source text for static review (never auto-executed)."""

    path: str
    content: str
