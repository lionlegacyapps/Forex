"""Application-level enumerations for the Version 1 trading schema.

Stored as VARCHAR with CHECK constraints (native_enum=False) so future
value additions do not require fragile PostgreSQL ALTER TYPE migrations.
"""

from __future__ import annotations

from enum import StrEnum


class TradingMode(StrEnum):
    PAPER = "paper"
    LIVE = "live"


class StrategyStatus(StrEnum):
    DEVELOPMENT = "development"
    BACKTESTING = "backtesting"
    PAPER = "paper"
    LIVE_ELIGIBLE = "live_eligible"
    PAUSED = "paused"
    RETIRED = "retired"


class TradeSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class TimeInForce(StrEnum):
    DAY = "day"
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"


class TradeProposalStatus(StrEnum):
    PENDING = "pending"
    RISK_REJECTED = "risk_rejected"
    RISK_APPROVED = "risk_approved"
    VALIDATION_REJECTED = "validation_rejected"
    VALIDATED = "validated"
    ROUTED = "routed"
    SUBMITTED = "submitted"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OrderStatus(StrEnum):
    NEW = "new"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class PositionStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    FLATTENING = "flattening"


class RiskScopeType(StrEnum):
    GLOBAL = "global"
    BROKER_ACCOUNT = "broker_account"
    STRATEGY = "strategy"
    STRATEGY_ACCOUNT = "strategy_account"


class AssetClass(StrEnum):
    FOREX = "forex"
    EQUITY = "equity"
    FUTURES = "futures"
    CRYPTO = "crypto"
    OPTION = "option"
    OTHER = "other"
