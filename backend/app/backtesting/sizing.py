"""Deterministic position sizing boundary for backtests.

Separates strategy direction/entry logic from capital/risk sizing.
Strategies may suggest quantity; the sizing model can override or cap it.
Real/paper execution still uses the Risk Engine separately.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

from app.strategies.decision import StrategyDecision


class SizingMode(StrEnum):
    FIXED_QUANTITY = "fixed_quantity"
    DECISION_QUANTITY = "decision_quantity"
    PERCENT_EQUITY = "percent_equity"


class BacktestSizingModel(BaseModel):
    mode: SizingMode = SizingMode.DECISION_QUANTITY
    fixed_quantity: Decimal = Field(default=Decimal("1"))
    percent_equity: Decimal = Field(default=Decimal("0.10"))
    max_quantity: Decimal | None = None

    @field_validator("fixed_quantity", "percent_equity", mode="before")
    @classmethod
    def _dec(cls, value: object) -> Decimal:
        return Decimal(str(value))

    @field_validator("fixed_quantity")
    @classmethod
    def _pos_qty(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("fixed_quantity must be positive")
        return value

    @field_validator("percent_equity")
    @classmethod
    def _pct(cls, value: Decimal) -> Decimal:
        if value <= 0 or value > 1:
            raise ValueError("percent_equity must be in (0, 1]")
        return value

    def size(
        self,
        decision: StrategyDecision,
        *,
        equity: Decimal,
        reference_price: Decimal,
    ) -> Decimal:
        if self.mode == SizingMode.FIXED_QUANTITY:
            qty = self.fixed_quantity
        elif self.mode == SizingMode.DECISION_QUANTITY:
            if decision.quantity is None or decision.quantity <= 0:
                qty = self.fixed_quantity
            else:
                qty = decision.quantity
        elif self.mode == SizingMode.PERCENT_EQUITY:
            if reference_price <= 0:
                raise ValueError("reference_price must be positive for percent sizing")
            notional = equity * self.percent_equity
            qty = (notional / reference_price).quantize(Decimal("0.0001"))
            if qty <= 0:
                qty = Decimal("0")
        else:
            raise ValueError(f"unknown sizing mode {self.mode}")

        if self.max_quantity is not None:
            qty = min(qty, self.max_quantity)
        return qty
