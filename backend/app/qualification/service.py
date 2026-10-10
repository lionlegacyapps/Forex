"""Paper Strategy Qualification Gate — evidence review + manual approval.

Never starts strategies, creates broker orders, activates sessions, or enables live trading.
No public HTTP approval endpoint is registered by this module.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.audit.service import AuditService
from app.evaluation.walkforward.harness import WalkForwardResult
from app.models.strategy_paper_qualification import StrategyPaperQualification
from app.qualification.auth import AuthenticatedOwner
from app.qualification.criteria import POLICY_VERSION, QualificationCriteria
from app.qualification.errors import HardBlockerError, QualificationError, StaleApprovalError
from app.qualification.evidence import review_walk_forward_evidence
from app.qualification.report import QualificationReport
from app.qualification.repository import QualificationRepository
from app.qualification.states import (
    DEFAULT_STATE,
    ApprovalScope,
    QualificationRecommendation,
    QualificationState,
    assert_transition,
)

# Audit event types
QUALIFICATION_CREATED = "PAPER_QUALIFICATION_CREATED"
QUALIFICATION_EVALUATED = "PAPER_QUALIFICATION_EVALUATED"
QUALIFICATION_REVIEW_REQUIRED = "PAPER_QUALIFICATION_REVIEW_REQUIRED"
QUALIFICATION_APPROVED = "PAPER_QUALIFICATION_APPROVED"
QUALIFICATION_REJECTED = "PAPER_QUALIFICATION_REJECTED"
QUALIFICATION_REVOKED = "PAPER_QUALIFICATION_REVOKED"
QUALIFICATION_EXPIRED = "PAPER_QUALIFICATION_EXPIRED"
QUALIFICATION_INVALIDATED = "PAPER_QUALIFICATION_INVALIDATED"


class PaperQualificationService:
    """Durable qualification workflow with manual owner approval."""

    def __init__(
        self,
        session: Session,
        *,
        criteria: QualificationCriteria | None = None,
        audit: AuditService | None = None,
    ) -> None:
        self.session = session
        self.criteria = criteria or QualificationCriteria()
        self.repo = QualificationRepository(session)
        self.audit = audit or AuditService(session)
        self._broker_orders_created = 0

    @property
    def broker_orders_created(self) -> int:
        return self._broker_orders_created

    def create_draft(
        self,
        *,
        engine_strategy_id: str,
        strategy_version: str,
        parameter_hash: str,
        evidence_fingerprint: str,
        evaluation_id: str,
        dataset_fingerprint: str,
        strategy_db_id: uuid.UUID | None = None,
    ) -> StrategyPaperQualification:
        existing = self.repo.find_by_evidence_binding(
            engine_strategy_id=engine_strategy_id,
            strategy_version=strategy_version,
            parameter_hash=parameter_hash,
            evidence_fingerprint=evidence_fingerprint,
        )
        if existing is not None:
            return existing  # idempotent

        row = StrategyPaperQualification(
            strategy_id=strategy_db_id,
            engine_strategy_id=engine_strategy_id,
            strategy_version=strategy_version,
            parameter_hash=parameter_hash,
            evidence_fingerprint=evidence_fingerprint,
            evaluation_id=evaluation_id,
            dataset_fingerprint=dataset_fingerprint,
            policy_version=self.criteria.policy_version,
            qualification_state=DEFAULT_STATE,
            approval_scope=ApprovalScope.PAPER_ONLY,
            report={},
            hard_blockers=[],
            warnings=[],
            state_version=0,
        )
        self.repo.add(row)
        self._audit(
            QUALIFICATION_CREATED,
            row,
            actor_type="system",
            details={"state": row.qualification_state.value},
        )
        return row

    def require_evaluation(
        self, qualification_id: uuid.UUID
    ) -> StrategyPaperQualification:
        row = self._get(qualification_id)
        return self._transition(row, QualificationState.EVALUATION_REQUIRED)

    def submit_walk_forward_evidence(
        self,
        qualification_id: uuid.UUID,
        result: WalkForwardResult,
        *,
        generated_at: datetime | None = None,
    ) -> tuple[StrategyPaperQualification, QualificationReport]:
        row = self._get(qualification_id)
        if row.qualification_state == QualificationState.DRAFT:
            row = self._transition(row, QualificationState.EVALUATION_REQUIRED)

        report = review_walk_forward_evidence(
            result, criteria=self.criteria, generated_at=generated_at
        )
        self._assert_evidence_binding(row, report)

        # Move to EVALUATED
        if row.qualification_state == QualificationState.EVALUATION_REQUIRED:
            row = self._transition(
                row,
                QualificationState.EVALUATED,
                recommendation=report.recommendation.value,
                report=report.to_serializable_dict(),
                hard_blockers=[f.model_dump(mode="json") for f in report.hard_blockers],
                warnings=[f.model_dump(mode="json") for f in report.warnings],
                policy_version=report.policy_version,
            )
        elif row.qualification_state == QualificationState.EVALUATED:
            # Idempotent re-submit of same evidence updates report in place
            row = self.repo.transition_atomic(
                row,
                expected_version=row.state_version,
                new_state=QualificationState.EVALUATED,
                recommendation=report.recommendation.value,
                report=report.to_serializable_dict(),
                hard_blockers=[f.model_dump(mode="json") for f in report.hard_blockers],
                warnings=[f.model_dump(mode="json") for f in report.warnings],
            )
        else:
            raise QualificationError(
                f"cannot submit evidence from state {row.qualification_state.value}",
                code="invalid_state_for_evidence",
            )

        self._audit(
            QUALIFICATION_EVALUATED,
            row,
            actor_type="system",
            details={
                "recommendation": report.recommendation.value,
                "hard_blocker_count": len(report.hard_blockers),
            },
        )

        # Auto-route recommendation (still not approval)
        if report.recommendation == QualificationRecommendation.ELIGIBLE_FOR_REVIEW:
            row = self._transition(row, QualificationState.REVIEW_REQUIRED)
            self._audit(
                QUALIFICATION_REVIEW_REQUIRED,
                row,
                actor_type="system",
                details={"recommendation": report.recommendation.value},
            )
        elif report.recommendation in {
            QualificationRecommendation.INSUFFICIENT_EVIDENCE,
            QualificationRecommendation.REJECT_RECOMMENDED,
        }:
            # Leave in EVALUATED or move to REJECTED only via explicit reject;
            # recommendation is recorded — do not auto-reject without owner for
            # REJECT_RECOMMENDED when hard blockers exist: stay EVALUATED so
            # owner can reject, or we can auto-stay. Spec: "Do not automatically
            # approve". Auto-reject on hard blockers is OK for clarity.
            if report.has_hard_blockers:
                # Keep EVALUATED with recommendation; owner must reject or re-eval
                pass

        assert self._broker_orders_created == 0
        return row, report

    def approve(
        self,
        qualification_id: uuid.UUID,
        *,
        owner: AuthenticatedOwner,
        expires_at: datetime | None = None,
        now: datetime | None = None,
    ) -> StrategyPaperQualification:
        """Manual approval — requires AuthenticatedOwner (server-established)."""
        now = now or datetime.now(UTC)
        row = self._get(qualification_id)
        if row.qualification_state != QualificationState.REVIEW_REQUIRED:
            raise QualificationError(
                "approval requires REVIEW_REQUIRED state",
                code="not_ready_for_approval",
            )
        if row.hard_blockers:
            raise HardBlockerError(
                "cannot approve while hard blockers remain; blockers are not waived"
            )
        if row.recommendation != QualificationRecommendation.ELIGIBLE_FOR_REVIEW.value:
            raise HardBlockerError(
                "cannot approve unless recommendation is eligible_for_review"
            )
        if row.approval_scope != ApprovalScope.PAPER_ONLY:
            raise HardBlockerError("approval_scope must be paper_only")
        if row.policy_version != self.criteria.policy_version:
            raise StaleApprovalError(
                "qualification policy version mismatch; re-evaluate required"
            )

        exp = expires_at or (
            now + timedelta(days=self.criteria.approval_ttl_days)
        )
        row = self._transition(
            row,
            QualificationState.APPROVED_FOR_PAPER,
            approved_by_actor_type=owner.actor_type,
            approved_by_actor_reference=owner.subject,
            approved_at=now,
            expires_at=exp,
            rejection_reason=None,
            revocation_reason=None,
        )
        self._audit(
            QUALIFICATION_APPROVED,
            row,
            actor_type=owner.actor_type,
            actor_reference=owner.subject,
            details={
                "approval_scope": ApprovalScope.PAPER_ONLY.value,
                "parameter_hash": row.parameter_hash,
                "evidence_fingerprint": row.evidence_fingerprint,
                "policy_version": row.policy_version,
                "expires_at": exp.isoformat(),
                "strategy_version": row.strategy_version,
            },
        )
        assert self._broker_orders_created == 0
        return row

    def reject(
        self,
        qualification_id: uuid.UUID,
        *,
        owner: AuthenticatedOwner,
        reason: str,
    ) -> StrategyPaperQualification:
        row = self._get(qualification_id)
        if row.qualification_state not in {
            QualificationState.EVALUATED,
            QualificationState.REVIEW_REQUIRED,
        }:
            raise QualificationError(
                "reject requires EVALUATED or REVIEW_REQUIRED",
                code="invalid_state_for_reject",
            )
        row = self._transition(
            row,
            QualificationState.REJECTED,
            rejection_reason=reason,
            approved_by_actor_type=None,
            approved_by_actor_reference=None,
            approved_at=None,
            expires_at=None,
        )
        self._audit(
            QUALIFICATION_REJECTED,
            row,
            actor_type=owner.actor_type,
            actor_reference=owner.subject,
            details={"reason": reason},
        )
        return row

    def revoke(
        self,
        qualification_id: uuid.UUID,
        *,
        owner: AuthenticatedOwner,
        reason: str,
    ) -> StrategyPaperQualification:
        row = self._get(qualification_id)
        if row.qualification_state != QualificationState.APPROVED_FOR_PAPER:
            raise QualificationError(
                "revoke requires APPROVED_FOR_PAPER",
                code="invalid_state_for_revoke",
            )
        row = self._transition(
            row,
            QualificationState.REVOKED,
            revocation_reason=reason,
        )
        self._audit(
            QUALIFICATION_REVOKED,
            row,
            actor_type=owner.actor_type,
            actor_reference=owner.subject,
            details={"reason": reason},
        )
        return row

    def expire_if_needed(
        self,
        qualification_id: uuid.UUID,
        *,
        now: datetime | None = None,
    ) -> StrategyPaperQualification:
        now = now or datetime.now(UTC)
        row = self._get(qualification_id)
        if row.qualification_state != QualificationState.APPROVED_FOR_PAPER:
            return row
        if row.expires_at is None or now < row.expires_at:
            return row
        row = self._transition(row, QualificationState.EXPIRED)
        self._audit(
            QUALIFICATION_EXPIRED,
            row,
            actor_type="system",
            details={"expired_at": now.isoformat()},
        )
        return row

    def invalidate_for_change(
        self,
        qualification_id: uuid.UUID,
        *,
        reason: str,
        new_strategy_version: str | None = None,
        new_parameter_hash: str | None = None,
        new_evidence_fingerprint: str | None = None,
        new_policy_version: str | None = None,
    ) -> StrategyPaperQualification:
        """Invalidate approval when strategy/params/evidence/policy change."""
        row = self._get(qualification_id)
        changed = False
        if new_strategy_version is not None and new_strategy_version != row.strategy_version:
            changed = True
        if new_parameter_hash is not None and new_parameter_hash != row.parameter_hash:
            changed = True
        if (
            new_evidence_fingerprint is not None
            and new_evidence_fingerprint != row.evidence_fingerprint
        ):
            changed = True
        if new_policy_version is not None and new_policy_version != row.policy_version:
            changed = True
        if not changed and row.qualification_state == QualificationState.APPROVED_FOR_PAPER:
            # Explicit invalidation call without field diffs still allowed via reason
            changed = True
        if not changed:
            return row

        if row.qualification_state == QualificationState.APPROVED_FOR_PAPER:
            target = QualificationState.EVALUATION_REQUIRED
        elif row.qualification_state in {
            QualificationState.REVIEW_REQUIRED,
            QualificationState.EVALUATED,
        }:
            target = QualificationState.EVALUATION_REQUIRED
        else:
            return row

        row = self._transition(
            row,
            target,
            approved_by_actor_type=None,
            approved_by_actor_reference=None,
            approved_at=None,
            expires_at=None,
            revocation_reason=reason,
        )
        self._audit(
            QUALIFICATION_INVALIDATED,
            row,
            actor_type="system",
            details={"reason": reason},
        )
        return row

    def request_reevaluation(
        self, qualification_id: uuid.UUID
    ) -> StrategyPaperQualification:
        row = self._get(qualification_id)
        if row.qualification_state not in {
            QualificationState.REJECTED,
            QualificationState.REVOKED,
            QualificationState.EXPIRED,
            QualificationState.EVALUATED,
            QualificationState.REVIEW_REQUIRED,
            QualificationState.APPROVED_FOR_PAPER,
        }:
            if row.qualification_state == QualificationState.DRAFT:
                return self.require_evaluation(qualification_id)
            raise QualificationError(
                f"cannot re-evaluate from {row.qualification_state.value}",
                code="invalid_reeval_state",
            )
        return self._transition(
            row,
            QualificationState.EVALUATION_REQUIRED,
            approved_by_actor_type=None,
            approved_by_actor_reference=None,
            approved_at=None,
            expires_at=None,
        )

    def _get(self, qualification_id: uuid.UUID) -> StrategyPaperQualification:
        row = self.repo.get(qualification_id)
        if row is None:
            raise QualificationError("qualification not found", code="not_found")
        return row

    def _transition(
        self,
        row: StrategyPaperQualification,
        target: QualificationState,
        **fields: Any,
    ) -> StrategyPaperQualification:
        assert_transition(row.qualification_state, target)
        return self.repo.transition_atomic(
            row,
            expected_version=row.state_version,
            new_state=target,
            **fields,
        )

    def _assert_evidence_binding(
        self, row: StrategyPaperQualification, report: QualificationReport
    ) -> None:
        if report.strategy_id != row.engine_strategy_id:
            raise StaleApprovalError("strategy_id mismatch vs qualification record")
        if report.strategy_version != row.strategy_version:
            raise StaleApprovalError("strategy_version mismatch vs qualification record")
        if report.parameter_hash != row.parameter_hash:
            raise StaleApprovalError("parameter_hash mismatch vs qualification record")
        if report.evidence_fingerprint != row.evidence_fingerprint:
            raise StaleApprovalError("evidence_fingerprint mismatch vs qualification record")
        if report.evaluation_id != row.evaluation_id:
            raise StaleApprovalError("evaluation_id mismatch vs qualification record")

    def _audit(
        self,
        event_type: str,
        row: StrategyPaperQualification,
        *,
        actor_type: str,
        actor_reference: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "engine_strategy_id": row.engine_strategy_id,
            "strategy_version": row.strategy_version,
            "parameter_hash": row.parameter_hash,
            "evidence_fingerprint": row.evidence_fingerprint,
            "state": row.qualification_state.value,
            "approval_scope": row.approval_scope.value,
            "policy_version": row.policy_version,
            **(details or {}),
        }
        self.audit.record(
            event_type=event_type,
            entity_type="strategy_paper_qualification",
            entity_id=row.id,
            actor_type=actor_type,
            actor_reference=actor_reference,
            details=payload,
        )


# Ensure POLICY_VERSION is referenced for importers
__all__ = [
    "POLICY_VERSION",
    "PaperQualificationService",
    "QUALIFICATION_APPROVED",
    "QUALIFICATION_CREATED",
    "QUALIFICATION_EVALUATED",
    "QUALIFICATION_EXPIRED",
    "QUALIFICATION_INVALIDATED",
    "QUALIFICATION_REJECTED",
    "QUALIFICATION_REVIEW_REQUIRED",
    "QUALIFICATION_REVOKED",
]
