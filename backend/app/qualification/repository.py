"""Durable repository for strategy paper qualifications."""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.mixins import utc_now
from app.models.strategy_paper_qualification import StrategyPaperQualification
from app.qualification.errors import ConcurrentStateError
from app.qualification.states import QualificationState


class QualificationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, qualification_id: uuid.UUID) -> StrategyPaperQualification | None:
        return self.session.get(StrategyPaperQualification, qualification_id)

    def find_by_evidence_binding(
        self,
        *,
        engine_strategy_id: str,
        strategy_version: str,
        parameter_hash: str,
        evidence_fingerprint: str,
    ) -> StrategyPaperQualification | None:
        q = select(StrategyPaperQualification).where(
            StrategyPaperQualification.engine_strategy_id == engine_strategy_id,
            StrategyPaperQualification.strategy_version == strategy_version,
            StrategyPaperQualification.parameter_hash == parameter_hash,
            StrategyPaperQualification.evidence_fingerprint == evidence_fingerprint,
        )
        return self.session.execute(q).scalars().first()

    def find_active_approval(
        self,
        *,
        engine_strategy_id: str,
        strategy_version: str,
        parameter_hash: str,
        evidence_fingerprint: str,
    ) -> StrategyPaperQualification | None:
        row = self.find_by_evidence_binding(
            engine_strategy_id=engine_strategy_id,
            strategy_version=strategy_version,
            parameter_hash=parameter_hash,
            evidence_fingerprint=evidence_fingerprint,
        )
        if row is None:
            return None
        if row.qualification_state != QualificationState.APPROVED_FOR_PAPER:
            return None
        return row

    def add(self, row: StrategyPaperQualification) -> StrategyPaperQualification:
        self.session.add(row)
        self.session.flush()
        return row

    def transition_atomic(
        self,
        row: StrategyPaperQualification,
        *,
        expected_version: int,
        new_state: QualificationState,
        **fields: object,
    ) -> StrategyPaperQualification:
        """Optimistic concurrency: UPDATE … WHERE state_version = expected."""
        values = {
            "qualification_state": new_state,
            "state_version": expected_version + 1,
            "updated_at": utc_now(),
            **fields,
        }
        stmt = (
            update(StrategyPaperQualification)
            .where(
                StrategyPaperQualification.id == row.id,
                StrategyPaperQualification.state_version == expected_version,
                StrategyPaperQualification.qualification_state == row.qualification_state,
            )
            .values(**values)
        )
        result = self.session.execute(stmt)
        if result.rowcount != 1:  # type: ignore[attr-defined]
            raise ConcurrentStateError(
                "qualification state changed concurrently; transition aborted"
            )
        self.session.refresh(row)
        return row
