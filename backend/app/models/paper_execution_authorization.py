"""Session-scoped PAPER_EXECUTE authorization (consent).

Never accepts client-provided account-mode flags as proof of paper status.
Live trading is impossible through this model.
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
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.enums import PaperExecutionConsentState
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.types import str_enum_column

if TYPE_CHECKING:
    from app.models.broker_account import BrokerAccount
    from app.models.paper_trading_session import PaperTradingSession


class PaperExecutionAuthorization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "paper_execution_authorizations"
    __table_args__ = (
        Index(
            "ix_paper_exec_auth_session_state",
            "session_id",
            "consent_state",
        ),
        Index("ix_paper_exec_auth_account", "broker_account_id"),
        Index("ix_paper_exec_auth_expires", "expires_at"),
        # At most one GRANTED consent per session.
        Index(
            "uq_paper_exec_auth_one_granted_per_session",
            "session_id",
            unique=True,
            postgresql_where=text("consent_state = 'granted'"),
        ),
        CheckConstraint(
            "consent_state IN ('granted', 'revoked', 'expired', 'consumed')",
            name="ck_paper_exec_auth_state",
        ),
        CheckConstraint("state_version >= 0", name="ck_paper_exec_auth_state_version"),
        CheckConstraint(
            "scope = 'paper_execute'",
            name="ck_paper_exec_auth_scope_paper_only",
        ),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("paper_trading_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    broker_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("broker_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    owner_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    scope: Mapped[str] = mapped_column(
        String(32), nullable=False, default="paper_execute", server_default="paper_execute"
    )
    consent_state: Mapped[PaperExecutionConsentState] = mapped_column(
        str_enum_column(PaperExecutionConsentState, name="paper_execution_consent_state"),
        nullable=False,
        default=PaperExecutionConsentState.GRANTED,
        server_default=PaperExecutionConsentState.GRANTED.value,
    )
    authorization_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    paper_endpoint_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    paper_base_url_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    one_time: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoke_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    state_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    session: Mapped[PaperTradingSession] = relationship(
        back_populates="execution_authorizations"
    )
    broker_account: Mapped[BrokerAccount] = relationship()
