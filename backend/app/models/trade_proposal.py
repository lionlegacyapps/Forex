"""Trade proposal ORM model — pipeline entry point before any broker order."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.enums import (
    AssetClass,
    OrderType,
    ProposalSource,
    TimeInForce,
    TradeProposalStatus,
    TradeSide,
)
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.types import str_enum_column

if TYPE_CHECKING:
    from app.models.broker_account import BrokerAccount
    from app.models.market_memory_event import MarketMemoryEvent
    from app.models.order import Order
    from app.models.strategy import Strategy


class TradeProposal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "trade_proposals"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "broker_account_id",
            name="uq_trade_proposals_id_broker_account_id",
        ),
        Index("ix_trade_proposals_broker_account_status", "broker_account_id", "status"),
        Index("ix_trade_proposals_strategy_created", "strategy_id", "created_at"),
        Index("ix_trade_proposals_symbol_created", "symbol", "created_at"),
        CheckConstraint("quantity > 0", name="ck_trade_proposals_quantity_positive"),
        CheckConstraint(
            "(limit_price IS NULL OR limit_price >= 0)"
            " AND (stop_price IS NULL OR stop_price >= 0)"
            " AND (take_profit_price IS NULL OR take_profit_price >= 0)"
            " AND (stop_loss_price IS NULL OR stop_loss_price >= 0)",
            name="ck_trade_proposals_prices_non_negative",
        ),
        CheckConstraint(
            "(source <> 'strategy') OR (strategy_id IS NOT NULL)",
            name="ck_trade_proposals_strategy_source",
        ),
    )

    # RESTRICT: strategies with historical proposals cannot be hard-deleted.
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategies.id", ondelete="RESTRICT"),
        nullable=True,
    )
    broker_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("broker_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source: Mapped[ProposalSource] = mapped_column(
        str_enum_column(ProposalSource, name="trade_proposal_source"),
        nullable=False,
        index=True,
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    asset_class: Mapped[AssetClass] = mapped_column(
        str_enum_column(AssetClass, name="trade_proposal_asset_class"),
        nullable=False,
    )
    side: Mapped[TradeSide] = mapped_column(
        str_enum_column(TradeSide, name="trade_proposal_side"),
        nullable=False,
    )
    order_type: Mapped[OrderType] = mapped_column(
        str_enum_column(OrderType, name="trade_proposal_order_type"),
        nullable=False,
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    # Entry stop/stop-limit trigger (order-type dependent).
    stop_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    take_profit_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    # Protective exit level for the resulting position plan (not the same as stop_price).
    stop_loss_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    time_in_force: Mapped[TimeInForce] = mapped_column(
        str_enum_column(TimeInForce, name="trade_proposal_tif"),
        nullable=False,
        default=TimeInForce.DAY,
        server_default=TimeInForce.DAY.value,
    )
    status: Mapped[TradeProposalStatus] = mapped_column(
        str_enum_column(TradeProposalStatus, name="trade_proposal_status"),
        nullable=False,
        default=TradeProposalStatus.PENDING,
        server_default=TradeProposalStatus.PENDING.value,
        index=True,
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    signal_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    strategy: Mapped[Strategy | None] = relationship(back_populates="trade_proposals")
    broker_account: Mapped[BrokerAccount] = relationship(back_populates="trade_proposals")
    orders: Mapped[list[Order]] = relationship(
        back_populates="trade_proposal",
        foreign_keys="Order.trade_proposal_id",
    )
    market_memory_events: Mapped[list[MarketMemoryEvent]] = relationship(
        back_populates="trade_proposal",
    )
