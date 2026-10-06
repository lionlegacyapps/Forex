"""Configurable backtest cost assumptions (commission + slippage).

Zero-cost defaults are for baseline unit tests only and do NOT represent
real trading economics.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class BacktestCostModel(BaseModel):
    """Per-fill cost assumptions."""

    commission_per_share: Decimal = Field(default=Decimal("0"))
    commission_flat: Decimal = Field(default=Decimal("0"))
    # Slippage as fraction of price (e.g. 0.001 = 10 bps) applied adversely.
    slippage_bps: Decimal = Field(default=Decimal("0"))

    @field_validator(
        "commission_per_share",
        "commission_flat",
        "slippage_bps",
        mode="before",
    )
    @classmethod
    def _to_decimal(cls, value: object) -> Decimal:
        return Decimal(str(value))

    @field_validator("commission_per_share", "commission_flat", "slippage_bps")
    @classmethod
    def _non_negative(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("cost parameters must be >= 0")
        return value

    def commission(self, quantity: Decimal) -> Decimal:
        qty = abs(quantity)
        return (self.commission_per_share * qty) + self.commission_flat

    def apply_slippage(self, price: Decimal, *, side: str) -> Decimal:
        """Apply adverse slippage. side is 'buy' or 'sell'."""
        if self.slippage_bps == 0:
            return price
        fraction = self.slippage_bps / Decimal("10000")
        if side == "buy":
            return price * (Decimal("1") + fraction)
        if side == "sell":
            return price * (Decimal("1") - fraction)
        raise ValueError(f"unknown side {side!r}")
