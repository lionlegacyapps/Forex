"""Order ORM model — broker-submitted order linked to a trade proposal."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.enums import AssetClass, OrderStatus, OrderType, TimeInForce, TradeSide
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.types import str_enum_column

if TYPE_CHECKING:
    from app.models.broker_account import BrokerAccount
    from app.models.execution import Execution
    from app.models.trade_proposal import TradeProposal


class Order(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        # Ensures the order's broker_account_id matches the proposal's account.
        ForeignKeyConstraint(
            ["trade_proposal_id", "broker_account_id"],
            ["trade_proposals.id", "trade_proposals.broker_account_id"],
            name="fk_orders_trade_proposal_account",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "broker_account_id",
            "broker_order_id",
            name="uq_orders_broker_account_id_broker_order_id",
        ),
        Index("ix_orders_broker_account_status", "broker_account_id", "status"),
        Index("ix_orders_proposal_created", "trade_proposal_id", "created_at"),
        Index("ix_orders_symbol_created", "symbol", "created_at"),
        CheckConstraint("quantity > 0", name="ck_orders_quantity_positive"),
        CheckConstraint(
            "(limit_price IS NULL OR limit_price >= 0)"
            " AND (stop_price IS NULL OR stop_price >= 0)",
            name="ck_orders_prices_non_negative",
        ),
    )

    trade_proposal_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    broker_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("broker_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    broker_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
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
    time_in_force: Mapped[TimeInForce] = mapped_column(
        str_enum_column(TimeInForce, name="order_tif"),
        nullable=False,
        default=TimeInForce.DAY,
        server_default=TimeInForce.DAY.value,
    )
    status: Mapped[OrderStatus] = mapped_column(
        str_enum_column(OrderStatus, name="order_status"),
        nullable=False,
        default=OrderStatus.NEW,
        server_default=OrderStatus.NEW.value,
        index=True,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    trade_proposal: Mapped[TradeProposal] = relationship(
        back_populates="orders",
        foreign_keys=[trade_proposal_id, broker_account_id],
        overlaps="broker_account,orders",
    )
    broker_account: Mapped[BrokerAccount] = relationship(
        back_populates="orders",
        overlaps="trade_proposal",
    )
    executions: Mapped[list[Execution]] = relationship(back_populates="order")
