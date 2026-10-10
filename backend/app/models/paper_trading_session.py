"""Controlled paper trading session — durable lifecycle state.

Sessions never auto-start. Live trading is impossible through this model.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
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
from app.models.enums import PaperSessionExecutionMode, PaperSessionState
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.types import str_enum_column

if TYPE_CHECKING:
    from app.models.broker_account import BrokerAccount
    from app.models.paper_execution_authorization import PaperExecutionAuthorization
    from app.models.strategy import Strategy
    from app.models.strategy_paper_qualification import StrategyPaperQualification


class PaperTradingSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "paper_trading_sessions"
    __table_args__ = (
        Index("ix_paper_sessions_account_state", "broker_account_id", "session_state"),
        Index("ix_paper_sessions_strategy_state", "engine_strategy_id", "session_state"),
        Index("ix_paper_sessions_lease", "worker_lease_expires_at"),
        # At most one non-terminal session per paper account (V1).
        Index(
            "uq_paper_sessions_one_active_per_account",
            "broker_account_id",
            unique=True,
            postgresql_where=text(
                "session_state IN ('created','ready','running','pausing','paused','stopping')"
            ),
        ),
        CheckConstraint(
            "execution_mode IN ('dry_run', 'paper_execute')",
            name="ck_paper_sessions_execution_mode",
        ),
        CheckConstraint(
            "orders_submitted_count >= 0 AND max_orders_per_session > 0",
            name="ck_paper_sessions_order_counts",
        ),
        CheckConstraint("state_version >= 0", name="ck_paper_sessions_state_version"),
    )

    # session_id is the UUID primary key (`id`)
    strategy_db_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategies.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    engine_strategy_id: Mapped[str] = mapped_column(String(128), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    parameter_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    qualification_approval_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategy_paper_qualifications.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    evidence_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    broker_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("broker_accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    instrument: Mapped[str] = mapped_column(String(64), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(32), nullable=False)
    session_state: Mapped[PaperSessionState] = mapped_column(
        str_enum_column(PaperSessionState, name="paper_session_state"),
        nullable=False,
        default=PaperSessionState.CREATED,
        server_default=PaperSessionState.CREATED.value,
        index=True,
    )
    execution_mode: Mapped[PaperSessionExecutionMode] = mapped_column(
        str_enum_column(PaperSessionExecutionMode, name="paper_session_execution_mode"),
        nullable=False,
        default=PaperSessionExecutionMode.DRY_RUN,
        server_default=PaperSessionExecutionMode.DRY_RUN.value,
    )
    start_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    stopped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_processed_bar_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    stop_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_limits: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    orders_submitted_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    max_orders_per_session: Mapped[int] = mapped_column(
        Integer, nullable=False, default=50, server_default=text("50")
    )
    worker_lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    worker_lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    state_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    failure_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    submissions_blocked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    submissions_block_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    strategy: Mapped[Strategy | None] = relationship()
    broker_account: Mapped[BrokerAccount] = relationship()
    qualification: Mapped[StrategyPaperQualification] = relationship()
    processed_bars: Mapped[list[PaperSessionProcessedBar]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )
    execution_authorizations: Mapped[list[PaperExecutionAuthorization]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )


class PaperSessionProcessedBar(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Idempotency ledger for completed-bar decisions."""

    __tablename__ = "paper_session_processed_bars"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "idempotency_key",
            name="uq_paper_session_idempotency_key",
        ),
        UniqueConstraint(
            "session_id",
            "bar_timestamp",
            "decision_identity",
            name="uq_paper_session_bar_decision",
        ),
        Index("ix_paper_session_processed_session", "session_id"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("paper_trading_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    bar_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    decision_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    outcome: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    session: Mapped[PaperTradingSession] = relationship(back_populates="processed_bars")
