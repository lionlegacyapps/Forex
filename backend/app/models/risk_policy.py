"""Risk policy ORM model — scoped limits; engine not implemented yet."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import Boolean, Index, Integer, Numeric
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
    require_stop_loss: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
