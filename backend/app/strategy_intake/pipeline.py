"""Intake review pipeline — metadata/static review only.

Does NOT clone repositories.
Does NOT execute external GitHub code.
Prepares the framework for a future milestone that reviews one specific repo.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.strategy_intake.classification import classify_repository, decide_integration
from app.strategy_intake.license_review import review_license
from app.strategy_intake.manifest import RepositoryManifest, create_manifest
from app.strategy_intake.models import (
    ExternalRepositoryIntake,
    IntegrationDecision,
    ManifestStatus,
    SourceSnippet,
)
from app.strategy_intake.review_report import RepoReviewReport, build_review_report
from app.strategy_intake.security_review import review_sources


class IntakeReviewResult(BaseModel):
    intake: ExternalRepositoryIntake
    classification: list[str] = Field(default_factory=list)
    license_kind: str | None = None
    license_flags: list[str] = Field(default_factory=list)
    security_finding_count: int = 0
    broker_isolation_required: bool = True
    decision: IntegrationDecision
    report: RepoReviewReport
    draft_manifest: RepositoryManifest
    external_code_executed: bool = False

    def to_serializable_dict(self) -> dict:
        return self.model_dump(mode="json")


def review_repository_intake(
    intake: ExternalRepositoryIntake,
    *,
    source_snippets: list[SourceSnippet] | None = None,
    purpose: str | None = None,
    maintenance_status: str | None = None,
) -> IntakeReviewResult:
    """Run license/security/classification/decision without executing code."""
    license_result = review_license(intake.license)
    security = review_sources(list(source_snippets or []))
    classification = classify_repository(intake)
    decision = decide_integration(
        intake,
        classification=classification,
        license_review=license_result,
        security=security,
    )
    report = build_review_report(
        intake,
        classification=classification,
        license_review=license_result,
        security=security,
        decision=decision,
        purpose=purpose,
        maintenance_status=maintenance_status,
    )

    status = ManifestStatus.REVIEWING
    if decision.recommendation.value == "reject":
        status = ManifestStatus.REJECTED
    elif not license_result.adaptation_allowed:
        status = ManifestStatus.REJECTED

    draft = create_manifest(
        repository=intake.repository_url,
        revision=None,  # must be pinned before approval
        license=intake.license,
        classification=classification.classifications,
        integration_mode=decision.recommendation,
        approved_files=[],
        rejected_files=[],
        dependencies=list(intake.dependency_files),
        security_findings=list(security.findings),
        status=status,
        risk_level=decision.risk_level,
        notes=[
            "Draft manifest from intake review — commit pin required before approval.",
            "EXTERNAL GITHUB CODE IS NEVER TRUSTED BY DEFAULT.",
        ],
    )

    return IntakeReviewResult(
        intake=intake,
        classification=[c.value for c in classification.classifications],
        license_kind=license_result.license_kind.value,
        license_flags=[f.value for f in license_result.flags],
        security_finding_count=len(security.findings),
        broker_isolation_required=decision.broker_isolation_required
        or security.broker_order_submission_detected
        or security.requires_isolation,
        decision=decision,
        report=report,
        draft_manifest=draft,
        external_code_executed=False,
    )
