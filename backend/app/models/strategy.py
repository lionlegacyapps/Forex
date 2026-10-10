"""Strategy ORM model — definition metadata only (no execution logic)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import StrategyStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.types import str_enum_column

if TYPE_CHECKING:
    from app.models.market_memory_event import MarketMemoryEvent
    from app.models.position import Position
    from app.models.strategy_account_assignment import StrategyAccountAssignment
    from app.models.strategy_paper_qualification import StrategyPaperQualification
    from app.models.trade_proposal import TradeProposal


class Strategy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "strategies"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_strategies_name_version"),
        CheckConstraint("btrim(name) <> ''", name="ck_strategies_name_not_blank"),
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    strategy_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="0.1.0",
        server_default="0.1.0",
    )
    status: Mapped[StrategyStatus] = mapped_column(
        str_enum_column(StrategyStatus, name="strategy_status"),
        nullable=False,
        default=StrategyStatus.DEVELOPMENT,
        server_default=StrategyStatus.DEVELOPMENT.value,
        index=True,
    )

    account_assignments: Mapped[list[StrategyAccountAssignment]] = relationship(
        back_populates="strategy",
    )
    trade_proposals: Mapped[list[TradeProposal]] = relationship(
        back_populates="strategy",
    )
    positions: Mapped[list[Position]] = relationship(
        back_populates="strategy",
    )
    market_memory_events: Mapped[list[MarketMemoryEvent]] = relationship(
        back_populates="strategy",
    )
    paper_qualifications: Mapped[list[StrategyPaperQualification]] = relationship(
        back_populates="strategy",
    )
