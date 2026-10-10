"""Walk-forward period and aggregate performance reporting."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.backtesting.metrics import PerformanceMetrics
from app.backtesting.result import BacktestResult, BacktestTradeRecord, EquityPoint
from app.evaluation.models import (
    SplitRole,
    StrategyEvaluationRecord,
)
from app.evaluation.walkforward.windows import WalkForwardWindow


class PeriodReport(BaseModel):
    role: SplitRole
    window_index: int
    evaluation: StrategyEvaluationRecord
    backtest: BacktestResult | None = None  # optional; may omit bulky curves in persistence
    net_return: Decimal
    win_rate: Decimal | None
    profit_factor: Decimal | None
    expectancy: Decimal | None
    max_drawdown: Decimal | None
    trade_count: int
    average_win: Decimal | None
    average_loss: Decimal | None
    transaction_costs: Decimal
    equity_curve: list[EquityPoint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RoleAggregate(BaseModel):
    role: SplitRole
    window_count: int
    total_trades: int
    total_net_pnl: Decimal
    # Compounded return across independent windows (product of wealth ratios)
    compounded_return_pct: Decimal | None = None
    # Trade-weighted average win rate (not simple mean of percentages)
    trade_weighted_win_rate: Decimal | None = None
    total_costs: Decimal = Decimal("0")
    max_drawdown_worst: Decimal | None = None
    warnings: list[str] = Field(default_factory=list)


def transaction_costs(trades: list[BacktestTradeRecord]) -> Decimal:
    return sum((t.costs for t in trades), Decimal("0"))


def period_report_from_evaluation(
    *,
    role: SplitRole,
    window_index: int,
    evaluation: StrategyEvaluationRecord,
    result: BacktestResult,
) -> PeriodReport:
    return PeriodReport(
        role=role,
        window_index=window_index,
        evaluation=evaluation,
        backtest=result,
        net_return=result.metrics.total_return_pct,
        win_rate=result.metrics.win_rate,
        profit_factor=result.metrics.profit_factor,
        expectancy=result.metrics.expectancy,
        max_drawdown=result.metrics.max_drawdown,
        trade_count=result.metrics.number_of_trades,
        average_win=result.metrics.average_win,
        average_loss=result.metrics.average_loss,
        transaction_costs=transaction_costs(result.trades),
        equity_curve=list(result.equity_curve),
        warnings=list(evaluation.warnings),
    )


def aggregate_role(reports: list[PeriodReport], role: SplitRole) -> RoleAggregate:
    subset = [r for r in reports if r.role == role]
    warnings: list[str] = []
    if not subset:
        return RoleAggregate(
            role=role,
            window_count=0,
            total_trades=0,
            total_net_pnl=Decimal("0"),
            warnings=["no_periods_for_role"],
        )

    # Reject naive averaging of overlapping windows
    indices = [r.window_index for r in subset]
    if len(indices) != len(set(indices)):
        warnings.append("overlapping_window_indices_in_aggregate")

    total_trades = sum(r.trade_count for r in subset)
    total_net = sum((r.evaluation.metrics.net_pnl for r in subset), Decimal("0"))
    total_costs = sum((r.transaction_costs for r in subset), Decimal("0"))

    # Compound independent windows: Π (1 + r_i) - 1
    wealth = Decimal("1")
    for r in subset:
        # total_return_pct is percent points
        wealth *= Decimal("1") + (r.net_return / Decimal("100"))
    compounded = (wealth - Decimal("1")) * Decimal("100")

    wins = 0
    for r in subset:
        m = r.evaluation.metrics
        if m.number_of_trades and m.win_rate is not None:
            wins += int(round((m.win_rate / Decimal("100")) * Decimal(m.number_of_trades)))
    tw_wr = (
        (Decimal(wins) / Decimal(total_trades)) * Decimal("100") if total_trades else None
    )

    drawdowns = [r.max_drawdown for r in subset if r.max_drawdown is not None]
    worst = max(drawdowns) if drawdowns else None

    if total_trades < 10:
        warnings.append("small_sample_aggregate")

    return RoleAggregate(
        role=role,
        window_count=len(subset),
        total_trades=total_trades,
        total_net_pnl=total_net,
        compounded_return_pct=compounded,
        trade_weighted_win_rate=tw_wr,
        total_costs=total_costs,
        max_drawdown_worst=worst,
        warnings=warnings,
    )


def compact_period_summary(report: PeriodReport) -> dict[str, Any]:
    """Persistence-friendly summary without equity curves / full attributions."""
    return {
        "role": report.role.value,
        "window_index": report.window_index,
        "evaluation_id": report.evaluation.evaluation_id,
        "net_return_pct": str(report.net_return),
        "win_rate": None if report.win_rate is None else str(report.win_rate),
        "profit_factor": None if report.profit_factor is None else str(report.profit_factor),
        "expectancy": None if report.expectancy is None else str(report.expectancy),
        "max_drawdown": None if report.max_drawdown is None else str(report.max_drawdown),
        "trade_count": report.trade_count,
        "transaction_costs": str(report.transaction_costs),
        "warnings": report.warnings,
        "configuration_hash": report.evaluation.configuration_hash,
        "dataset_fingerprint": report.evaluation.dataset.fingerprint,
        "split_role": report.evaluation.split_role.value,
    }


def window_bounds_dict(window: WalkForwardWindow) -> dict[str, Any]:
    return {
        "window_index": window.window_index,
        "mode": window.mode.value,
        "train": window.train.model_dump(mode="json"),
        "validation": window.validation.model_dump(mode="json"),
        "oos": window.oos.model_dump(mode="json"),
        "configuration_hash": window.configuration_hash,
        "dataset_fingerprint": window.dataset_fingerprint,
    }
