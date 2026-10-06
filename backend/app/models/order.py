"""Order ORM model — broker-submitted order linked to a trade proposal."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.enums import AssetClass, OrderStatus, OrderType, TradeSide
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.types import str_enum_column

if TYPE_CHECKING:
    from app.models.broker_account import BrokerAccount
    from app.models.execution import Execution
    from app.models.trade_proposal import TradeProposal


class Order(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_broker_account_status", "broker_account_id", "status"),
        Index("ix_orders_proposal_created", "trade_proposal_id", "created_at"),
        Index("ix_orders_symbol_created", "symbol", "created_at"),
    )

    trade_proposal_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("trade_proposals.id", ondelete="RESTRICT"),
        nullable=False,
    )
    broker_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("broker_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    broker_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    asset_class: Mapped[AssetClass] = mapped_column(
        str_enum_column(AssetClass, name="order_asset_class"),
        nullable=False,
    )
    side: Mapped[TradeSide] = mapped_column(
        str_enum_column(TradeSide, name="order_side"),
        nullable=False,
    )
    order_type: Mapped[OrderType] = mapped_column(
        str_enum_column(OrderType, name="order_order_type"),
        nullable=False,
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    stop_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    status: Mapped[OrderStatus] = mapped_column(
        str_enum_column(OrderStatus, name="order_status"),
        nullable=False,
        default=OrderStatus.NEW,
        server_default=OrderStatus.NEW.value,
        index=True,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    trade_proposal: Mapped[TradeProposal] = relationship(back_populates="orders")
    broker_account: Mapped[BrokerAccount] = relationship(back_populates="orders")
    executions: Mapped[list[Execution]] = relationship(back_populates="order")
