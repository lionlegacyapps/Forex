"""Paper Strategy Qualification Gate V1 (approval ≠ execution)."""

from app.qualification.auth import AuthenticatedOwner, resolve_authenticated_owner
from app.qualification.criteria import POLICY_VERSION, QualificationCriteria
from app.qualification.eligibility import EligibilityCheckResult, PaperEligibilityService
from app.qualification.errors import (
    ConcurrentStateError,
    HardBlockerError,
    IllegalTransitionError,
    QualificationError,
    UnauthorizedApprovalError,
)
from app.qualification.evidence import evidence_fingerprint, review_walk_forward_evidence
from app.qualification.report import QualificationReport
from app.qualification.service import PaperQualificationService
from app.qualification.states import (
    ApprovalScope,
    QualificationRecommendation,
    QualificationState,
)

__all__ = [
    "ApprovalScope",
    "AuthenticatedOwner",
    "ConcurrentStateError",
    "EligibilityCheckResult",
    "HardBlockerError",
    "IllegalTransitionError",
    "POLICY_VERSION",
    "PaperEligibilityService",
    "PaperQualificationService",
    "QualificationCriteria",
    "QualificationError",
    "QualificationRecommendation",
    "QualificationReport",
    "QualificationState",
    "UnauthorizedApprovalError",
    "evidence_fingerprint",
    "resolve_authenticated_owner",
    "review_walk_forward_evidence",
]
