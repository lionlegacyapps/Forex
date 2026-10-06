"""Performance metrics V1 for backtest results.

Formulas / assumptions:
- total_return_pct = (ending_equity - starting_capital) / starting_capital * 100
- win_rate = winning_trades / number_of_trades (None if no trades)
- average_win / average_loss over closed trades only
- profit_factor = gross_wins / abs(gross_losses); None if no losses;
  infinity represented as None with warning when no losses and wins > 0
- expectancy = mean(net_pnl) across closed trades
- max_drawdown = max peak-to-trough decline on equity curve / peak
- Sharpe / Sortino: require equity curve with >= 2 periods and sample stdev > 0;
  use population of period returns; risk-free rate = 0; not annualized in V1
  when timeframe is unknown. Returns None when insufficient data.

BACKTEST PERFORMANCE DOES NOT GUARANTEE FUTURE PERFORMANCE.
"""

from __future__ import annotations

from decimal import Decimal
from statistics import mean, pstdev
from typing import Protocol

from pydantic import BaseModel, Field

from app.backtesting.portfolio import ClosedTrade


class _EquityLike(Protocol):
    @property
    def equity(self) -> Decimal: ...


class PerformanceMetrics(BaseModel):
    starting_capital: Decimal
    ending_equity: Decimal
    net_pnl: Decimal
    total_return_pct: Decimal
    number_of_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: Decimal | None = None
    average_win: Decimal | None = None
    average_loss: Decimal | None = None
    profit_factor: Decimal | None = None
    max_drawdown: Decimal | None = None
    max_drawdown_pct: Decimal | None = None
    expectancy: Decimal | None = None
    sharpe_ratio: Decimal | None = None
    sortino_ratio: Decimal | None = None
    warnings: list[str] = Field(default_factory=list)


def calculate_metrics(
    *,
    starting_capital: Decimal,
    ending_equity: Decimal,
    trades: list[ClosedTrade],
    equity_curve: list[_EquityLike],
) -> PerformanceMetrics:
    warnings: list[str] = []
    net_pnl = ending_equity - starting_capital
    if starting_capital == 0:
        total_return_pct = Decimal("0")
        warnings.append("starting_capital is zero; total_return_pct set to 0")
    else:
        total_return_pct = (net_pnl / starting_capital) * Decimal("100")

    n = len(trades)
    wins = [t for t in trades if t.net_pnl > 0]
    losses = [t for t in trades if t.net_pnl < 0]
    flats = [t for t in trades if t.net_pnl == 0]

    win_rate: Decimal | None
    if n == 0:
        win_rate = None
        warnings.append("no closed trades; win_rate undefined")
    else:
        win_rate = (Decimal(len(wins)) / Decimal(n)) * Decimal("100")

    average_win = (
        Decimal(str(mean([float(t.net_pnl) for t in wins]))) if wins else None
    )
    average_loss = (
        Decimal(str(mean([float(t.net_pnl) for t in losses]))) if losses else None
    )

    gross_wins = sum((t.net_pnl for t in wins), Decimal("0"))
    gross_losses = sum((t.net_pnl for t in losses), Decimal("0"))
    profit_factor: Decimal | None
    if gross_losses == 0:
        if gross_wins > 0:
            profit_factor = None
            warnings.append("profit_factor undefined (no losing trades)")
        else:
            profit_factor = None
            if n:
                warnings.append("profit_factor undefined (no wins or losses)")
    else:
        profit_factor = gross_wins / abs(gross_losses)

    expectancy: Decimal | None
    if n == 0:
        expectancy = None
    else:
        expectancy = sum((t.net_pnl for t in trades), Decimal("0")) / Decimal(n)

    max_dd, max_dd_pct = _max_drawdown(equity_curve)
    if max_dd is None and equity_curve:
        warnings.append("max_drawdown undefined (insufficient equity points)")

    sharpe = _sharpe(equity_curve)
    sortino = _sortino(equity_curve)
    if sharpe is None and len(equity_curve) >= 2:
        warnings.append("sharpe_ratio undefined (zero variance or insufficient data)")
    if sortino is None and len(equity_curve) >= 2:
        warnings.append("sortino_ratio undefined (no downside variance or insufficient data)")

    _ = flats  # counted in n but neither win nor loss

    return PerformanceMetrics(
        starting_capital=starting_capital,
        ending_equity=ending_equity,
        net_pnl=net_pnl,
        total_return_pct=total_return_pct,
        number_of_trades=n,
        winning_trades=len(wins),
        losing_trades=len(losses),
        win_rate=win_rate,
        average_win=average_win,
        average_loss=average_loss,
        profit_factor=profit_factor,
        max_drawdown=max_dd,
        max_drawdown_pct=max_dd_pct,
        expectancy=expectancy,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        warnings=warnings,
    )


def _max_drawdown(
    curve: list[_EquityLike],
) -> tuple[Decimal | None, Decimal | None]:
    if len(curve) < 2:
        return None, None
    peak = curve[0].equity
    max_dd = Decimal("0")
    max_dd_pct = Decimal("0")
    for pt in curve:
        if pt.equity > peak:
            peak = pt.equity
        dd = peak - pt.equity
        if dd > max_dd:
            max_dd = dd
            max_dd_pct = (dd / peak * Decimal("100")) if peak != 0 else Decimal("0")
    return max_dd, max_dd_pct


def _period_returns(curve: list[_EquityLike]) -> list[float]:
    rets: list[float] = []
    for i in range(1, len(curve)):
        prev = curve[i - 1].equity
        if prev == 0:
            continue
        rets.append(float((curve[i].equity - prev) / prev))
    return rets


def _sharpe(curve: list[_EquityLike]) -> Decimal | None:
    rets = _period_returns(curve)
    if len(rets) < 2:
        return None
    mu = mean(rets)
    sigma = pstdev(rets)
    if sigma == 0:
        return None
    return Decimal(str(mu / sigma))


def _sortino(curve: list[_EquityLike]) -> Decimal | None:
    rets = _period_returns(curve)
    if len(rets) < 2:
        return None
    mu = mean(rets)
    downside = [r for r in rets if r < 0]
    if len(downside) < 1:
        return None
    # Downside deviation vs 0 target
    dd = pstdev(downside) if len(downside) > 1 else abs(downside[0])
    if dd == 0:
        return None
    return Decimal(str(mu / dd))
