"""Paper qualification state machine — legal transitions only."""

from __future__ import annotations

from app.models.enums import ApprovalScope, QualificationState
from app.qualification.errors import IllegalTransitionError

# Re-export for callers
__all__ = [
    "ApprovalScope",
    "DEFAULT_STATE",
    "LEGAL_TRANSITIONS",
    "QualificationRecommendation",
    "QualificationState",
    "assert_transition",
    "is_approved",
]

from enum import StrEnum


class QualificationRecommendation(StrEnum):
    ELIGIBLE_FOR_REVIEW = "eligible_for_review"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    REJECT_RECOMMENDED = "reject_recommended"


# Directed edges: from_state → frozenset of allowed to_states
LEGAL_TRANSITIONS: dict[QualificationState, frozenset[QualificationState]] = {
    QualificationState.DRAFT: frozenset(
        {
            QualificationState.EVALUATION_REQUIRED,
        }
    ),
    QualificationState.EVALUATION_REQUIRED: frozenset(
        {
            QualificationState.EVALUATED,
        }
    ),
    QualificationState.EVALUATED: frozenset(
        {
            QualificationState.REVIEW_REQUIRED,
            QualificationState.REJECTED,
            QualificationState.EVALUATION_REQUIRED,
        }
    ),
    QualificationState.REVIEW_REQUIRED: frozenset(
        {
            QualificationState.APPROVED_FOR_PAPER,
            QualificationState.REJECTED,
            QualificationState.EVALUATION_REQUIRED,
        }
    ),
    QualificationState.APPROVED_FOR_PAPER: frozenset(
        {
            QualificationState.REVOKED,
            QualificationState.EXPIRED,
            QualificationState.EVALUATION_REQUIRED,
        }
    ),
    QualificationState.REJECTED: frozenset(
        {
            QualificationState.EVALUATION_REQUIRED,
        }
    ),
    QualificationState.REVOKED: frozenset(
        {
            QualificationState.EVALUATION_REQUIRED,
        }
    ),
    QualificationState.EXPIRED: frozenset(
        {
            QualificationState.EVALUATION_REQUIRED,
        }
    ),
}

DEFAULT_STATE = QualificationState.DRAFT


def assert_transition(current: QualificationState, target: QualificationState) -> None:
    allowed = LEGAL_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise IllegalTransitionError(
            f"illegal qualification transition {current.value} → {target.value}"
        )


def is_approved(state: QualificationState) -> bool:
    return state == QualificationState.APPROVED_FOR_PAPER
