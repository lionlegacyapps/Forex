"""GitHub Strategy Intake & Adapter Framework V1.

EXTERNAL GITHUB CODE IS NEVER TRUSTED BY DEFAULT.

Pipeline:
  GitHub Repo → Intake Review → License → Dependencies → Security →
  Architecture Classification → Algorithm Extraction / Safe Wrapper →
  Internal Strategy Adapter → Strategy Registry → Backtest → QA → Paper

Never:
  GitHub Repo → execute directly → Broker

V1 does not clone repositories and does not execute external code.
"""

from app.strategy_intake.adapter import (
    FORBIDDEN_ADAPTER_DEPENDENCIES,
    ExternalStrategyAdapter,
    IntakeRegistrationGate,
)
from app.strategy_intake.classification import classify_repository, decide_integration
from app.strategy_intake.errors import (
    AdapterGateError,
    IntakeError,
    LicenseReviewError,
    ManifestError,
    SecurityReviewError,
)
from app.strategy_intake.examples import ThresholdMomentumAdapter
from app.strategy_intake.gated_registry import GatedStrategyRegistry
from app.strategy_intake.harness import HarnessResult, run_adapter_harness
from app.strategy_intake.license_review import classify_license, review_license
from app.strategy_intake.manifest import (
    RepositoryManifest,
    assert_ready_for_adaptation,
    create_manifest,
)
from app.strategy_intake.models import (
    ClassificationResult,
    ExternalRepositoryIntake,
    IntegrationDecision,
    IntegrationRecommendation,
    LicenseFlag,
    LicenseKind,
    LicenseReviewResult,
    ManifestStatus,
    RepoClassification,
    RiskLevel,
    SecurityFinding,
    SecurityFindingSeverity,
    SecurityReviewResult,
    SourceSnippet,
)
from app.strategy_intake.pipeline import IntakeReviewResult, review_repository_intake
from app.strategy_intake.review_report import RepoReviewReport, build_review_report
from app.strategy_intake.sandbox import SANDBOX_REQUIREMENTS, SandboxBoundarySpec
from app.strategy_intake.security_review import review_sources

__all__ = [
    "FORBIDDEN_ADAPTER_DEPENDENCIES",
    "AdapterGateError",
    "ClassificationResult",
    "ExternalRepositoryIntake",
    "ExternalStrategyAdapter",
    "GatedStrategyRegistry",
    "HarnessResult",
    "IntakeError",
    "IntakeRegistrationGate",
    "IntakeReviewResult",
    "IntegrationDecision",
    "IntegrationRecommendation",
    "LicenseFlag",
    "LicenseKind",
    "LicenseReviewError",
    "LicenseReviewResult",
    "ManifestError",
    "ManifestStatus",
    "RepoClassification",
    "RepoReviewReport",
    "RepositoryManifest",
    "RiskLevel",
    "SANDBOX_REQUIREMENTS",
    "SandboxBoundarySpec",
    "SecurityFinding",
    "SecurityFindingSeverity",
    "SecurityReviewError",
    "SecurityReviewResult",
    "SourceSnippet",
    "ThresholdMomentumAdapter",
    "assert_ready_for_adaptation",
    "build_review_report",
    "classify_license",
    "classify_repository",
    "create_manifest",
    "decide_integration",
    "review_license",
    "review_repository_intake",
    "review_sources",
    "run_adapter_harness",
]
