"""Walk-Forward Evaluation Harness V1 — test matrix."""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.backtesting import BacktestCostModel, make_bar
from app.evaluation.models import SplitRole
from app.evaluation.research_adapters import (
    finrlx_baseline_provenance,
    qlib_momentum_provenance,
    reference_strategy_provenance,
)
from app.evaluation.walkforward import (
    ChronologicalSplit,
    DataLeakageError,
    InsufficientHistoryError,
    InvalidSplitError,
    SplitSpec,
    UnsupportedStrategyError,
    WalkForwardHarness,
    WalkForwardPlan,
    WindowMode,
    generate_windows,
)
from app.evaluation.walkforward.gating import ScoreWindowGateStrategy
from app.evaluation.walkforward.leakage import assert_no_future_bars, require_purge_or_reject
from app.market_memory import MarketMemoryService
from app.models.enums import AssetClass
from app.strategies import DecisionAction, StrategyDecision, no_action
from app.strategies.protocol import Strategy
from app.strategies.reference.rsi_macd_trend import RSIMACDTrendStrategy
from app.strategies.reference.sma_crossover import SMACrossoverStrategy
from app.models.enums import OrderType


def _ts(day: int) -> datetime:
    return datetime(2024, 1, 1, 16, 0, tzinfo=UTC) + timedelta(days=day - 1)


def _bars(n: int = 90, *, start_price: int = 100) -> list:
    out = []
    for i in range(n):
        c = Decimal(str(start_price + i))
        out.append(
            make_bar(
                "AAPL",
                _ts(i + 1),
                open=c,
                high=c + Decimal("1"),
                low=c - Decimal("1"),
                close=c,
            )
        )
    return out


class FixedDecisionStrategy(Strategy):
    def __init__(self, decisions: list[StrategyDecision], *, strategy_id: str = "fixed") -> None:
        self._decisions = list(decisions)
        self._i = 0
        self._id = strategy_id

    @property
    def strategy_id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return "Fixed"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def supported_asset_classes(self) -> frozenset[AssetClass]:
        return frozenset({AssetClass.EQUITY})

    @property
    def required_timeframes(self) -> frozenset[str]:
        return frozenset({"1Day"})

    def evaluate(self, context) -> StrategyDecision:
        _ = context
        if self._i >= len(self._decisions):
            return no_action()
        d = self._decisions[self._i]
        self._i += 1
        return d


# ---------------------------------------------------------------------------
# Splitting
# ---------------------------------------------------------------------------


def test_chronological_percentage_split() -> None:
    bars = _bars(100)
    windows = generate_windows(
        bars,
        spec=SplitSpec(train_pct=0.5, validation_pct=0.2, oos_pct=0.3, warmup_bars=5),
        symbol="AAPL",
        timeframe="1Day",
        strategy_id="sma_crossover",
        strategy_version="1.0.0",
        parameters={"fast_period": 5},
    )
    assert len(windows) == 1
    w = windows[0]
    assert w.train.score_end <= w.validation.score_start
    assert w.validation.score_end <= w.oos.score_start
    assert w.train.bar_count_scored == 50
    assert w.dataset_fingerprint


def test_date_based_split() -> None:
    bars = _bars(60)
    windows = generate_windows(
        bars,
        spec=SplitSpec(
            mode=WindowMode.FIXED,
            train_start=_ts(1),
            train_end=_ts(31),
            validation_end=_ts(46),
            oos_end=_ts(61),
            warmup_bars=5,
        ),
        symbol="AAPL",
        timeframe="1Day",
        strategy_id="sma_crossover",
        strategy_version="1.0.0",
    )
    w = windows[0]
    assert w.train.score_start == bars[0].timestamp
    assert w.oos.bar_count_scored >= 1


def test_rolling_windows() -> None:
    bars = _bars(90)
    windows = generate_windows(
        bars,
        spec=SplitSpec(
            mode=WindowMode.ROLLING,
            train_bars=30,
            validation_bars=15,
            oos_bars=15,
            step_bars=15,
            warmup_bars=10,
        ),
        symbol="AAPL",
        timeframe="1Day",
        strategy_id="sma_crossover",
        strategy_version="1.0.0",
    )
    assert len(windows) >= 2
    assert windows[0].mode == WindowMode.ROLLING
    # Rolling train start advances
    assert windows[1].train.score_start > windows[0].train.score_start


def test_expanding_windows() -> None:
    bars = _bars(90)
    windows = generate_windows(
        bars,
        spec=SplitSpec(
            mode=WindowMode.EXPANDING,
            train_bars=30,
            validation_bars=15,
            oos_bars=15,
            step_bars=15,
            warmup_bars=5,
        ),
        symbol="AAPL",
        timeframe="1Day",
        strategy_id="sma_crossover",
        strategy_version="1.0.0",
    )
    assert len(windows) >= 2
    assert windows[0].mode == WindowMode.EXPANDING
    # Expanding train starts at first bar; length grows
    assert windows[0].train.score_start == bars[0].timestamp
    assert windows[1].train.score_start == bars[0].timestamp
    assert windows[1].train.bar_count_scored > windows[0].train.bar_count_scored


def test_invalid_split_rejection() -> None:
    bars = _bars(20)
    with pytest.raises((InvalidSplitError, InsufficientHistoryError, ValueError)):
        generate_windows(
            bars,
            spec=SplitSpec(train_pct=0.5, validation_pct=0.5, oos_pct=0.5),
            symbol="AAPL",
            timeframe="1Day",
            strategy_id="x",
            strategy_version="1",
        )
    with pytest.raises(InsufficientHistoryError):
        generate_windows(
            bars,
            spec=SplitSpec(
                mode=WindowMode.ROLLING,
                train_bars=50,
                validation_bars=50,
                oos_bars=50,
            ),
            symbol="AAPL",
            timeframe="1Day",
            strategy_id="x",
            strategy_version="1",
        )


def test_overlap_prevention() -> None:
    plan = WalkForwardPlan(
        symbol="AAPL",
        timeframe="1Day",
        splits=[
            ChronologicalSplit(role=SplitRole.TRAIN, start=_ts(1), end=_ts(20)),
            ChronologicalSplit(role=SplitRole.VALIDATION, start=_ts(15), end=_ts(30)),
        ],
    )
    with pytest.raises(ValueError):
        plan.validate_chronology()


def test_warmup_boundaries_do_not_score_warmup_trades() -> None:
    bars = _bars(80)
    harness = WalkForwardHarness(starting_capital=Decimal("100000"))
    result = harness.run(
        strategy=SMACrossoverStrategy(),
        bars=bars,
        timeframe="1Day",
        spec=SplitSpec(
            mode=WindowMode.FIXED,
            train_pct=0.5,
            validation_pct=0.25,
            oos_pct=0.25,
            warmup_bars=15,
        ),
        parameters={"fast_period": 5, "slow_period": 12, "quantity": "1"},
        research=reference_strategy_provenance(
            strategy_id="sma_crossover", strategy_version="1.0.0"
        ),
    )
    w = result.windows[0]
    role_key = {
        SplitRole.TRAIN: "train",
        SplitRole.VALIDATION: "validation",
        SplitRole.OUT_OF_SAMPLE: "oos",
    }
    for report in result.period_reports:
        bounds = w[role_key[report.role]]
        score_start = datetime.fromisoformat(bounds["score_start"])
        score_end = datetime.fromisoformat(bounds["score_end"])
        for t in report.evaluation.attributions:
            assert score_start <= t.entry_time < score_end
        if report.backtest is not None:
            for t in report.backtest.trades:
                assert score_start <= t.entry_time < score_end


# ---------------------------------------------------------------------------
# Isolation / leakage
# ---------------------------------------------------------------------------


def test_train_val_oos_isolation() -> None:
    bars = _bars(90)
    result = WalkForwardHarness().run(
        strategy=SMACrossoverStrategy(),
        bars=bars,
        timeframe="1Day",
        spec=SplitSpec(
            mode=WindowMode.ROLLING,
            train_bars=30,
            validation_bars=15,
            oos_bars=15,
            step_bars=30,
            warmup_bars=10,
        ),
        parameters={"fast_period": 5, "slow_period": 12, "quantity": "1"},
    )
    for report in result.period_reports:
        assert report.evaluation.split_role == report.role
        if report.role != SplitRole.OUT_OF_SAMPLE:
            assert report.evaluation.split_role != SplitRole.OUT_OF_SAMPLE


def test_future_data_leakage_prevention() -> None:
    bars = _bars(10)
    with pytest.raises(DataLeakageError):
        assert_no_future_bars(bars, as_of=bars[3].timestamp)


def test_forward_label_leakage_rejected() -> None:
    bars = _bars(90)
    with pytest.raises(DataLeakageError):
        WalkForwardHarness().run(
            strategy=SMACrossoverStrategy(),
            bars=bars,
            timeframe="1Day",
            spec=SplitSpec(
                mode=WindowMode.FIXED,
                train_pct=0.5,
                validation_pct=0.25,
                oos_pct=0.25,
                label_horizon_bars=5,
                embargo_bars=0,
            ),
            parameters={"fast_period": 5, "slow_period": 12, "quantity": "1"},
        )


def test_purge_embargo_helper() -> None:
    require_purge_or_reject(
        label_horizon_bars=2, embargo_bars=1, gap_bars_between_fit_and_eval=3
    )
    with pytest.raises(DataLeakageError):
        require_purge_or_reject(
            label_horizon_bars=5, embargo_bars=0, gap_bars_between_fit_and_eval=0
        )


def test_gating_blocks_warmup_actions() -> None:
    decisions = [
        StrategyDecision(
            action=DecisionAction.ENTER_LONG,
            symbol="AAPL",
            asset_class=AssetClass.EQUITY,
            quantity=Decimal("1"),
            order_type=OrderType.MARKET,
        )
    ]
    inner = FixedDecisionStrategy(decisions)
    gate = ScoreWindowGateStrategy(
        inner, score_start=_ts(5), score_end=_ts(10)
    )
    from app.strategies.context import StrategyContext

    ctx_early = StrategyContext(
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        timestamp=_ts(2),
        timeframe="1Day",
        bars=[],
        reference_price=Decimal("100"),
    )
    assert gate.evaluate(ctx_early).action == DecisionAction.NO_ACTION


def test_position_reset_independent_windows() -> None:
    bars = _bars(90)
    result = WalkForwardHarness(starting_capital=Decimal("50000")).run(
        strategy=SMACrossoverStrategy(),
        bars=bars,
        timeframe="1Day",
        spec=SplitSpec(
            mode=WindowMode.ROLLING,
            train_bars=30,
            validation_bars=10,
            oos_bars=10,
            step_bars=20,
            warmup_bars=8,
        ),
        parameters={"fast_period": 5, "slow_period": 12, "quantity": "1"},
    )
    for report in result.period_reports:
        assert report.backtest is not None
        assert report.backtest.starting_capital == Decimal("50000")
        assert report.backtest.execution_assumptions.get("position_carryover") is False


# ---------------------------------------------------------------------------
# Reporting / aggregation / reproducibility
# ---------------------------------------------------------------------------


def test_performance_reporting_roles() -> None:
    bars = _bars(80)
    result = WalkForwardHarness().run(
        strategy=SMACrossoverStrategy(),
        bars=bars,
        timeframe="1Day",
        spec=SplitSpec(
            train_pct=0.5, validation_pct=0.25, oos_pct=0.25, warmup_bars=10
        ),
        parameters={"fast_period": 5, "slow_period": 12, "quantity": "1"},
    )
    roles = {r.role for r in result.period_reports}
    assert roles == {
        SplitRole.TRAIN,
        SplitRole.VALIDATION,
        SplitRole.OUT_OF_SAMPLE,
    }
    for r in result.period_reports:
        assert r.trade_count == r.evaluation.metrics.number_of_trades
        assert isinstance(r.transaction_costs, Decimal)
    assert len(result.aggregates) == 3
    oos_agg = next(a for a in result.aggregates if a.role == SplitRole.OUT_OF_SAMPLE)
    assert oos_agg.compounded_return_pct is not None


def test_dataset_fingerprint_stability() -> None:
    bars = _bars(60)
    a = WalkForwardHarness().run(
        strategy=SMACrossoverStrategy(),
        bars=bars,
        timeframe="1Day",
        spec=SplitSpec(train_pct=0.5, validation_pct=0.25, oos_pct=0.25),
        parameters={"fast_period": 5, "slow_period": 12, "quantity": "1"},
        evaluated_at=datetime(2024, 6, 1, tzinfo=UTC),
    )
    b = WalkForwardHarness().run(
        strategy=SMACrossoverStrategy(),
        bars=bars,
        timeframe="1Day",
        spec=SplitSpec(train_pct=0.5, validation_pct=0.25, oos_pct=0.25),
        parameters={"fast_period": 5, "slow_period": 12, "quantity": "1"},
        evaluated_at=datetime(2025, 1, 1, tzinfo=UTC),
    )
    assert a.harness_id == b.harness_id
    assert a.dataset_fingerprint == b.dataset_fingerprint
    assert a.configuration_hash == b.configuration_hash


def test_cost_accounting_present() -> None:
    bars = _bars(70)
    costs = BacktestCostModel(commission_flat=Decimal("1"), slippage_bps=Decimal("10"))
    result = WalkForwardHarness(costs=costs).run(
        strategy=SMACrossoverStrategy(),
        bars=bars,
        timeframe="1Day",
        spec=SplitSpec(train_pct=0.5, validation_pct=0.25, oos_pct=0.25, warmup_bars=8),
        parameters={"fast_period": 5, "slow_period": 12, "quantity": "1"},
    )
    # If trades exist, costs should be non-zero under this model
    traded = [r for r in result.period_reports if r.trade_count > 0]
    if traded:
        assert any(r.transaction_costs > 0 for r in traded)


def test_small_sample_warnings() -> None:
    bars = _bars(40)
    result = WalkForwardHarness().run(
        strategy=SMACrossoverStrategy(),
        bars=bars,
        timeframe="1Day",
        spec=SplitSpec(
            train_pct=0.5, validation_pct=0.25, oos_pct=0.25, warmup_bars=5
        ),
        parameters={"fast_period": 5, "slow_period": 12, "quantity": "1"},
    )
    assert result.robustness is not None
    assert result.robustness.small_sample or "small_oos_trade_sample" in result.warnings or any(
        "small_sample" in w for w in result.warnings
    )


def test_robustness_descriptive_only() -> None:
    bars = _bars(90)
    result = WalkForwardHarness().run(
        strategy=SMACrossoverStrategy(),
        bars=bars,
        timeframe="1Day",
        spec=SplitSpec(
            mode=WindowMode.ROLLING,
            train_bars=30,
            validation_bars=10,
            oos_bars=10,
            step_bars=20,
            warmup_bars=5,
        ),
        parameters={"fast_period": 5, "slow_period": 12, "quantity": "1"},
    )
    assert "no statistical confidence levels are claimed" in result.robustness.disclaimer.lower()
    assert "does not establish strategy profitability" in result.robustness.disclaimer


# ---------------------------------------------------------------------------
# Strategy compatibility
# ---------------------------------------------------------------------------


def test_sma_and_rsi_macd_compatibility() -> None:
    bars = _bars(80)
    spec = SplitSpec(train_pct=0.5, validation_pct=0.25, oos_pct=0.25, warmup_bars=20)
    r1 = WalkForwardHarness().run(
        strategy=SMACrossoverStrategy(),
        bars=bars,
        timeframe="1Day",
        spec=spec,
        parameters={"fast_period": 5, "slow_period": 15, "quantity": "1"},
    )
    r2 = WalkForwardHarness().run(
        strategy=RSIMACDTrendStrategy(),
        bars=bars,
        timeframe="1Day",
        spec=spec,
        parameters={"quantity": "1"},
    )
    assert r1.strategy_id == "sma_crossover"
    assert r2.strategy_id == "rsi_macd_trend"


def test_qlib_provenance_compatible() -> None:
    bars = _bars(60)
    result = WalkForwardHarness().run(
        strategy=SMACrossoverStrategy(),
        bars=bars,
        timeframe="1Day",
        spec=SplitSpec(train_pct=0.5, validation_pct=0.25, oos_pct=0.25),
        parameters={"fast_period": 5, "slow_period": 12, "quantity": "1"},
        research=qlib_momentum_provenance(),
    )
    assert result.research.research_model_id == "qlib_inspired_momentum_v1"
    assert result.research.is_trained_ai_policy is False


def test_finrlx_baseline_flag_and_not_trained() -> None:
    bars = _bars(60)
    result = WalkForwardHarness().run(
        strategy=SMACrossoverStrategy(),
        bars=bars,
        timeframe="1Day",
        spec=SplitSpec(train_pct=0.5, validation_pct=0.25, oos_pct=0.25),
        parameters={"fast_period": 5, "slow_period": 12, "quantity": "1"},
        research=finrlx_baseline_provenance(),
        allow_finrlx_baseline=True,
    )
    assert result.research.is_trained_ai_policy is False
    assert any("NOT a trained AI" in n for n in result.research.notes)


class _UnknownStrategy(Strategy):
    @property
    def strategy_id(self) -> str:
        return "totally_unknown_strategy_xyz"

    @property
    def name(self) -> str:
        return "X"

    @property
    def version(self) -> str:
        return "1"

    @property
    def supported_asset_classes(self):
        return frozenset({AssetClass.EQUITY})

    @property
    def required_timeframes(self):
        return frozenset({"1Day"})

    def evaluate(self, context):
        return no_action()


def test_unsupported_strategy() -> None:
    with pytest.raises(UnsupportedStrategyError):
        WalkForwardHarness().run(
            strategy=_UnknownStrategy(),
            bars=_bars(40),
            timeframe="1Day",
            spec=SplitSpec(train_pct=0.5, validation_pct=0.25, oos_pct=0.25),
        )


# ---------------------------------------------------------------------------
# Market Memory
# ---------------------------------------------------------------------------


def test_market_memory_walk_forward_persistence(db_session: Session) -> None:
    bars = _bars(60)
    result = WalkForwardHarness().run(
        strategy=SMACrossoverStrategy(),
        bars=bars,
        timeframe="1Day",
        spec=SplitSpec(train_pct=0.5, validation_pct=0.25, oos_pct=0.25, warmup_bars=5),
        parameters={"fast_period": 5, "slow_period": 12, "quantity": "1"},
    )
    svc = MarketMemoryService(db_session)
    e1, c1 = svc.persist_walk_forward(result)
    e2, c2 = svc.persist_walk_forward(result)
    assert c1 and not c2
    assert e1.id == e2.id
    assert e1.event_type == "walk_forward_evaluation_summary"
    assert e1.market_context["evidence_id"] == result.harness_id
    assert "equity_curve" not in (e1.outcome or {})
    assert "period_reports" not in (e1.outcome or {})
    assert "period_summaries" in (e1.outcome or {})


def test_idempotent_event_writes(db_session: Session) -> None:
    bars = _bars(50)
    result = WalkForwardHarness().run(
        strategy=SMACrossoverStrategy(),
        bars=bars,
        timeframe="1Day",
        spec=SplitSpec(train_pct=0.5, validation_pct=0.25, oos_pct=0.25),
        parameters={"fast_period": 5, "slow_period": 12, "quantity": "1"},
    )
    svc = MarketMemoryService(db_session)
    svc.persist_walk_forward(result)
    again = svc.get_walk_forward_event(result.harness_id)
    assert again is not None


# ---------------------------------------------------------------------------
# Boundaries
# ---------------------------------------------------------------------------


def test_broker_isolation_ast() -> None:
    root = Path(__file__).resolve().parents[1] / "app" / "evaluation" / "walkforward"
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("app.brokers.alpaca")
                assert not node.module.startswith("app.brokers.router")
                assert node.module.split(".")[0] not in {"alpaca", "alpaca_trade_api"}


def test_no_order_submission_and_no_promotion() -> None:
    bars = _bars(60)
    harness = WalkForwardHarness()
    result = harness.run(
        strategy=SMACrossoverStrategy(),
        bars=bars,
        timeframe="1Day",
        spec=SplitSpec(train_pct=0.5, validation_pct=0.25, oos_pct=0.25),
        parameters={"fast_period": 5, "slow_period": 12, "quantity": "1"},
    )
    assert result.broker_orders_created == 0
    assert harness.broker_orders_created == 0
    assert result.paper_eligible is False
    assert result.promotion_blocked is True


def test_zero_cost_warning() -> None:
    bars = _bars(50)
    result = WalkForwardHarness(costs=BacktestCostModel()).run(
        strategy=SMACrossoverStrategy(),
        bars=bars,
        timeframe="1Day",
        spec=SplitSpec(train_pct=0.5, validation_pct=0.25, oos_pct=0.25),
        parameters={"fast_period": 5, "slow_period": 12, "quantity": "1"},
    )
    assert "unrealistic_zero_cost_assumptions" in result.warnings or (
        result.robustness and "unrealistic_zero_cost_assumptions" in result.robustness.warnings
    )
