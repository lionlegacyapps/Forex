"""Risk policy ORM model — scoped limits; engine not implemented yet."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Index, Integer, Numeric, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.enums import RiskScopeType
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.types import str_enum_column


class RiskPolicy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "risk_policies"
    __table_args__ = (
        Index("ix_risk_policies_scope", "scope_type", "scope_id"),
        Index(
            "uq_risk_policies_global",
            "scope_type",
            unique=True,
            postgresql_where=text("scope_type = 'global'"),
        ),
        Index(
            "uq_risk_policies_scope",
            "scope_type",
            "scope_id",
            unique=True,
            postgresql_where=text("scope_id IS NOT NULL"),
        ),
        CheckConstraint(
            "(scope_type = 'global') = (scope_id IS NULL)",
            name="ck_risk_policies_scope_id_matches_type",
        ),
        CheckConstraint(
            "(max_position_value IS NULL OR max_position_value > 0)"
            " AND (max_position_percent IS NULL OR (max_position_percent > 0 AND max_position_percent <= 100))"
            " AND (max_daily_loss IS NULL OR max_daily_loss >= 0)"
            " AND (max_order_value IS NULL OR max_order_value > 0)"
            " AND (max_total_exposure IS NULL OR max_total_exposure > 0)"
            " AND (max_open_positions IS NULL OR max_open_positions > 0)",
            name="ck_risk_policies_limits_valid",
        ),
    )

    scope_type: Mapped[RiskScopeType] = mapped_column(
        str_enum_column(RiskScopeType, name="risk_scope_type"),
        nullable=False,
    )
    # Polymorphic reference (broker account / strategy / assignment id). Null for GLOBAL.
    scope_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)

    max_position_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    max_position_percent: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    max_daily_loss: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    max_open_positions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_order_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    max_total_exposure: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    # Fail-closed: stop-loss required unless a policy explicitly opts out.
    require_stop_loss: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
