"""Durable paper-strategy qualification / approval records.

Qualification is not execution. Approval never implies live trading.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.enums import ApprovalScope, QualificationState
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.types import str_enum_column

if TYPE_CHECKING:
    from app.models.strategy import Strategy


class StrategyPaperQualification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "strategy_paper_qualifications"
    __table_args__ = (
        UniqueConstraint(
            "engine_strategy_id",
            "strategy_version",
            "parameter_hash",
            "evidence_fingerprint",
            name="uq_paper_qual_evidence_binding",
        ),
        Index("ix_paper_qual_engine_state", "engine_strategy_id", "qualification_state"),
        Index("ix_paper_qual_expires", "expires_at"),
        CheckConstraint(
            "approval_scope = 'paper_only'",
            name="ck_paper_qual_scope_paper_only",
        ),
        CheckConstraint(
            "state_version >= 0",
            name="ck_paper_qual_state_version_nonneg",
        ),
    )

    strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategies.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    engine_strategy_id: Mapped[str] = mapped_column(String(128), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    parameter_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)

    qualification_state: Mapped[QualificationState] = mapped_column(
        str_enum_column(QualificationState, name="paper_qualification_state"),
        nullable=False,
        default=QualificationState.DRAFT,
        server_default=QualificationState.DRAFT.value,
        index=True,
    )
    approval_scope: Mapped[ApprovalScope] = mapped_column(
        str_enum_column(ApprovalScope, name="paper_qualification_scope"),
        nullable=False,
        default=ApprovalScope.PAPER_ONLY,
        server_default=ApprovalScope.PAPER_ONLY.value,
    )
    recommendation: Mapped[str | None] = mapped_column(String(64), nullable=True)
    report: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    hard_blockers: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    warnings: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )

    approved_by_actor_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_by_actor_reference: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Optimistic concurrency for atomic transitions
    state_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    strategy: Mapped[Strategy | None] = relationship(
        back_populates="paper_qualifications",
    )
