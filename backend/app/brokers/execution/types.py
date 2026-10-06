"""Execution submission types — require pipeline proof.

Adapters must reject submissions that lack risk/validation/routing proof.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExecutionSubmission(BaseModel):
    """Normalized order submission with mandatory pipeline preconditions."""

    model_config = ConfigDict(extra="forbid")

    # Pipeline proof — adapter must enforce these
    trade_proposal_id: uuid.UUID
    proposal_status: str  # must be "routed"
    risk_approved: bool  # must be True
    validated: bool  # must be True
    routed: bool  # must be True

    # Account gates
    broker_account_id: uuid.UUID
    broker: str  # must be "alpaca"
    trading_mode: str  # must be "paper"
    account_enabled: bool  # must be True

    # Durable identity for client_order_id / idempotency
    internal_order_id: uuid.UUID
    client_order_id: str

    # Order body
    symbol: str
    asset_class: str
    side: str
    order_type: str
    quantity: Decimal
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    time_in_force: str = "day"


class ExecutionResult(BaseModel):
    """Normalized broker accept/reject result."""

    model_config = ConfigDict(extra="forbid")

    broker_order_id: str
    client_order_id: str
    status: str
    submitted_at: datetime | None = None
    filled_quantity: Decimal = Decimal("0")
    filled_avg_price: Decimal | None = None
    recovered_existing: bool = False  # True when found via client_order_id (idempotent)
    submit_http_calls: int = 0  # POST count for this attempt (tests)
    raw_status: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
