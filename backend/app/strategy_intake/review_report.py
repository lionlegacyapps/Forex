"""Reusable repository review report format."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.strategy_intake.models import (
    ClassificationResult,
    ExternalRepositoryIntake,
    IntegrationDecision,
    LicenseReviewResult,
    RiskLevel,
    SecurityReviewResult,
)


class RepoReviewReport(BaseModel):
    repository: str
    purpose: str | None = None
    license: str | None = None
    maintenance_status: str | None = None
    architecture: list[str] = Field(default_factory=list)
    useful_components: list[str] = Field(default_factory=list)
    broker_coupling: str | None = None
    security_findings: list[str] = Field(default_factory=list)
    dependency_cost: str | None = None
    integration_recommendation: str | None = None
    integration_method: str | None = None
    risk_level: RiskLevel = RiskLevel.HIGH
    notes: list[str] = Field(default_factory=list)

    def to_serializable_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def build_review_report(
    intake: ExternalRepositoryIntake,
    *,
    classification: ClassificationResult,
    license_review: LicenseReviewResult,
    security: SecurityReviewResult,
    decision: IntegrationDecision,
    purpose: str | None = None,
    maintenance_status: str | None = None,
    useful_components: list[str] | None = None,
    dependency_cost: str | None = None,
) -> RepoReviewReport:
    broker = "none detected"
    if security.broker_order_submission_detected or intake.broker_integrations:
        broker = "direct broker order path detected — isolation required; do not reuse"

    findings = [
        f"[{f.severity}] {f.rule_id}: {f.message}" + (f" ({f.path}:{f.line})" if f.path else "")
        for f in security.findings
    ]
    findings.extend(intake.security_warnings)

    return RepoReviewReport(
        repository=intake.repository_url,
        purpose=purpose,
        license=license_review.raw_license or intake.license,
        maintenance_status=maintenance_status,
        architecture=[c.value for c in classification.classifications],
        useful_components=list(useful_components or intake.strategy_files),
        broker_coupling=broker,
        security_findings=findings,
        dependency_cost=dependency_cost
        or (
            f"{len(intake.dependency_files)} dependency file(s); "
            "prefer extracting small algorithms over large frameworks"
        ),
        integration_recommendation=decision.recommendation.value,
        integration_method=decision.preferred_method,
        risk_level=decision.risk_level,
        notes=list(decision.reasons)
        + [
            "EXTERNAL GITHUB CODE IS NEVER TRUSTED BY DEFAULT.",
            "Static scanning does not prove safety.",
        ],
    )
