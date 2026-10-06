"""Execution / fill ORM model — one order may have many fills."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from app.models.order import Order


class Execution(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "executions"
    __table_args__ = (
        Index("ix_executions_order_executed", "order_id", "executed_at"),
        UniqueConstraint(
            "order_id",
            "broker_execution_id",
            name="uq_executions_order_id_broker_execution_id",
        ),
        CheckConstraint("quantity > 0", name="ck_executions_quantity_positive"),
        CheckConstraint("price >= 0", name="ck_executions_price_non_negative"),
        CheckConstraint(
            "commission IS NULL OR commission >= 0",
            name="ck_executions_commission_non_negative",
        ),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
    )
    broker_execution_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    commission: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=utc_now,
    )

    order: Mapped[Order] = relationship(back_populates="executions")
