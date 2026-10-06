"""Market memory event foundation — storage only, no memory logic yet."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.enums import AssetClass
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin, utc_now
from app.models.types import str_enum_column

if TYPE_CHECKING:
    from app.models.strategy import Strategy
    from app.models.trade_proposal import TradeProposal


class MarketMemoryEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "market_memory_events"
    __table_args__ = (
        Index("ix_market_memory_symbol_event_time", "symbol", "event_time"),
        Index("ix_market_memory_strategy_event_time", "strategy_id", "event_time"),
        Index("ix_market_memory_proposal", "trade_proposal_id"),
    )

    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    asset_class: Mapped[AssetClass] = mapped_column(
        str_enum_column(AssetClass, name="market_memory_asset_class"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=utc_now,
        index=True,
    )
    market_context: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategies.id", ondelete="RESTRICT"),
        nullable=True,
    )
    trade_proposal_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("trade_proposals.id", ondelete="RESTRICT"),
        nullable=True,
    )
    outcome: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    strategy: Mapped[Strategy | None] = relationship(back_populates="market_memory_events")
    trade_proposal: Mapped[TradeProposal | None] = relationship(
        back_populates="market_memory_events",
    )
