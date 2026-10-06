"""Position ORM model — strategy-aware; symbol alone is not unique."""

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
    func,
    text,
)
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
        # One open position per account+strategy+symbol+asset_class.
        # Allows multiple strategies to trade the same symbol concurrently.
        Index(
            "uq_positions_open_account_strategy_symbol_asset",
            "broker_account_id",
            "strategy_id",
            "symbol",
            "asset_class",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
        CheckConstraint(
            "average_entry_price >= 0 AND (current_price IS NULL OR current_price >= 0)",
            name="ck_positions_prices_non_negative",
        ),
        CheckConstraint(
            "("
            "  (status = 'open' AND closed_at IS NULL AND quantity <> 0)"
            "  OR (status = 'closed' AND closed_at IS NOT NULL)"
            "  OR (status = 'flattening')"
            ")",
            name="ck_positions_open_closed_consistent",
        ),
    )

    broker_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("broker_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # RESTRICT preserves historical interpretability of positions.
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategies.id", ondelete="RESTRICT"),
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
