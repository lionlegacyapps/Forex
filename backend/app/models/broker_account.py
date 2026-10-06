"""Broker account ORM model — no API credentials stored here."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import AccountType, TradingMode
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.types import str_enum_column

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.position import Position
    from app.models.strategy_account_assignment import StrategyAccountAssignment
    from app.models.trade_proposal import TradeProposal


class BrokerAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "broker_accounts"
    __table_args__ = (
        UniqueConstraint("name", name="uq_broker_accounts_name"),
        UniqueConstraint(
            "broker",
            "external_account_id",
            name="uq_broker_accounts_broker_external_account_id",
        ),
        CheckConstraint("btrim(name) <> ''", name="ck_broker_accounts_name_not_blank"),
        CheckConstraint(
            "broker = lower(btrim(broker)) AND broker <> ''",
            name="ck_broker_accounts_broker_slug",
        ),
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    broker: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    external_account_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    account_type: Mapped[AccountType] = mapped_column(
        str_enum_column(AccountType, name="broker_account_type"),
        nullable=False,
    )
    trading_mode: Mapped[TradingMode] = mapped_column(
        str_enum_column(TradingMode, name="broker_account_trading_mode"),
        nullable=False,
        default=TradingMode.PAPER,
        server_default=TradingMode.PAPER.value,
    )
    # Fail-closed: new accounts require explicit enabling.
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    strategy_assignments: Mapped[list[StrategyAccountAssignment]] = relationship(
        back_populates="broker_account",
    )
    trade_proposals: Mapped[list[TradeProposal]] = relationship(
        back_populates="broker_account",
    )
    orders: Mapped[list[Order]] = relationship(
        back_populates="broker_account",
    )
    positions: Mapped[list[Position]] = relationship(
        back_populates="broker_account",
    )
