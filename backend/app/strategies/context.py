"""StrategyContext — normalized decision inputs without broker objects."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.market_data.models import Bar, Quote, Trade
from app.models.enums import AssetClass


class StrategyPositionView(BaseModel):
    """Strategy-scoped position snapshot (provider-agnostic)."""

    symbol: str
    quantity: Decimal
    average_entry_price: Decimal | None = None
    side: str | None = None  # "long" | "short" | "flat"
    unrealized_pnl: Decimal | None = None

    @field_validator("symbol")
    @classmethod
    def _norm_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @property
    def is_flat(self) -> bool:
        return self.quantity == 0

    @property
    def is_long(self) -> bool:
        return self.quantity > 0

    @property
    def is_short(self) -> bool:
        return self.quantity < 0


class PortfolioContextView(BaseModel):
    """Optional account/portfolio context for sizing-aware strategies."""

    cash: Decimal | None = None
    equity: Decimal | None = None
    buying_power: Decimal | None = None
    currency: str = "USD"


class StrategyContext(BaseModel):
    """Normalized inputs available to a strategy at one evaluation moment.

    Historical bars must already be lookahead-safe (no future bars).
    Broker adapters, routers, and credentials must never appear here.
    """

    symbol: str
    asset_class: AssetClass
    timestamp: datetime
    timeframe: str
    bars: list[Bar] = Field(default_factory=list)
    latest_quote: Quote | None = None
    latest_trade: Trade | None = None
    reference_price: Decimal | None = None
    position: StrategyPositionView | None = None
    portfolio: PortfolioContextView | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    strategy_id: str | None = None
    strategy_version: str | None = None

    @field_validator("symbol")
    @classmethod
    def _norm_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @property
    def bar_count(self) -> int:
        return len(self.bars)

    @property
    def current_bar(self) -> Bar | None:
        return self.bars[-1] if self.bars else None

    @property
    def closes(self) -> list[Decimal]:
        return [b.close for b in self.bars]
