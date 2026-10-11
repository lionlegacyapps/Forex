"""Manual qualification approval checkpoint — prepare only, never auto-execute."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models.strategy_paper_qualification import StrategyPaperQualification
from app.onboarding.errors import OnboardingBlockedError
from app.qualification.auth import AuthenticatedOwner
from app.qualification.criteria import QualificationCriteria
from app.qualification.service import PaperQualificationService
from app.qualification.states import QualificationRecommendation, QualificationState


DEFAULT_QUALIFICATION_ID = uuid.UUID("b46aa6ab-dcb4-41d7-b3e0-d4d5667d0573")


@dataclass(frozen=True, slots=True)
class ApprovalCheckpoint:
    ready_for_owner_decision: bool
    qualification_id: str
    strategy_id: str
    strategy_version: str
    parameter_hash: str
    evidence_fingerprint: str
    state: str
    recommendation: str
    hard_blocker_count: int
    unsafe_override_offered: bool
    operation: str
    parameters: dict[str, Any]
    instructions: tuple[str, ...]
    blocked_reason: str | None = None


def prepare_approval_checkpoint(
    db: Session,
    *,
    qualification_id: uuid.UUID = DEFAULT_QUALIFICATION_ID,
    criteria: QualificationCriteria | None = None,
) -> ApprovalCheckpoint:
    """Inspect the qualification and describe the exact approve() call.

    Does **not** call approve().
    Does **not** offer an override when hard blockers exist.
    """
    row = db.get(StrategyPaperQualification, qualification_id)
    if row is None:
        raise OnboardingBlockedError(
            f"Qualification {qualification_id} not found",
            code="qualification_missing",
        )

    blockers = row.hard_blockers or []
    crit = criteria or QualificationCriteria()
    ttl_days = crit.approval_ttl_days
    params = {
        "qualification_id": str(row.id),
        "owner": "AuthenticatedOwner from verified Supabase sign-in (credential_verified=True)",
        "expires_at": f"optional; default now+{ttl_days} days",
        "binds_to": {
            "strategy_id": row.engine_strategy_id,
            "strategy_version": row.strategy_version,
            "parameter_hash": row.parameter_hash,
            "evidence_fingerprint": row.evidence_fingerprint,
            "approval_scope": row.approval_scope.value,
        },
    }
    instructions = (
        "1. Complete OWNER SETUP so PAPER_QUALIFICATION_OWNER_SUBJECTS matches your verified email.",
        "2. Review the human-readable qualification report thoroughly.",
        "3. Only if you accept the historical evidence (warnings and all), authorize approval.",
        "4. From a trusted server shell (never a public HTTP API), run the approve operation below.",
        "5. Confirm the returned state is approved_for_paper and expires_at is set.",
        "6. Do NOT enable the broker account or PAPER_SESSION_EXECUTE_ENABLED in this step.",
    )

    ready = True
    blocked_reason = None
    if blockers:
        ready = False
        blocked_reason = "hard blockers present — approval is refused by service; no override offered"
    elif row.qualification_state != QualificationState.REVIEW_REQUIRED:
        ready = False
        blocked_reason = f"state is {row.qualification_state.value}, need review_required"
    elif row.recommendation != QualificationRecommendation.ELIGIBLE_FOR_REVIEW.value:
        ready = False
        blocked_reason = f"recommendation is {row.recommendation}, need eligible_for_review"

    return ApprovalCheckpoint(
        ready_for_owner_decision=ready,
        qualification_id=str(row.id),
        strategy_id=row.engine_strategy_id,
        strategy_version=row.strategy_version,
        parameter_hash=row.parameter_hash,
        evidence_fingerprint=row.evidence_fingerprint,
        state=row.qualification_state.value,
        recommendation=row.recommendation or "",
        hard_blocker_count=len(blockers),
        unsafe_override_offered=False,
        operation="PaperQualificationService.approve(qualification_id, owner=AuthenticatedOwner(...))",
        parameters=params,
        instructions=instructions,
        blocked_reason=blocked_reason,
    )


def approval_cli_snippet(checkpoint: ApprovalCheckpoint) -> str:
    """Exact operator snippet — still requires explicit owner decision to run."""
    return f"""
# MANUAL APPROVAL ONLY — run after explicit owner decision.
# This snippet does not run itself. Do not paste until you intend to approve.

from datetime import UTC, datetime, timedelta
from uuid import UUID
from app.core.config import get_settings
from app.db.session import get_session_factory, reset_db_state
from app.onboarding.supabase_owner import sign_in_supabase_password
from app.onboarding.owner import require_authenticated_owner
from app.qualification.service import PaperQualificationService

QUALIFICATION_ID = UUID("{checkpoint.qualification_id}")
# Expected bindings (abort if mismatch):
# strategy={checkpoint.strategy_id}@{checkpoint.strategy_version}
# parameter_hash={checkpoint.parameter_hash}
# evidence_fingerprint={checkpoint.evidence_fingerprint}

get_settings.cache_clear(); reset_db_state()
settings = get_settings()
assert settings.paper_session_execute_enabled is False

email = input("Owner email: ").strip()
password = __import__("getpass").getpass("Owner password: ")
identity, _token = sign_in_supabase_password(email, password, settings=settings)
del _token
owner = require_authenticated_owner(
    subject=identity.subject,
    credential_verified=True,
    settings=settings,
)

factory = get_session_factory()
with factory() as db:
    row = db.get(__import__("app.models.strategy_paper_qualification", fromlist=["StrategyPaperQualification"]).StrategyPaperQualification, QUALIFICATION_ID)
    assert row is not None
    assert row.parameter_hash == "{checkpoint.parameter_hash}"
    assert row.evidence_fingerprint == "{checkpoint.evidence_fingerprint}"
    assert row.strategy_version == "{checkpoint.strategy_version}"
    assert not row.hard_blockers
    svc = PaperQualificationService(db)
    approved = svc.approve(QUALIFICATION_ID, owner=owner)
    db.commit()
    print("state=", approved.qualification_state.value)
    print("expires_at=", approved.expires_at)
    print("approved_by=", approved.approved_by_actor_reference)
""".strip()


def execute_approval_if_authorized(
    db: Session,
    *,
    qualification_id: uuid.UUID,
    owner: AuthenticatedOwner,
    explicit_authorization_phrase: str,
    expires_at: datetime | None = None,
) -> StrategyPaperQualification:
    """Execute approval only when the owner supplies the exact authorization phrase.

    Required phrase: APPROVE_SMA_CROSSOVER_FOR_PAPER
    Still refuses hard blockers via PaperQualificationService.approve.
    """
    if explicit_authorization_phrase.strip() != "APPROVE_SMA_CROSSOVER_FOR_PAPER":
        raise OnboardingBlockedError(
            "Approval not executed — missing explicit authorization phrase",
            code="approval_not_authorized",
        )
    svc = PaperQualificationService(db)
    return svc.approve(
        qualification_id,
        owner=owner,
        expires_at=expires_at,
        now=datetime.now(UTC),
    )
