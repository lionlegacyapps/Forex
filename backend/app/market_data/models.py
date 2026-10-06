"""Normalized market-data domain models (Decimal prices only)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field


class MarketDataAssetClass(StrEnum):
    EQUITY = "equity"
    CRYPTO = "crypto"
    FUTURES = "futures"
    OPTION = "option"
    OTHER = "other"


class Quote(BaseModel):
    symbol: str
    bid_price: Decimal | None = None
    ask_price: Decimal | None = None
    bid_size: Decimal | None = None
    ask_size: Decimal | None = None
    timestamp: datetime
    provider: str
    asset_class: MarketDataAssetClass = MarketDataAssetClass.EQUITY
    raw: dict = Field(default_factory=dict)


class Trade(BaseModel):
    symbol: str
    price: Decimal
    size: Decimal | None = None
    timestamp: datetime
    provider: str
    asset_class: MarketDataAssetClass = MarketDataAssetClass.EQUITY
    raw: dict = Field(default_factory=dict)


class Bar(BaseModel):
    symbol: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None = None
    timestamp: datetime
    timeframe: str
    provider: str
    asset_class: MarketDataAssetClass = MarketDataAssetClass.EQUITY
    raw: dict = Field(default_factory=dict)


class ReferencePrice(BaseModel):
    """Resolved reference price used by Risk / Exposure (provider-agnostic)."""

    symbol: str
    price: Decimal
    timestamp: datetime
    provider: str
    source: str  # "midpoint" | "last_trade" | "simulation"
    stale: bool = False
