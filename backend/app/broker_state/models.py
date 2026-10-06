"""Normalized broker account read models (external snapshots only)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BrokerAssetClass(StrEnum):
    EQUITY = "equity"
    CRYPTO = "crypto"
    OPTION = "option"
    FUTURES = "futures"
    FOREX = "forex"
    OTHER = "other"


class AccountSnapshot(BaseModel):
    """External broker account snapshot — never contains credentials."""

    model_config = ConfigDict(extra="forbid")

    broker: str
    external_account_id: str
    account_status: str
    currency: str = "USD"
    cash: Decimal
    equity: Decimal | None = None
    buying_power: Decimal | None = None
    portfolio_value: Decimal | None = None
    timestamp: datetime
    trading_blocked: bool = False
    account_blocked: bool = False
    paper_verified: bool = False
    account_number: str | None = None


class BrokerPositionSnapshot(BaseModel):
    """External broker position snapshot (not internal accounting)."""

    model_config = ConfigDict(extra="forbid")

    symbol: str
    asset_class: BrokerAssetClass = BrokerAssetClass.EQUITY
    quantity: Decimal
    side: str  # long | short
    average_entry_price: Decimal | None = None
    current_price: Decimal | None = None
    market_value: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    unrealized_pnl_percent: Decimal | None = None
    timestamp: datetime
    broker: str = "alpaca"


class BrokerOrderSnapshot(BaseModel):
    """External broker order snapshot."""

    model_config = ConfigDict(extra="forbid")

    broker_order_id: str
    symbol: str
    asset_class: BrokerAssetClass = BrokerAssetClass.EQUITY
    side: str
    order_type: str
    quantity: Decimal
    filled_quantity: Decimal = Decimal("0")
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    time_in_force: str | None = None
    status: str
    submitted_at: datetime | None = None
    filled_at: datetime | None = None
    cancelled_at: datetime | None = None
    broker: str = "alpaca"


class BrokerFillSnapshot(BaseModel):
    """External fill / trade activity snapshot."""

    model_config = ConfigDict(extra="forbid")

    activity_id: str
    broker_order_id: str | None = None
    symbol: str
    side: str | None = None
    quantity: Decimal
    price: Decimal
    timestamp: datetime
    broker: str = "alpaca"


class ReconciliationCategory(StrEnum):
    MATCH = "MATCH"
    MISSING_INTERNAL_POSITION = "MISSING_INTERNAL_POSITION"
    MISSING_BROKER_POSITION = "MISSING_BROKER_POSITION"
    POSITION_QUANTITY_MISMATCH = "POSITION_QUANTITY_MISMATCH"
    POSITION_SIDE_MISMATCH = "POSITION_SIDE_MISMATCH"
    UNKNOWN_BROKER_ORDER = "UNKNOWN_BROKER_ORDER"
    MISSING_BROKER_ORDER = "MISSING_BROKER_ORDER"
    ORDER_STATUS_MISMATCH = "ORDER_STATUS_MISMATCH"


class ReconciliationFinding(BaseModel):
    category: ReconciliationCategory
    message: str
    symbol: str | None = None
    broker_order_id: str | None = None
    internal_value: str | None = None
    broker_value: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ReconciliationReport(BaseModel):
    """Observational reconciliation result — never mutates state."""

    broker: str
    external_account_id: str | None = None
    generated_at: datetime
    findings: list[ReconciliationFinding] = Field(default_factory=list)
    mutations: int = 0  # Always 0 for V1

    @property
    def is_clean(self) -> bool:
        return all(f.category == ReconciliationCategory.MATCH for f in self.findings) or (
            len(self.findings) == 0
        )
