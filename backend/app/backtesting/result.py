"""Normalized BacktestResult — serializable for future API/UI."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.backtesting.metrics import PerformanceMetrics


class EquityPoint(BaseModel):
    timestamp: datetime
    equity: Decimal
    cash: Decimal
    unrealized_pnl: Decimal


class BacktestTradeRecord(BaseModel):
    strategy_id: str
    strategy_version: str
    symbol: str
    side: str
    entry_time: datetime
    entry_price: Decimal
    exit_time: datetime
    exit_price: Decimal
    quantity: Decimal
    gross_pnl: Decimal
    costs: Decimal
    net_pnl: Decimal
    exit_reason: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class BacktestResult(BaseModel):
    strategy_id: str
    strategy_name: str
    strategy_version: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    start: datetime | None = None
    end: datetime | None = None
    symbols: list[str] = Field(default_factory=list)
    timeframe: str
    starting_capital: Decimal
    ending_equity: Decimal
    metrics: PerformanceMetrics
    trades: list[BacktestTradeRecord] = Field(default_factory=list)
    equity_curve: list[EquityPoint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    execution_assumptions: dict[str, Any] = Field(default_factory=dict)
    cost_assumptions: dict[str, Any] = Field(default_factory=dict)

    def to_serializable_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
