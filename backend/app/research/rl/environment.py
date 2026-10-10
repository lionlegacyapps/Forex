"""Minimal offline trading research environment (FinRL-X inspired).

Deterministic reset/step. Chronological observations only.
No broker API. No live market execution. No gymnasium/torch dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import IntEnum
from typing import Any

from pydantic import BaseModel, Field

from app.market_data.models import Bar
from app.research.data import ResearchBarFrame, bars_to_research_frame


class Action(IntEnum):
    HOLD = 0
    BUY = 1
    SELL = 2


class OfflineTradingEnvConfig(BaseModel):
    starting_cash: Decimal = Field(default=Decimal("100000"))
    trade_quantity: Decimal = Field(default=Decimal("1"))
    max_position_qty: Decimal = Field(default=Decimal("10"))
    commission_per_share: Decimal = Field(default=Decimal("0"))
    slippage_bps: Decimal = Field(default=Decimal("0"))
    lookback: int = 5


@dataclass
class Observation:
    index: int
    timestamp: datetime
    symbol: str
    close: Decimal
    returns_1: Decimal | None
    momentum: Decimal | None
    position_qty: Decimal
    cash: Decimal
    equity: Decimal

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "close": str(self.close),
            "returns_1": None if self.returns_1 is None else str(self.returns_1),
            "momentum": None if self.momentum is None else str(self.momentum),
            "position_qty": str(self.position_qty),
            "cash": str(self.cash),
            "equity": str(self.equity),
        }


@dataclass
class StepResult:
    observation: Observation
    reward: Decimal
    terminated: bool
    truncated: bool
    info: dict[str, Any] = field(default_factory=dict)


@dataclass
class EpisodeResult:
    rewards: list[Decimal]
    actions: list[Action]
    timestamps: list[datetime]
    equities: list[Decimal]
    total_reward: Decimal
    ending_equity: Decimal
    ending_cash: Decimal
    ending_position: Decimal
    total_costs: Decimal
    infos: list[dict[str, Any]] = field(default_factory=list)


class OfflineTradingEnv:
    """Point-in-time single-symbol offline trading environment."""

    def __init__(
        self,
        bars: list[Bar] | ResearchBarFrame,
        config: OfflineTradingEnvConfig | None = None,
    ) -> None:
        self.config = config or OfflineTradingEnvConfig()
        if isinstance(bars, ResearchBarFrame):
            self.frame = bars
        else:
            self.frame = bars_to_research_frame(bars)
        if len(self.frame.rows) < self.config.lookback + 2:
            raise ValueError("insufficient bars for environment")
        self._i = 0
        self._cash = self.config.starting_cash
        self._qty = Decimal("0")
        self._avg_entry = Decimal("0")
        self._total_costs = Decimal("0")
        self._terminated = False

    @property
    def symbol(self) -> str:
        return self.frame.symbol

    def reset(self) -> Observation:
        self._i = self.config.lookback  # first actionable index with history
        self._cash = self.config.starting_cash
        self._qty = Decimal("0")
        self._avg_entry = Decimal("0")
        self._total_costs = Decimal("0")
        self._terminated = False
        return self._observe()

    def step(self, action: Action | int) -> StepResult:
        if self._terminated:
            raise RuntimeError("episode already terminated; call reset()")
        action = Action(int(action))
        row = self.frame.rows[self._i]
        price = self._fill_price(row.close, action)
        prev_equity = self._equity(row.close)
        info: dict[str, Any] = {"action": action.name, "fill_price": str(price)}

        traded = Decimal("0")
        if action == Action.BUY:
            room = self.config.max_position_qty - self._qty
            qty = min(self.config.trade_quantity, room)
            if qty > 0:
                cost = self._trade_cost(qty)
                notional = price * qty
                if self._cash >= notional + cost:
                    self._cash -= notional + cost
                    new_qty = self._qty + qty
                    if self._qty > 0:
                        self._avg_entry = (
                            (self._avg_entry * self._qty) + (price * qty)
                        ) / new_qty
                    else:
                        self._avg_entry = price
                    self._qty = new_qty
                    self._total_costs += cost
                    traded = qty
                else:
                    info["rejected"] = "insufficient_cash"
            else:
                info["rejected"] = "max_position"
        elif action == Action.SELL:
            qty = min(self.config.trade_quantity, self._qty)
            if qty > 0:
                cost = self._trade_cost(qty)
                self._cash += price * qty - cost
                self._qty -= qty
                self._total_costs += cost
                traded = -qty
                if self._qty == 0:
                    self._avg_entry = Decimal("0")
            else:
                info["rejected"] = "flat"

        info["traded_qty"] = str(traded)
        # Advance time after action (observation at next bar; no future fill leakage)
        self._i += 1
        terminated = self._i >= len(self.frame.rows) - 1
        if terminated:
            self._terminated = True
        obs = self._observe()
        reward = obs.equity - prev_equity
        info["equity"] = str(obs.equity)
        info["costs_total"] = str(self._total_costs)
        return StepResult(
            observation=obs,
            reward=reward,
            terminated=terminated,
            truncated=False,
            info=info,
        )

    def _fill_price(self, close: Decimal, action: Action) -> Decimal:
        if self.config.slippage_bps == 0 or action == Action.HOLD:
            return close
        frac = self.config.slippage_bps / Decimal("10000")
        if action == Action.BUY:
            return close * (Decimal("1") + frac)
        if action == Action.SELL:
            return close * (Decimal("1") - frac)
        return close

    def _trade_cost(self, qty: Decimal) -> Decimal:
        return self.config.commission_per_share * abs(qty)

    def _equity(self, mark: Decimal) -> Decimal:
        return self._cash + self._qty * mark

    def _observe(self) -> Observation:
        # Clamp index for terminal observation
        idx = min(self._i, len(self.frame.rows) - 1)
        row = self.frame.rows[idx]
        closes = self.frame.closes
        returns_1: Decimal | None = None
        if idx >= 1 and closes[idx - 1] != 0:
            returns_1 = closes[idx] / closes[idx - 1] - Decimal("1")
        momentum: Decimal | None = None
        lb = self.config.lookback
        if idx >= lb:
            window = closes[idx - lb : idx]  # prior only
            mean = sum(window, Decimal("0")) / Decimal(lb)
            if mean != 0:
                momentum = closes[idx] / mean - Decimal("1")
        return Observation(
            index=idx,
            timestamp=row.timestamp,
            symbol=self.frame.symbol,
            close=row.close,
            returns_1=returns_1,
            momentum=momentum,
            position_qty=self._qty,
            cash=self._cash,
            equity=self._equity(row.close),
        )
