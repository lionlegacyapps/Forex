"""Walk-forward evaluation harness — fixed parameters, independent windows."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.backtesting.costs import BacktestCostModel
from app.backtesting.engine import BacktestEngine
from app.backtesting.historical import InMemoryHistoricalMarketDataProvider
from app.backtesting.metrics import calculate_metrics
from app.backtesting.portfolio import ClosedTrade
from app.backtesting.result import BacktestResult, BacktestTradeRecord, EquityPoint
from app.evaluation.hashing import configuration_hash, evaluation_identity, sha256_hex, canonical_json
from app.evaluation.models import ResearchProvenance, SplitRole
from app.evaluation.research_adapters import (
    finrlx_baseline_provenance,
    qlib_momentum_provenance,
    reference_strategy_provenance,
)
from app.evaluation.service import StrategyEvaluationService
from app.evaluation.walkforward.errors import (
    DataLeakageError,
    UnsupportedStrategyError,
    WalkForwardError,
)
from app.evaluation.walkforward.gating import ScoreWindowGateStrategy
from app.evaluation.walkforward.leakage import (
    assert_period_isolation,
    require_purge_or_reject,
)
from app.evaluation.walkforward.reporting import (
    PeriodReport,
    RoleAggregate,
    aggregate_role,
    compact_period_summary,
    period_report_from_evaluation,
    window_bounds_dict,
)
from app.evaluation.walkforward.robustness import RobustnessReport, analyze_robustness
from app.evaluation.walkforward.windows import (
    EvaluationPeriod,
    SplitSpec,
    WalkForwardWindow,
    generate_windows,
    window_config_hash,
)
from app.market_data.models import Bar
from app.strategies.protocol import Strategy

COMPATIBLE_STRATEGY_IDS = frozenset(
    {
        "sma_crossover",
        "rsi_macd_trend",
        "qlib_momentum_external",
        "qlib_inspired_momentum",
        "qlib_factor_signal",
    }
)

FINRLX_COMPAT_NOTES = [
    "FinRL-X baseline policy may be evaluated only as a fixed offline policy.",
    "Results must not be presented as trained reinforcement-learning performance.",
]


class WalkForwardResult(BaseModel):
    harness_id: str
    strategy_id: str
    strategy_version: str
    configuration_hash: str
    dataset_fingerprint: str
    symbol: str
    timeframe: str
    mode: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    windows: list[dict[str, Any]] = Field(default_factory=list)
    period_reports: list[PeriodReport] = Field(default_factory=list)
    aggregates: list[RoleAggregate] = Field(default_factory=list)
    robustness: RobustnessReport | None = None
    research: ResearchProvenance = Field(default_factory=ResearchProvenance)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    paper_eligible: bool = False
    promotion_blocked: bool = True
    broker_orders_created: int = 0
    evaluated_at: datetime

    def to_serializable_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def persistence_summary(self) -> dict[str, Any]:
        """Compact payload for Market Memory (no equity curves)."""
        return {
            "harness_id": self.harness_id,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "configuration_hash": self.configuration_hash,
            "dataset_fingerprint": self.dataset_fingerprint,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "mode": self.mode,
            "parameters": self.parameters,
            "windows": self.windows,
            "period_summaries": [
                compact_period_summary(
                    PeriodReport(
                        role=r.role,
                        window_index=r.window_index,
                        evaluation=r.evaluation,
                        net_return=r.net_return,
                        win_rate=r.win_rate,
                        profit_factor=r.profit_factor,
                        expectancy=r.expectancy,
                        max_drawdown=r.max_drawdown,
                        trade_count=r.trade_count,
                        average_win=r.average_win,
                        average_loss=r.average_loss,
                        transaction_costs=r.transaction_costs,
                        warnings=r.warnings,
                    )
                )
                for r in self.period_reports
            ],
            "aggregates": [a.model_dump(mode="json") for a in self.aggregates],
            "robustness": None if self.robustness is None else self.robustness.model_dump(mode="json"),
            "research": self.research.model_dump(mode="json"),
            "warnings": self.warnings,
            "limitations": self.limitations,
            "paper_eligible": False,
            "promotion_blocked": True,
        }


class WalkForwardHarness:
    """Deterministic chronological walk-forward evaluation (no optimization)."""

    def __init__(
        self,
        *,
        evaluation_service: StrategyEvaluationService | None = None,
        starting_capital: Decimal = Decimal("100000"),
        costs: BacktestCostModel | None = None,
    ) -> None:
        self.evaluation_service = evaluation_service or StrategyEvaluationService()
        self.starting_capital = starting_capital
        self.costs = costs or BacktestCostModel()
        self._broker_orders_created = 0

    @property
    def broker_orders_created(self) -> int:
        return self._broker_orders_created

    def run(
        self,
        *,
        strategy: Strategy,
        bars: list[Bar],
        timeframe: str,
        spec: SplitSpec,
        parameters: dict[str, Any] | None = None,
        research: ResearchProvenance | None = None,
        symbol: str | None = None,
        evaluated_at: datetime | None = None,
        allow_finrlx_baseline: bool = False,
    ) -> WalkForwardResult:
        if not bars:
            raise WalkForwardError("bars required", code="empty_bars")
        sym = (symbol or bars[0].symbol).strip().upper()
        params = strategy.validate_parameters(parameters or {})
        research = research or self._default_provenance(strategy)

        self._assert_strategy_compatible(strategy, allow_finrlx_baseline=allow_finrlx_baseline)

        windows = generate_windows(
            bars,
            spec=spec,
            symbol=sym,
            timeframe=timeframe,
            strategy_id=strategy.strategy_id,
            strategy_version=strategy.version,
            parameters=params,
        )

        period_reports: list[PeriodReport] = []
        warnings: list[str] = []
        limitations: list[str] = [
            "Walk-forward V1 uses fixed parameters across windows (no optimization).",
            "Independent windows reset capital and positions; no carry-over.",
            "FULL_SAMPLE / TRAIN metrics are not OUT_OF_SAMPLE evidence.",
            "BACKTEST PERFORMANCE DOES NOT GUARANTEE FUTURE PERFORMANCE.",
            "Evaluation never enables strategies, brokers, or order submission.",
        ]

        for window in windows:
            assert_period_isolation(window)
            self._check_label_leakage(window, bars)
            for period in (window.train, window.validation, window.oos):
                report = self._evaluate_period(
                    strategy=strategy,
                    bars=bars,
                    window=window,
                    period=period,
                    parameters=params,
                    research=research,
                    timeframe=timeframe,
                    symbol=sym,
                )
                period_reports.append(report)
                for w in report.warnings:
                    if w not in warnings:
                        warnings.append(w)

        aggregates = [
            aggregate_role(period_reports, SplitRole.TRAIN),
            aggregate_role(period_reports, SplitRole.VALIDATION),
            aggregate_role(period_reports, SplitRole.OUT_OF_SAMPLE),
        ]
        zero_cost = (
            str(self.costs.slippage_bps) == "0"
            and str(self.costs.commission_per_share) == "0"
            and str(self.costs.commission_flat) == "0"
        )
        robustness = analyze_robustness(
            period_reports,
            oos_aggregate=aggregates[2],
            zero_cost=zero_cost,
        )
        for w in robustness.warnings:
            if w not in warnings:
                warnings.append(w)

        if not any(r.role == SplitRole.OUT_OF_SAMPLE for r in period_reports):
            warnings.append("missing_oos_periods")

        cfg_hash = configuration_hash(params)
        fingerprint = windows[0].dataset_fingerprint
        harness_id = sha256_hex(
            canonical_json(
                {
                    "strategy_id": strategy.strategy_id,
                    "strategy_version": strategy.version,
                    "configuration_hash": cfg_hash,
                    "dataset_fingerprint": fingerprint,
                    "mode": windows[0].mode.value,
                    "window_hashes": [window_config_hash(w) for w in windows],
                    "cost_assumptions": self.costs.model_dump(mode="json"),
                    "starting_capital": str(self.starting_capital),
                }
            )
        )

        assert self._broker_orders_created == 0
        result = WalkForwardResult(
            harness_id=harness_id,
            strategy_id=strategy.strategy_id,
            strategy_version=strategy.version,
            configuration_hash=cfg_hash,
            dataset_fingerprint=fingerprint,
            symbol=sym,
            timeframe=timeframe,
            mode=windows[0].mode.value,
            parameters=params,
            windows=[window_bounds_dict(w) for w in windows],
            period_reports=period_reports,
            aggregates=aggregates,
            robustness=robustness,
            research=research,
            warnings=warnings,
            limitations=limitations,
            paper_eligible=False,
            promotion_blocked=True,
            broker_orders_created=0,
            evaluated_at=evaluated_at or datetime.now(UTC),
        )
        if result.paper_eligible or not result.promotion_blocked:
            raise WalkForwardError("auto-promotion forbidden", code="promotion_blocked")
        return result

    def _assert_strategy_compatible(
        self, strategy: Strategy, *, allow_finrlx_baseline: bool
    ) -> None:
        sid = strategy.strategy_id
        if sid in COMPATIBLE_STRATEGY_IDS:
            return
        if allow_finrlx_baseline and (
            "finrl" in sid.lower() or sid.endswith("_baseline") or "rl_" in sid.lower()
        ):
            return
        if sid.startswith("external_") or "momentum" in sid:
            return
        # Reference / test doubles still allowed if they implement Strategy
        if sid in {"fixed", "fixed_decision"}:
            return
        raise UnsupportedStrategyError(
            f"strategy {sid!r} is not in the V1 walk-forward compatibility list; "
            "document as unsupported or pass allow_finrlx_baseline for baseline policies"
        )

    def _default_provenance(self, strategy: Strategy) -> ResearchProvenance:
        sid = strategy.strategy_id
        if "qlib" in sid:
            return qlib_momentum_provenance()
        if "finrl" in sid or "rl_" in sid:
            prov = finrlx_baseline_provenance()
            prov.notes.extend(FINRLX_COMPAT_NOTES)
            return prov
        return reference_strategy_provenance(
            strategy_id=sid, strategy_version=strategy.version
        )

    def _check_label_leakage(self, window: WalkForwardWindow, bars: list[Bar]) -> None:
        if window.label_horizon_bars <= 0:
            return
        # Gap between train end and validation start in bars
        train_end = window.train.score_end
        val_start = window.validation.score_start
        gap = sum(1 for b in bars if train_end <= b.timestamp < val_start)
        # Contiguous V1 splits have gap 0; forward-label horizons require an
        # explicit purge/embargo gap or the evaluation is rejected.
        require_purge_or_reject(
            label_horizon_bars=window.label_horizon_bars,
            embargo_bars=window.embargo_bars,
            gap_bars_between_fit_and_eval=gap,
        )

    def _evaluate_period(
        self,
        *,
        strategy: Strategy,
        bars: list[Bar],
        window: WalkForwardWindow,
        period: EvaluationPeriod,
        parameters: dict[str, Any],
        research: ResearchProvenance,
        timeframe: str,
        symbol: str,
    ) -> PeriodReport:
        period_bars = [
            b
            for b in bars
            if period.warmup_start <= b.timestamp < period.score_end
        ]
        if not period_bars:
            raise WalkForwardError(f"no bars for {period.role}", code="empty_period")

        # Isolation: train/validation slices must not include OOS timestamps
        if period.role != SplitRole.OUT_OF_SAMPLE:
            if any(b.timestamp >= window.oos.score_start for b in period_bars):
                raise DataLeakageError("OOS bars leaked into earlier evaluation period")

        if period.warmup_bars == 0 and period.role != SplitRole.TRAIN:
            # still OK; warn at evaluation layer
            pass

        gated = ScoreWindowGateStrategy(
            strategy,
            score_start=period.score_start,
            score_end=period.score_end,
        )
        provider = InMemoryHistoricalMarketDataProvider()
        provider.load_bars(symbol, timeframe, period_bars)
        engine = BacktestEngine(provider, costs=self.costs)
        raw = engine.run(
            gated,
            symbols=[symbol],
            timeframe=timeframe,
            start=period.warmup_start,
            end=period_bars[-1].timestamp,
            starting_capital=self.starting_capital,
            parameters=parameters,
        )
        assert self._broker_orders_created == 0

        scored = self._filter_scored_result(raw, period)
        # Fingerprint the full dataset (shared), but evaluation identity includes period role
        evaluation = self.evaluation_service.evaluate_backtest_result(
            scored,
            bars,  # full series fingerprint context for regime attribution
            research=research,
            split_role=period.role,
        )
        # Ensure period-specific identity components in warnings
        if period.warmup_bars == 0:
            if "missing_warmup_period" not in evaluation.warnings:
                evaluation.warnings.append("missing_warmup_period")
        if period.bar_count_scored < 5:
            evaluation.warnings.append("insufficient_period_history")

        # Rebind evaluation_id to include window/period for evidence uniqueness
        period_eid = evaluation_identity(
            strategy_id=scored.strategy_id,
            strategy_version=scored.strategy_version,
            configuration_hash=window.configuration_hash,
            dataset_fingerprint=window.dataset_fingerprint,
            execution_assumptions={
                **scored.execution_assumptions,
                "walk_forward_window": window.window_index,
                "split_role": period.role.value,
                "score_start": period.score_start.isoformat(),
                "score_end": period.score_end.isoformat(),
            },
            cost_assumptions=scored.cost_assumptions,
        )
        evaluation.evaluation_id = period_eid

        return period_report_from_evaluation(
            role=period.role,
            window_index=window.window_index,
            evaluation=evaluation,
            result=scored,
        )

    def _filter_scored_result(
        self, result: BacktestResult, period: EvaluationPeriod
    ) -> BacktestResult:
        """Keep only trades entered in the scored window; rebuild metrics."""
        scored_trades = [
            t
            for t in result.trades
            if period.score_start <= t.entry_time < period.score_end
        ]
        scored_curve = [
            p
            for p in result.equity_curve
            if period.score_start <= p.timestamp < period.score_end
        ]
        # Independent window accounting: ending equity from starting capital + scored trade PnL
        # plus mark-to-market at period end when curve available.
        if scored_curve:
            ending = scored_curve[-1].equity
            # Adjust: curve includes warm-up activity that was gated (should be flat).
            # With gating, equity should remain starting_capital until first scored trade.
        else:
            ending = result.starting_capital + sum(
                (t.net_pnl for t in scored_trades), Decimal("0")
            )

        closed = [
            ClosedTrade(
                strategy_id=t.strategy_id,
                strategy_version=t.strategy_version,
                symbol=t.symbol,
                side=t.side,
                entry_time=t.entry_time,
                entry_price=t.entry_price,
                exit_time=t.exit_time,
                exit_price=t.exit_price,
                quantity=t.quantity,
                gross_pnl=t.gross_pnl,
                costs=t.costs,
                net_pnl=t.net_pnl,
                exit_reason=t.exit_reason,
            )
            for t in scored_trades
        ]
        metrics = calculate_metrics(
            starting_capital=result.starting_capital,
            ending_equity=ending,
            trades=closed,
            equity_curve=scored_curve,
        )
        warnings = [
            w
            for w in result.warnings
            if "pending" not in w.lower() or scored_trades
        ]
        warnings.append("walk_forward_independent_window_position_reset")
        return BacktestResult(
            strategy_id=result.strategy_id,
            strategy_name=result.strategy_name,
            strategy_version=result.strategy_version,
            parameters=result.parameters,
            start=period.score_start,
            end=scored_curve[-1].timestamp if scored_curve else period.score_start,
            symbols=result.symbols,
            timeframe=result.timeframe,
            starting_capital=result.starting_capital,
            ending_equity=ending,
            metrics=metrics,
            trades=scored_trades,
            equity_curve=scored_curve,
            warnings=warnings,
            execution_assumptions={
                **result.execution_assumptions,
                "walk_forward_score_start": period.score_start.isoformat(),
                "walk_forward_score_end": period.score_end.isoformat(),
                "position_carryover": False,
            },
            cost_assumptions=result.cost_assumptions,
        )
