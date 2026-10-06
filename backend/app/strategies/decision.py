"""Normalized StrategyDecision — strategies never create broker orders."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import AssetClass, OrderType, TimeInForce, TradeSide


class DecisionAction(StrEnum):
    """High-level strategy intent (direction / lifecycle)."""

    NO_ACTION = "no_action"
    ENTER_LONG = "enter_long"
    ENTER_SHORT = "enter_short"
    EXIT_LONG = "exit_long"
    EXIT_SHORT = "exit_short"


class StrategyDecision(BaseModel):
    """Provider-agnostic decision emitted by a strategy.

    Strategies stop here. Conversion to TradeProposal is handled by
    StrategyProposalAdapter; broker submission is never available to strategies.
    """

    action: DecisionAction = DecisionAction.NO_ACTION
    symbol: str | None = None
    asset_class: AssetClass | None = None
    side: TradeSide | None = None
    quantity: Decimal | None = None
    order_type: OrderType = OrderType.MARKET
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    stop_loss_price: Decimal | None = None
    take_profit_price: Decimal | None = None
    time_in_force: TimeInForce = TimeInForce.DAY
    rationale_code: str | None = None
    rationale: str | None = None
    signal_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip().upper()
        return stripped or None

    @model_validator(mode="after")
    def _validate_action_fields(self) -> StrategyDecision:
        if self.action == DecisionAction.NO_ACTION:
            return self
        if not self.symbol:
            raise ValueError(f"{self.action} requires symbol")
        if self.asset_class is None:
            raise ValueError(f"{self.action} requires asset_class")
        if self.side is None:
            self.side = _default_side(self.action)
        if self.quantity is not None and self.quantity <= 0:
            raise ValueError("quantity must be positive when provided")
        if self.order_type == OrderType.LIMIT and self.limit_price is None:
            raise ValueError("limit order requires limit_price")
        if self.order_type == OrderType.STOP and self.stop_price is None:
            raise ValueError("stop order requires stop_price")
        if self.order_type == OrderType.STOP_LIMIT and (
            self.stop_price is None or self.limit_price is None
        ):
            raise ValueError("stop_limit order requires stop_price and limit_price")
        return self

    @property
    def is_actionable(self) -> bool:
        return self.action != DecisionAction.NO_ACTION


def _default_side(action: DecisionAction) -> TradeSide:
    if action in {DecisionAction.ENTER_LONG, DecisionAction.EXIT_SHORT}:
        return TradeSide.BUY
    if action in {DecisionAction.ENTER_SHORT, DecisionAction.EXIT_LONG}:
        return TradeSide.SELL
    raise ValueError(f"No default side for {action}")


def no_action(*, rationale_code: str | None = None, rationale: str | None = None) -> StrategyDecision:
    return StrategyDecision(
        action=DecisionAction.NO_ACTION,
        rationale_code=rationale_code,
        rationale=rationale,
    )
