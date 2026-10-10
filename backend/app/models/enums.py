"""Application-level enumerations for the trading schema.

Stored as VARCHAR with CHECK constraints (native_enum=False) so future
value additions do not require fragile PostgreSQL ALTER TYPE migrations.
"""

from __future__ import annotations

from enum import StrEnum


class TradingMode(StrEnum):
    PAPER = "paper"
    LIVE = "live"


class AccountType(StrEnum):
    CASH = "cash"
    MARGIN = "margin"
    FUTURES = "futures"
    OTHER = "other"


class StrategyStatus(StrEnum):
    DEVELOPMENT = "development"
    BACKTESTING = "backtesting"
    PAPER = "paper"
    LIVE_ELIGIBLE = "live_eligible"
    PAUSED = "paused"
    RETIRED = "retired"


class QualificationState(StrEnum):
    """Paper qualification workflow states (approval ≠ execution)."""

    DRAFT = "draft"
    EVALUATION_REQUIRED = "evaluation_required"
    EVALUATED = "evaluated"
    REVIEW_REQUIRED = "review_required"
    APPROVED_FOR_PAPER = "approved_for_paper"
    REJECTED = "rejected"
    REVOKED = "revoked"
    EXPIRED = "expired"


class ApprovalScope(StrEnum):
    """Approval scope — live is intentionally absent."""

    PAPER_ONLY = "paper_only"


class PaperSessionState(StrEnum):
    CREATED = "created"
    READY = "ready"
    RUNNING = "running"
    PAUSING = "pausing"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class PaperSessionExecutionMode(StrEnum):
    DRY_RUN = "dry_run"
    PAPER_EXECUTE = "paper_execute"


class PaperExecutionConsentState(StrEnum):
    """Session-scoped PAPER_EXECUTE authorization lifecycle."""

    GRANTED = "granted"
    REVOKED = "revoked"
    EXPIRED = "expired"
    CONSUMED = "consumed"


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


class ProposalSource(StrEnum):
    STRATEGY = "strategy"
    AI = "ai"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    MANUAL = "manual"
    EXTERNAL = "external"


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
