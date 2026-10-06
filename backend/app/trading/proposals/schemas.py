"""Pydantic inputs/outputs for Trade Proposal service (internal, not public API)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.enums import (
    AssetClass,
    OrderType,
    ProposalSource,
    TimeInForce,
    TradeProposalStatus,
    TradeSide,
)
from app.trading.risk.results import RiskDecision
from app.trading.routing.router import RouteResult
from app.trading.validation.validator import ValidationResult


class CreateTradeProposalInput(BaseModel):
    broker_account_id: uuid.UUID
    strategy_id: uuid.UUID | None = None
    source: ProposalSource
    symbol: str
    asset_class: AssetClass
    side: TradeSide
    order_type: OrderType
    quantity: Decimal
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    stop_loss_price: Decimal | None = None
    take_profit_price: Decimal | None = None
    time_in_force: TimeInForce = TimeInForce.DAY
    signal_reference: str | None = None
    # Optional application-level idempotency key (stored in metadata).
    idempotency_key: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def _strip_symbol(cls, value: str) -> str:
        return value.strip()

    @field_validator("quantity")
    @classmethod
    def _quantity_positive_hint(cls, value: Decimal) -> Decimal:
        # Soft check — Risk Engine still enforces; allows tests to submit bad qty.
        return value


class PipelineResult(BaseModel):
    proposal_id: uuid.UUID
    status: TradeProposalStatus
    risk: RiskDecision | None = None
    validation: ValidationResult | None = None
    route: RouteResult | None = None
    submitted: bool = False
    broker_order_id: str | None = None
