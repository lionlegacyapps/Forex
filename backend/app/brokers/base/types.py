"""Shared broker domain types (no provider-specific logic)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(StrEnum):
    NEW = "new"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class TimeInForce(StrEnum):
    DAY = "day"
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"


class OrderRequest(BaseModel):
    """Normalized order request passed into a broker adapter."""

    symbol: str
    side: OrderSide
    quantity: Decimal
    order_type: OrderType
    time_in_force: TimeInForce = TimeInForce.DAY
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    client_order_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Order(BaseModel):
    id: str
    client_order_id: str | None = None
    symbol: str
    side: OrderSide
    quantity: Decimal
    filled_quantity: Decimal = Decimal("0")
    order_type: OrderType
    status: OrderStatus
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    average_fill_price: Decimal | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class Position(BaseModel):
    symbol: str
    quantity: Decimal
    average_entry_price: Decimal | None = None
    market_value: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class Balance(BaseModel):
    cash: Decimal
    equity: Decimal | None = None
    currency: str = "USD"
    raw: dict[str, Any] = Field(default_factory=dict)


class BuyingPower(BaseModel):
    buying_power: Decimal
    currency: str = "USD"
    raw: dict[str, Any] = Field(default_factory=dict)


class Quote(BaseModel):
    symbol: str
    bid: Decimal | None = None
    ask: Decimal | None = None
    last: Decimal | None = None
    timestamp: datetime | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class Bar(BaseModel):
    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class Trade(BaseModel):
    id: str
    order_id: str | None = None
    symbol: str
    side: OrderSide
    quantity: Decimal
    price: Decimal
    timestamp: datetime | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class ModifyOrderRequest(BaseModel):
    quantity: Decimal | None = None
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    time_in_force: TimeInForce | None = None
