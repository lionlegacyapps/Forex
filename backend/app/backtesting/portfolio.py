"""Backtest portfolio state — cash, positions, P&L (Decimal)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from app.backtesting.execution_model import SimulatedFill
from app.models.enums import TradeSide
from app.strategies.context import StrategyPositionView
from app.strategies.decision import DecisionAction


@dataclass
class OpenPosition:
    symbol: str
    quantity: Decimal  # signed: +long, -short
    average_entry_price: Decimal
    entry_time: datetime
    entry_costs: Decimal = Decimal("0")
    strategy_id: str = ""
    strategy_version: str = ""

    @property
    def is_long(self) -> bool:
        return self.quantity > 0

    @property
    def is_short(self) -> bool:
        return self.quantity < 0


@dataclass
class ClosedTrade:
    strategy_id: str
    strategy_version: str
    symbol: str
    side: str  # "long" | "short"
    entry_time: datetime
    entry_price: Decimal
    exit_time: datetime
    exit_price: Decimal
    quantity: Decimal
    gross_pnl: Decimal
    costs: Decimal
    net_pnl: Decimal
    exit_reason: str


@dataclass
class BacktestPortfolio:
    starting_capital: Decimal
    cash: Decimal
    positions: dict[str, OpenPosition] = field(default_factory=dict)
    closed_trades: list[ClosedTrade] = field(default_factory=list)
    realized_pnl: Decimal = Decimal("0")
    total_costs: Decimal = Decimal("0")
    strategy_id: str = ""
    strategy_version: str = ""

    @classmethod
    def create(
        cls,
        starting_capital: Decimal,
        *,
        strategy_id: str = "",
        strategy_version: str = "",
    ) -> BacktestPortfolio:
        return cls(
            starting_capital=starting_capital,
            cash=starting_capital,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
        )

    def position_view(self, symbol: str) -> StrategyPositionView | None:
        pos = self.positions.get(symbol)
        if pos is None:
            return StrategyPositionView(
                symbol=symbol,
                quantity=Decimal("0"),
                average_entry_price=None,
                side="flat",
            )
        side = "long" if pos.is_long else "short" if pos.is_short else "flat"
        return StrategyPositionView(
            symbol=symbol,
            quantity=pos.quantity,
            average_entry_price=pos.average_entry_price,
            side=side,
        )

    def market_value(self, marks: dict[str, Decimal]) -> Decimal:
        """Signed mark-to-market value of open positions."""
        total = Decimal("0")
        for sym, pos in self.positions.items():
            mark = marks.get(sym)
            if mark is None:
                continue
            total += pos.quantity * mark
        return total

    def mark_unrealized(self, marks: dict[str, Decimal]) -> Decimal:
        """Unrealized P&L vs average entry (signed quantity)."""
        total = Decimal("0")
        for sym, pos in self.positions.items():
            mark = marks.get(sym)
            if mark is None:
                continue
            total += (mark - pos.average_entry_price) * pos.quantity
        return total

    def equity(self, marks: dict[str, Decimal]) -> Decimal:
        # cash already reflects entry notionals; add signed market value
        return self.cash + self.market_value(marks)

    def apply_fill(self, fill: SimulatedFill) -> ClosedTrade | None:
        """Apply a fill; return ClosedTrade if a position was fully closed."""
        signed_qty = fill.quantity if fill.side == TradeSide.BUY else -fill.quantity
        cost = fill.commission
        self.total_costs += cost
        self.cash -= cost

        # Cash impact of trade notional
        if fill.side == TradeSide.BUY:
            self.cash -= fill.price * fill.quantity
        else:
            self.cash += fill.price * fill.quantity

        existing = self.positions.get(fill.symbol)
        closed: ClosedTrade | None = None

        if existing is None or existing.quantity == 0:
            self.positions[fill.symbol] = OpenPosition(
                symbol=fill.symbol,
                quantity=signed_qty,
                average_entry_price=fill.price,
                entry_time=fill.fill_time,
                entry_costs=cost,
                strategy_id=self.strategy_id,
                strategy_version=self.strategy_version,
            )
            return None

        # Same direction → average in
        if (existing.quantity > 0 and signed_qty > 0) or (
            existing.quantity < 0 and signed_qty < 0
        ):
            total_qty = existing.quantity + signed_qty
            avg = (
                (existing.average_entry_price * abs(existing.quantity))
                + (fill.price * abs(signed_qty))
            ) / abs(total_qty)
            existing.quantity = total_qty
            existing.average_entry_price = avg
            existing.entry_costs += cost
            return None

        # Opposite direction → reduce / close / flip
        closing_qty = min(abs(existing.quantity), abs(signed_qty))
        direction = Decimal("1") if existing.quantity > 0 else Decimal("-1")
        # Long: sell closes → (exit - entry) * qty
        # Short: buy closes → (entry - exit) * qty
        if existing.is_long:
            gross = (fill.price - existing.average_entry_price) * closing_qty
            side_label = "long"
        else:
            gross = (existing.average_entry_price - fill.price) * closing_qty
            side_label = "short"

        trade_costs = existing.entry_costs * (closing_qty / abs(existing.quantity)) + cost
        # Entry cost was already deducted from cash when opened; only attribute
        # proportional entry + this fill's commission to the closed trade costs.
        net = gross - (
            existing.entry_costs * (closing_qty / abs(existing.quantity)) + fill.commission
        )
        self.realized_pnl += gross - (
            existing.entry_costs * (closing_qty / abs(existing.quantity)) + fill.commission
        )

        exit_reason = fill.rationale_code or fill.decision_action.value
        if fill.decision_action in {
            DecisionAction.EXIT_LONG,
            DecisionAction.EXIT_SHORT,
        }:
            exit_reason = fill.rationale_code or "exit"

        closed = ClosedTrade(
            strategy_id=self.strategy_id,
            strategy_version=self.strategy_version,
            symbol=fill.symbol,
            side=side_label,
            entry_time=existing.entry_time,
            entry_price=existing.average_entry_price,
            exit_time=fill.fill_time,
            exit_price=fill.price,
            quantity=closing_qty,
            gross_pnl=gross,
            costs=existing.entry_costs * (closing_qty / abs(existing.quantity))
            + fill.commission,
            net_pnl=net,
            exit_reason=exit_reason,
        )
        self.closed_trades.append(closed)

        remaining = existing.quantity + signed_qty
        if remaining == 0:
            del self.positions[fill.symbol]
        elif (existing.quantity > 0 and remaining < 0) or (
            existing.quantity < 0 and remaining > 0
        ):
            # Flip
            self.positions[fill.symbol] = OpenPosition(
                symbol=fill.symbol,
                quantity=remaining,
                average_entry_price=fill.price,
                entry_time=fill.fill_time,
                entry_costs=cost,
                strategy_id=self.strategy_id,
                strategy_version=self.strategy_version,
            )
        else:
            # Partial close
            frac_remaining = abs(remaining) / abs(existing.quantity)
            existing.entry_costs = existing.entry_costs * frac_remaining
            existing.quantity = remaining

        _ = direction
        return closed
