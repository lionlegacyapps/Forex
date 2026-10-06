"""Many-to-many assignment of strategies to broker accounts."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.enums import TradingMode
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.types import str_enum_column

if TYPE_CHECKING:
    from app.models.broker_account import BrokerAccount
    from app.models.strategy import Strategy


class StrategyAccountAssignment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "strategy_account_assignments"
    __table_args__ = (
        UniqueConstraint(
            "strategy_id",
            "broker_account_id",
            name="uq_strategy_account_assignment",
        ),
    )

    strategy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    broker_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("broker_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    trading_mode: Mapped[TradingMode] = mapped_column(
        str_enum_column(TradingMode, name="assignment_trading_mode"),
        nullable=False,
        default=TradingMode.PAPER,
        server_default=TradingMode.PAPER.value,
    )
    capital_allocation: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    max_position_size: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    daily_loss_limit: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    max_concurrent_positions: Mapped[int | None] = mapped_column(Integer, nullable=True)

    strategy: Mapped[Strategy] = relationship(back_populates="account_assignments")
    broker_account: Mapped[BrokerAccount] = relationship(back_populates="strategy_assignments")
