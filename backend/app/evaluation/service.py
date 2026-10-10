"""StrategyEvaluationService — offline evaluation, comparison, regime analysis.

Never enables strategies, brokers, or order submission.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.backtesting.engine import BacktestEngine
from app.backtesting.historical import HistoricalMarketDataProvider
from app.backtesting.result import BacktestResult
from app.evaluation.attribution import attribute_trades, regime_performance
from app.evaluation.comparison import compare_evaluations
from app.evaluation.evidence import assert_no_auto_promotion, collect_evaluation_warnings
from app.evaluation.models import (
    ResearchProvenance,
    SplitRole,
    StrategyComparisonReport,
    StrategyEvaluationRecord,
    build_dataset_identity,
    evaluation_id_from_inputs,
)
from app.evaluation.regimes import RegimeClassifierConfig, classify_market_context
from app.market_data.models import Bar
from app.strategies.protocol import Strategy


class StrategyEvaluationService:
    """Evaluate and compare strategies on identical historical datasets."""

    def __init__(
        self,
        *,
        regime_config: RegimeClassifierConfig | None = None,
        min_warmup_bars: int = 40,
    ) -> None:
        self.regime_config = regime_config or RegimeClassifierConfig()
        self.min_warmup_bars = min_warmup_bars
        self._broker_orders_created = 0

    @property
    def broker_orders_created(self) -> int:
        return self._broker_orders_created

    def evaluate_backtest_result(
        self,
        result: BacktestResult,
        bars: list[Bar],
        *,
        research: ResearchProvenance | None = None,
        split_role: SplitRole = SplitRole.FULL_SAMPLE,
        evaluated_at: datetime | None = None,
        research_source: str | None = None,
    ) -> StrategyEvaluationRecord:
        symbol = (result.symbols[0] if result.symbols else bars[0].symbol).upper()
        dataset = build_dataset_identity(bars, symbol=symbol, timeframe=result.timeframe)
        eid, cfg_hash = evaluation_id_from_inputs(
            strategy_id=result.strategy_id,
            strategy_version=result.strategy_version,
            parameters=result.parameters,
            dataset=dataset,
            execution_assumptions=result.execution_assumptions,
            cost_assumptions=result.cost_assumptions,
        )
        attributions = attribute_trades(
            result,
            bars,
            config=self.regime_config,
            research_source=research_source,
        )
        breakdown = regime_performance(attributions)

        warmup_incomplete = len(bars) < self.min_warmup_bars
        if bars:
            # Probe last bar context for warmup flag
            snap = classify_market_context(
                bars,
                as_of_index=len(bars) - 1,
                timeframe=result.timeframe,
                config=self.regime_config,
            )
            warmup_incomplete = warmup_incomplete or (not snap.warmup_complete)

        warnings, limitations = collect_evaluation_warnings(
            result=result,
            regime_breakdown=breakdown,
            split_role=split_role,
            cost_assumptions=result.cost_assumptions or {},
            warmup_incomplete=warmup_incomplete,
            missing_market_data=len(bars) == 0,
            lookahead_risk=False,
        )
        # Merge backtest warnings
        for w in result.warnings:
            if w not in warnings:
                warnings.append(w)
        for w in result.metrics.warnings:
            if w not in warnings:
                warnings.append(w)

        record = StrategyEvaluationRecord(
            evaluation_id=eid,
            strategy_id=result.strategy_id,
            strategy_name=result.strategy_name,
            strategy_version=result.strategy_version,
            configuration_hash=cfg_hash,
            parameters=dict(result.parameters or {}),
            dataset=dataset,
            execution_assumptions=dict(result.execution_assumptions or {}),
            cost_assumptions=dict(result.cost_assumptions or {}),
            research=research or ResearchProvenance(),
            evaluated_at=evaluated_at or datetime.now(UTC),
            split_role=split_role,
            metrics=result.metrics,
            attributions=attributions,
            regime_breakdown=breakdown,
            warnings=warnings,
            limitations=limitations,
            paper_eligible=False,
            promotion_blocked=True,
        )
        assert_no_auto_promotion(record)
        return record

    def run_and_evaluate(
        self,
        *,
        strategy: Strategy,
        provider: HistoricalMarketDataProvider,
        symbols: list[str],
        timeframe: str,
        start: datetime | None = None,
        end: datetime | None = None,
        parameters: dict[str, Any] | None = None,
        starting_capital: Any = None,
        research: ResearchProvenance | None = None,
        split_role: SplitRole = SplitRole.FULL_SAMPLE,
        costs: Any = None,
        bars: list[Bar] | None = None,
    ) -> StrategyEvaluationRecord:
        from decimal import Decimal

        from app.backtesting.costs import BacktestCostModel

        eng = BacktestEngine(
            provider,
            costs=costs if costs is not None else BacktestCostModel(),
        )
        kwargs: dict[str, Any] = {
            "symbols": symbols,
            "timeframe": timeframe,
            "start": start,
            "end": end,
            "parameters": parameters,
        }
        if starting_capital is not None:
            kwargs["starting_capital"] = Decimal(str(starting_capital))
        result = eng.run(strategy, **kwargs)
        assert self._broker_orders_created == 0
        if bars is None:
            bars = provider.get_bars(symbols[0], timeframe, start, end)
        return self.evaluate_backtest_result(
            result,
            bars,
            research=research,
            split_role=split_role,
        )

    def compare(
        self,
        records: list[StrategyEvaluationRecord],
    ) -> StrategyComparisonReport:
        return compare_evaluations(records)

    def reproduce_identity(
        self,
        result: BacktestResult,
        bars: list[Bar],
    ) -> str:
        """Return evaluation_id; identical inputs → identical id (ignores timestamp)."""
        symbol = (result.symbols[0] if result.symbols else bars[0].symbol).upper()
        dataset = build_dataset_identity(bars, symbol=symbol, timeframe=result.timeframe)
        eid, _ = evaluation_id_from_inputs(
            strategy_id=result.strategy_id,
            strategy_version=result.strategy_version,
            parameters=result.parameters,
            dataset=dataset,
            execution_assumptions=result.execution_assumptions,
            cost_assumptions=result.cost_assumptions,
        )
        return eid
