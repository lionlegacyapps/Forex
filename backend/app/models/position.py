"""Position ORM model — strategy-aware; symbol alone is not unique."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.enums import AssetClass, PositionStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, utc_now
from app.models.types import str_enum_column

if TYPE_CHECKING:
    from app.models.broker_account import BrokerAccount
    from app.models.strategy import Strategy


class Position(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "positions"
    __table_args__ = (
        Index(
            "ix_positions_account_strategy_symbol",
            "broker_account_id",
            "strategy_id",
            "symbol",
        ),
        Index("ix_positions_account_status", "broker_account_id", "status"),
        Index("ix_positions_symbol_status", "symbol", "status"),
    )

    broker_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("broker_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategies.id", ondelete="SET NULL"),
        nullable=True,
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    asset_class: Mapped[AssetClass] = mapped_column(
        str_enum_column(AssetClass, name="position_asset_class"),
        nullable=False,
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    average_entry_price: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    realized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(24, 8),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
    unrealized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(24, 8),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
    status: Mapped[PositionStatus] = mapped_column(
        str_enum_column(PositionStatus, name="position_status"),
        nullable=False,
        default=PositionStatus.OPEN,
        server_default=PositionStatus.OPEN.value,
    )
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=utc_now,
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    broker_account: Mapped[BrokerAccount] = relationship(back_populates="positions")
    strategy: Mapped[Strategy | None] = relationship(back_populates="positions")
