"""Internal repository manifest — version-pinned review record.

Approved strategy logic must pin an exact commit SHA or version.
Tracking latest/main/master for production strategy logic is forbidden.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.strategy_intake.errors import ManifestError
from app.strategy_intake.models import (
    IntegrationRecommendation,
    ManifestStatus,
    RepoClassification,
    RiskLevel,
    SecurityFinding,
)

_FLOATING_REFS = frozenset({"latest", "main", "master", "HEAD", "head"})
_SHA_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
_SHORT_SHA_RE = re.compile(r"^[0-9a-f]{7,39}$", re.IGNORECASE)


class RepositoryManifest(BaseModel):
    repository: str
    revision: str | None = None  # exact commit SHA preferred
    version_tag: str | None = None  # optional annotated tag accompanying SHA
    license: str | None = None
    classification: list[RepoClassification] = Field(default_factory=list)
    integration_mode: IntegrationRecommendation | None = None
    approved_files: list[str] = Field(default_factory=list)
    rejected_files: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    security_findings: list[SecurityFinding] = Field(default_factory=list)
    adapter_name: str | None = None
    status: ManifestStatus = ManifestStatus.CANDIDATE
    risk_level: RiskLevel = RiskLevel.HIGH
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("repository")
    @classmethod
    def _repo(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("repository must be non-empty")
        return value.strip()

    @model_validator(mode="after")
    def _pin_rules(self) -> RepositoryManifest:
        if self.revision is not None:
            rev = self.revision.strip()
            if rev in _FLOATING_REFS:
                raise ValueError(
                    "revision must not be a floating ref (latest/main/master/HEAD)"
                )
            self.revision = rev
        return self

    @property
    def is_commit_pinned(self) -> bool:
        if not self.revision:
            return False
        return bool(_SHA_RE.match(self.revision) or _SHORT_SHA_RE.match(self.revision))

    @property
    def is_approvable(self) -> bool:
        return self.status in {
            ManifestStatus.APPROVED_FOR_ADAPTATION,
            ManifestStatus.INTEGRATED,
        }

    def require_commit_pin(self) -> None:
        if not self.is_commit_pinned:
            raise ManifestError(
                "Approved/integrated manifests require an exact commit SHA pin "
                "(not latest/main/master)",
                code="commit_pin_required",
            )

    def to_serializable_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def create_manifest(
    *,
    repository: str,
    revision: str | None = None,
    version_tag: str | None = None,
    license: str | None = None,
    classification: list[RepoClassification] | None = None,
    integration_mode: IntegrationRecommendation | None = None,
    approved_files: list[str] | None = None,
    rejected_files: list[str] | None = None,
    dependencies: list[str] | None = None,
    security_findings: list[SecurityFinding] | None = None,
    adapter_name: str | None = None,
    status: ManifestStatus = ManifestStatus.CANDIDATE,
    risk_level: RiskLevel = RiskLevel.HIGH,
    notes: list[str] | None = None,
) -> RepositoryManifest:
    return RepositoryManifest(
        repository=repository,
        revision=revision,
        version_tag=version_tag,
        license=license,
        classification=list(classification or []),
        integration_mode=integration_mode,
        approved_files=list(approved_files or []),
        rejected_files=list(rejected_files or []),
        dependencies=list(dependencies or []),
        security_findings=list(security_findings or []),
        adapter_name=adapter_name,
        status=status,
        risk_level=risk_level,
        notes=list(notes or []),
    )


def assert_ready_for_adaptation(manifest: RepositoryManifest) -> None:
    if manifest.status == ManifestStatus.REJECTED:
        raise ManifestError(
            "Rejected repository cannot become an active strategy",
            code="rejected_manifest",
        )
    if manifest.status == ManifestStatus.RETIRED:
        raise ManifestError(
            "Retired repository cannot become an active strategy",
            code="retired_manifest",
        )
    if not manifest.is_approvable:
        raise ManifestError(
            f"Manifest status {manifest.status} is not approved for adaptation",
            code="not_approved",
        )
    manifest.require_commit_pin()
    if manifest.integration_mode == IntegrationRecommendation.REJECT:
        raise ManifestError(
            "Integration mode REJECT cannot be adapted",
            code="reject_mode",
        )
