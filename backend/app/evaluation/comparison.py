"""Same-dataset strategy comparison with explicit incomparability."""

from __future__ import annotations

from decimal import Decimal

from app.evaluation.models import (
    ComparisonMetric,
    StrategyComparisonReport,
    StrategyEvaluationRecord,
)


def _costs_total(record: StrategyEvaluationRecord) -> Decimal | None:
    if not record.attributions:
        return Decimal("0") if record.metrics.number_of_trades == 0 else None
    return sum((a.costs for a in record.attributions), Decimal("0"))


def compare_evaluations(
    records: list[StrategyEvaluationRecord],
) -> StrategyComparisonReport:
    if not records:
        return StrategyComparisonReport(
            comparable=False,
            reasons_not_comparable=["no_evaluations"],
            warnings=["no_evaluations"],
        )

    warnings: list[str] = []
    reasons: list[str] = []

    fingerprints = {r.dataset.fingerprint for r in records}
    symbols = {r.dataset.symbol for r in records}
    timeframes = {r.dataset.timeframe for r in records}
    exec_hashes = {
        str(sorted((r.execution_assumptions or {}).items())) for r in records
    }
    cost_hashes = {str(sorted((r.cost_assumptions or {}).items())) for r in records}
    splits = {r.split_role for r in records}

    comparable = True
    if len(fingerprints) > 1:
        comparable = False
        reasons.append("non_comparable_datasets")
        warnings.append("non_comparable_datasets")
    if len(symbols) > 1 or len(timeframes) > 1:
        comparable = False
        reasons.append("symbol_or_timeframe_mismatch")
    if len(exec_hashes) > 1:
        comparable = False
        reasons.append("execution_assumptions_mismatch")
        warnings.append("non_comparable_execution_assumptions")
    if len(cost_hashes) > 1:
        comparable = False
        reasons.append("cost_assumptions_mismatch")
        warnings.append("non_comparable_cost_assumptions")
    if len(splits) > 1:
        warnings.append("mixed_split_roles")

    metrics = [
        ComparisonMetric(
            strategy_id=r.strategy_id,
            strategy_version=r.strategy_version,
            evaluation_id=r.evaluation_id,
            net_pnl=r.metrics.net_pnl,
            total_return_pct=r.metrics.total_return_pct,
            win_rate=r.metrics.win_rate,
            profit_factor=r.metrics.profit_factor,
            expectancy=r.metrics.expectancy,
            max_drawdown=r.metrics.max_drawdown,
            max_drawdown_pct=r.metrics.max_drawdown_pct,
            number_of_trades=r.metrics.number_of_trades,
            average_win=r.metrics.average_win,
            average_loss=r.metrics.average_loss,
            costs_total=_costs_total(r),
        )
        for r in records
    ]

    # Surface zero-trade and small samples without inventing ranks
    for r in records:
        if r.metrics.number_of_trades == 0:
            warnings.append(f"zero_trades:{r.strategy_id}")
        if "small_sample_size" in r.warnings:
            warnings.append(f"small_sample:{r.strategy_id}")

    return StrategyComparisonReport(
        comparable=comparable,
        dataset_fingerprint=next(iter(fingerprints)) if len(fingerprints) == 1 else None,
        reasons_not_comparable=reasons,
        metrics=metrics,
        warnings=warnings,
    )
