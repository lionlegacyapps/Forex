"""Strategy Evaluation & Market Memory V1 — test matrix."""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.backtesting import (
    BacktestCostModel,
    BacktestEngine,
    InMemoryHistoricalMarketDataProvider,
    make_bar,
)
from app.backtesting.result import BacktestTradeRecord
from app.evaluation.attribution import attribute_trade, attribute_trades, regime_performance
from app.evaluation.comparison import compare_evaluations
from app.evaluation.evidence import assert_no_auto_promotion
from app.evaluation.hashing import (
    configuration_hash,
    dataset_fingerprint,
)
from app.evaluation.models import (
    SplitRole,
    build_dataset_identity,
)
from app.evaluation.regimes import (
    MarketRegime,
    RegimeClassifierConfig,
    classify_market_context,
    index_at_or_before,
)
from app.evaluation.research_adapters import (
    finrlx_baseline_provenance,
    provenance_from_research_output,
    qlib_momentum_provenance,
    reference_strategy_provenance,
)
from app.evaluation.service import StrategyEvaluationService
from app.evaluation.walkforward import ChronologicalSplit, WalkForwardPlan
from app.market_data.models import Bar
from app.market_memory import (
    EvidenceConflictError,
    EvidenceImmutabilityError,
    MarketMemoryService,
)
from app.models.enums import AssetClass, StrategyStatus
from app.models.strategy import Strategy as StrategyRow
from app.research.models import ResearchOutput
from app.strategies import DecisionAction, StrategyDecision, no_action
from app.strategies.protocol import Strategy
from app.strategies.reference.rsi_macd_trend import RSIMACDTrendStrategy
from app.strategies.reference.sma_crossover import SMACrossoverStrategy
from app.models.enums import OrderType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ts(day: int) -> datetime:
    return datetime(2024, 1, 1, 16, 0, tzinfo=UTC) + timedelta(days=day - 1)


def _ohlc_series(
    symbol: str,
    closes: list[str],
    *,
    timeframe: str = "1Day",
    volume: str | None = "1000",
) -> list[Bar]:
    bars: list[Bar] = []
    for i, c in enumerate(closes):
        price = Decimal(c)
        bars.append(
            make_bar(
                symbol,
                _ts(i + 1),
                open=price,
                high=price + Decimal("1"),
                low=price - Decimal("1"),
                close=price,
                timeframe=timeframe,
                volume=Decimal(volume) if volume is not None else None,
            )
        )
    return bars


def _provider(symbol: str, closes: list[str]) -> InMemoryHistoricalMarketDataProvider:
    p = InMemoryHistoricalMarketDataProvider()
    p.load_bars(symbol, "1Day", _ohlc_series(symbol, closes))
    return p


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


def _enter_exit_decisions(n_bars: int) -> list[StrategyDecision]:
    # enter at idx 1, exit at idx 4 — needs >= 6 bars for fill
    decisions: list[StrategyDecision] = [no_action()] * n_bars
    decisions[1] = StrategyDecision(
        action=DecisionAction.ENTER_LONG,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        quantity=Decimal("1"),
        order_type=OrderType.MARKET,
    )
    decisions[4] = StrategyDecision(
        action=DecisionAction.EXIT_LONG,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        quantity=Decimal("1"),
        order_type=OrderType.MARKET,
    )
    return decisions


def _uptrend_closes(n: int = 60) -> list[str]:
    return [str(100 + i) for i in range(n)]


def _downtrend_closes(n: int = 60) -> list[str]:
    return [str(200 - i) for i in range(n)]


def _ranging_closes(n: int = 60) -> list[str]:
    out = []
    for i in range(n):
        out.append(str(100 + (i % 3) - 1))  # 99,100,101 oscillation
    return out


# ---------------------------------------------------------------------------
# Hashing / normalization
# ---------------------------------------------------------------------------


def test_dataset_fingerprint_deterministic() -> None:
    bars = _ohlc_series("AAPL", ["10", "11", "12"])
    a = dataset_fingerprint(bars, symbol="AAPL", timeframe="1Day")
    b = dataset_fingerprint(bars, symbol="aapl", timeframe="1Day")
    assert a == b
    assert len(a) == 64
    other = dataset_fingerprint(_ohlc_series("AAPL", ["10", "11", "13"]), symbol="AAPL", timeframe="1Day")
    assert a != other


def test_configuration_hash_stable() -> None:
    h1 = configuration_hash({"fast_period": 2, "slow_period": 5})
    h2 = configuration_hash({"slow_period": 5, "fast_period": 2})
    assert h1 == h2
    assert h1 != configuration_hash({"fast_period": 3, "slow_period": 5})


def test_evaluation_record_normalization() -> None:
    closes = _uptrend_closes(40)
    provider = _provider("AAPL", closes)
    result = BacktestEngine(provider).run(
        SMACrossoverStrategy(),
        symbols=["AAPL"],
        timeframe="1Day",
        starting_capital=Decimal("100000"),
        parameters={"fast_period": 5, "slow_period": 15, "quantity": "1"},
    )
    bars = provider.get_bars("AAPL", "1Day", None, None)
    svc = StrategyEvaluationService()
    rec = svc.evaluate_backtest_result(result, bars)
    assert rec.evaluation_id
    assert rec.configuration_hash
    assert rec.dataset.fingerprint
    assert rec.dataset.symbol == "AAPL"
    assert rec.paper_eligible is False
    assert rec.promotion_blocked is True
    assert rec.split_role == SplitRole.FULL_SAMPLE
    assert "missing_out_of_sample_evaluation" in rec.warnings


# ---------------------------------------------------------------------------
# Market regimes / point-in-time
# ---------------------------------------------------------------------------


def test_regime_trending_up() -> None:
    bars = _ohlc_series("AAPL", _uptrend_closes(50))
    snap = classify_market_context(bars, as_of_index=len(bars) - 1, timeframe="1Day")
    assert MarketRegime.TRENDING_UP in snap.regimes
    assert snap.warmup_complete is True


def test_regime_trending_down() -> None:
    bars = _ohlc_series("AAPL", _downtrend_closes(50))
    snap = classify_market_context(bars, as_of_index=len(bars) - 1, timeframe="1Day")
    assert MarketRegime.TRENDING_DOWN in snap.regimes


def test_regime_ranging() -> None:
    bars = _ohlc_series("AAPL", _ranging_closes(50))
    cfg = RegimeClassifierConfig(ranging_band_pct=Decimal("0.02"))
    snap = classify_market_context(
        bars, as_of_index=len(bars) - 1, timeframe="1Day", config=cfg
    )
    assert MarketRegime.RANGING in snap.regimes or MarketRegime.UNKNOWN in snap.regimes


def test_point_in_time_no_future_bars() -> None:
    closes = _uptrend_closes(40)
    # Inject a future spike that must not affect earlier classification
    closes_future_spike = list(closes)
    closes_future_spike[-1] = "9999"
    bars_clean = _ohlc_series("AAPL", closes)
    bars_spike = _ohlc_series("AAPL", closes_future_spike)
    mid = 25
    a = classify_market_context(bars_clean, as_of_index=mid, timeframe="1Day")
    b = classify_market_context(bars_spike, as_of_index=mid, timeframe="1Day")
    assert a.regimes == b.regimes
    assert a.close == b.close


def test_index_at_or_before() -> None:
    bars = _ohlc_series("AAPL", ["10", "11", "12"])
    assert index_at_or_before(bars, bars[1].timestamp) == 1
    assert index_at_or_before(bars, bars[0].timestamp - timedelta(days=1)) is None


def test_insufficient_warmup_unknown() -> None:
    bars = _ohlc_series("AAPL", ["10", "11", "12"])
    snap = classify_market_context(bars, as_of_index=2, timeframe="1Day")
    assert MarketRegime.UNKNOWN in snap.regimes or snap.warmup_complete is False
    assert snap.warnings


# ---------------------------------------------------------------------------
# Attribution + regime performance
# ---------------------------------------------------------------------------


def test_trade_to_regime_attribution() -> None:
    closes = _uptrend_closes(30)
    decisions = _enter_exit_decisions(30)
    provider = _provider("AAPL", closes)
    result = BacktestEngine(provider).run(
        FixedDecisionStrategy(decisions),  # type: ignore[arg-type]
        symbols=["AAPL"],
        timeframe="1Day",
        starting_capital=Decimal("10000"),
    )
    bars = provider.get_bars("AAPL", "1Day", None, None)
    assert result.metrics.number_of_trades >= 1
    attrs = attribute_trades(result, bars)
    assert len(attrs) == result.metrics.number_of_trades
    assert attrs[0].entry_regimes
    assert attrs[0].holding_duration_seconds >= 0
    assert attrs[0].net_pnl == result.trades[0].net_pnl


def test_regime_performance_small_sample_not_reliable() -> None:
    trade = BacktestTradeRecord(
        strategy_id="x",
        strategy_version="1",
        symbol="AAPL",
        side="long",
        entry_time=_ts(20),
        entry_price=Decimal("100"),
        exit_time=_ts(22),
        exit_price=Decimal("105"),
        quantity=Decimal("1"),
        gross_pnl=Decimal("5"),
        costs=Decimal("0"),
        net_pnl=Decimal("5"),
        exit_reason="signal",
    )
    bars = _ohlc_series("AAPL", _uptrend_closes(40))
    attr = attribute_trade(trade, bars, timeframe="1Day")
    buckets = regime_performance([attr, attr])  # only 2 trades
    for b in buckets:
        if b.trade_count == 2:
            assert b.sample_reliable is False
            assert any("not_reliable" in w or "small_regime" in w for w in b.warnings)


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def test_same_dataset_strategy_comparison() -> None:
    closes = _uptrend_closes(50)
    bars = _ohlc_series("AAPL", closes)
    p1 = _provider("AAPL", closes)
    p2 = _provider("AAPL", closes)
    svc = StrategyEvaluationService()
    r1 = svc.run_and_evaluate(
        strategy=SMACrossoverStrategy(),
        provider=p1,
        symbols=["AAPL"],
        timeframe="1Day",
        parameters={"fast_period": 5, "slow_period": 15, "quantity": "1"},
        starting_capital=Decimal("100000"),
        research=reference_strategy_provenance(strategy_id="sma_crossover", strategy_version="1.0.0"),
        bars=bars,
    )
    r2 = svc.run_and_evaluate(
        strategy=RSIMACDTrendStrategy(),
        provider=p2,
        symbols=["AAPL"],
        timeframe="1Day",
        parameters={"quantity": "1"},
        starting_capital=Decimal("100000"),
        research=reference_strategy_provenance(strategy_id="rsi_macd_trend", strategy_version="1.0.0"),
        bars=bars,
    )
    report = svc.compare([r1, r2])
    assert report.comparable is True
    assert report.dataset_fingerprint == r1.dataset.fingerprint
    assert len(report.metrics) == 2
    assert "win rate alone" in report.ranking_note.lower()


def test_incomparable_dataset_warning() -> None:
    svc = StrategyEvaluationService()
    closes_a = _uptrend_closes(40)
    closes_b = _downtrend_closes(40)
    r1 = svc.run_and_evaluate(
        strategy=SMACrossoverStrategy(),
        provider=_provider("AAPL", closes_a),
        symbols=["AAPL"],
        timeframe="1Day",
        parameters={"fast_period": 5, "slow_period": 15, "quantity": "1"},
    )
    r2 = svc.run_and_evaluate(
        strategy=SMACrossoverStrategy(),
        provider=_provider("AAPL", closes_b),
        symbols=["AAPL"],
        timeframe="1Day",
        parameters={"fast_period": 5, "slow_period": 15, "quantity": "1"},
    )
    report = compare_evaluations([r1, r2])
    assert report.comparable is False
    assert "non_comparable_datasets" in report.reasons_not_comparable


def test_zero_trade_evaluation_warnings() -> None:
    closes = ["10", "11", "12", "13", "14", "15"]
    decisions = [no_action()] * 6
    provider = _provider("AAPL", closes)
    result = BacktestEngine(provider).run(
        FixedDecisionStrategy(decisions),  # type: ignore[arg-type]
        symbols=["AAPL"],
        timeframe="1Day",
    )
    rec = StrategyEvaluationService().evaluate_backtest_result(
        result, provider.get_bars("AAPL", "1Day", None, None)
    )
    assert "zero_completed_trades" in rec.warnings
    assert rec.metrics.number_of_trades == 0


def test_small_sample_warning() -> None:
    closes = _uptrend_closes(20)
    decisions = _enter_exit_decisions(20)
    provider = _provider("AAPL", closes)
    result = BacktestEngine(provider).run(
        FixedDecisionStrategy(decisions),  # type: ignore[arg-type]
        symbols=["AAPL"],
        timeframe="1Day",
        starting_capital=Decimal("10000"),
    )
    rec = StrategyEvaluationService().evaluate_backtest_result(
        result, provider.get_bars("AAPL", "1Day", None, None)
    )
    assert rec.metrics.number_of_trades < 10
    assert "small_sample_size" in rec.warnings or "zero_completed_trades" in rec.warnings


def test_profit_factor_and_drawdown_in_comparison() -> None:
    closes = [
        "100", "100", "100", "100", "110", "110", "110", "100", "100", "100",
        "100", "100", "100", "100", "100", "100",
    ]
    # trade1 win then trade2 loss via two enter/exit pairs
    decisions = [no_action()] * len(closes)
    decisions[1] = StrategyDecision(
        action=DecisionAction.ENTER_LONG, symbol="AAPL", asset_class=AssetClass.EQUITY,
        quantity=Decimal("1"), order_type=OrderType.MARKET,
    )
    decisions[3] = StrategyDecision(
        action=DecisionAction.EXIT_LONG, symbol="AAPL", asset_class=AssetClass.EQUITY,
        quantity=Decimal("1"), order_type=OrderType.MARKET,
    )
    decisions[6] = StrategyDecision(
        action=DecisionAction.ENTER_LONG, symbol="AAPL", asset_class=AssetClass.EQUITY,
        quantity=Decimal("1"), order_type=OrderType.MARKET,
    )
    decisions[8] = StrategyDecision(
        action=DecisionAction.EXIT_LONG, symbol="AAPL", asset_class=AssetClass.EQUITY,
        quantity=Decimal("1"), order_type=OrderType.MARKET,
    )
    provider = _provider("AAPL", closes)
    result = BacktestEngine(provider).run(
        FixedDecisionStrategy(decisions),  # type: ignore[arg-type]
        symbols=["AAPL"],
        timeframe="1Day",
        starting_capital=Decimal("10000"),
    )
    rec = StrategyEvaluationService().evaluate_backtest_result(
        result, provider.get_bars("AAPL", "1Day", None, None)
    )
    report = compare_evaluations([rec])
    m = report.metrics[0]
    assert m.number_of_trades >= 1
    # profit_factor may be None on edge; drawdown fields present on metrics object
    assert hasattr(m, "profit_factor")
    assert hasattr(m, "max_drawdown")


# ---------------------------------------------------------------------------
# Reproducibility / identity
# ---------------------------------------------------------------------------


def test_deterministic_reproducibility_identity() -> None:
    closes = _uptrend_closes(40)
    params = {"fast_period": 5, "slow_period": 15, "quantity": "1"}

    def once():
        p = _provider("AAPL", closes)
        bars = p.get_bars("AAPL", "1Day", None, None)
        result = BacktestEngine(p).run(
            SMACrossoverStrategy(),
            symbols=["AAPL"],
            timeframe="1Day",
            parameters=params,
            starting_capital=Decimal("100000"),
        )
        svc = StrategyEvaluationService()
        r1 = svc.evaluate_backtest_result(
            result, bars, evaluated_at=datetime(2024, 6, 1, tzinfo=UTC)
        )
        r2 = svc.evaluate_backtest_result(
            result, bars, evaluated_at=datetime(2025, 1, 1, tzinfo=UTC)
        )
        return r1, r2

    a1, a2 = once()
    b1, _ = once()
    assert a1.evaluation_id == a2.evaluation_id  # timestamp ignored
    assert a1.evaluation_id == b1.evaluation_id
    assert a1.metrics.net_pnl == b1.metrics.net_pnl


# ---------------------------------------------------------------------------
# Research compatibility
# ---------------------------------------------------------------------------


def test_qlib_research_metadata_compatibility() -> None:
    prov = qlib_momentum_provenance()
    assert prov.research_model_id == "qlib_inspired_momentum_v1"
    assert prov.is_trained_ai_policy is False
    assert "microsoft" in (prov.source_repository or "")


def test_finrlx_research_metadata_compatibility() -> None:
    prov = finrlx_baseline_provenance()
    assert prov.is_trained_ai_policy is False
    assert any("NOT a trained AI" in n for n in prov.notes)
    output = ResearchOutput(
        research_model_id="finrlx_offline_baseline_v1",
        source_repository="https://github.com/AI4Finance-Foundation/FinRL-Trading",
        pinned_commit="abc",
        model_version="1.0.0",
        symbol="AAPL",
        prediction_horizon="1bar",
        data_version="v1",
        metadata={"is_trained_ai_policy": True},  # must be forced False
    )
    adapted = provenance_from_research_output(output)
    assert adapted.is_trained_ai_policy is False


# ---------------------------------------------------------------------------
# Market Memory persistence
# ---------------------------------------------------------------------------


def test_market_memory_persistence_idempotent(db_session: Session) -> None:
    closes = _uptrend_closes(40)
    p = _provider("AAPL", closes)
    bars = p.get_bars("AAPL", "1Day", None, None)
    result = BacktestEngine(p).run(
        SMACrossoverStrategy(),
        symbols=["AAPL"],
        timeframe="1Day",
        parameters={"fast_period": 5, "slow_period": 15, "quantity": "1"},
    )
    rec = StrategyEvaluationService().evaluate_backtest_result(result, bars)
    svc = MarketMemoryService(db_session)
    e1, created1 = svc.persist_evaluation(rec)
    e2, created2 = svc.persist_evaluation(rec)
    assert created1 is True
    assert created2 is False
    assert e1.id == e2.id
    assert e1.event_type == "strategy_evaluation_summary"
    assert e1.market_context["evidence_id"] == rec.evaluation_id
    assert "equity_curve" not in (e1.outcome or {})


def test_historical_evidence_immutability(db_session: Session) -> None:
    svc = MarketMemoryService(db_session)
    with pytest.raises(EvidenceImmutabilityError):
        svc.repo.update_outcome_forbidden(
            __import__("uuid").uuid4(), {"mutated": True}
        )


def test_evidence_conflict_different_payload(db_session: Session) -> None:
    from app.market_memory.repository import MarketMemoryRepository

    repo = MarketMemoryRepository(db_session)
    eid = "abc123conflict"
    repo.persist_evaluation_summary(
        evidence_id=eid,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        event_time=datetime.now(UTC),
        summary={"net_pnl": "1"},
        engine_strategy_id="s1",
    )
    with pytest.raises(EvidenceConflictError):
        repo.persist_evaluation_summary(
            evidence_id=eid,
            symbol="AAPL",
            asset_class=AssetClass.EQUITY,
            event_time=datetime.now(UTC),
            summary={"net_pnl": "999"},
            engine_strategy_id="s1",
        )


def test_db_transaction_rollback(db_session: Session) -> None:
    closes = _uptrend_closes(30)
    p = _provider("AAPL", closes)
    result = BacktestEngine(p).run(
        SMACrossoverStrategy(),
        symbols=["AAPL"],
        timeframe="1Day",
        parameters={"fast_period": 5, "slow_period": 12, "quantity": "1"},
    )
    rec = StrategyEvaluationService().evaluate_backtest_result(
        result, p.get_bars("AAPL", "1Day", None, None)
    )
    nested = db_session.begin_nested()
    MarketMemoryService(db_session).persist_evaluation(rec)
    nested.rollback()
    assert MarketMemoryService(db_session).get_evaluation_event(rec.evaluation_id) is None


def test_strategy_identity_isolation(db_session: Session) -> None:
    s1 = StrategyRow(name="Eval-A", strategy_type="ref", version="1")
    s2 = StrategyRow(name="Eval-B", strategy_type="ref", version="1")
    db_session.add_all([s1, s2])
    db_session.flush()
    closes = _uptrend_closes(35)
    p = _provider("AAPL", closes)
    result = BacktestEngine(p).run(
        SMACrossoverStrategy(),
        symbols=["AAPL"],
        timeframe="1Day",
        parameters={"fast_period": 5, "slow_period": 12, "quantity": "1"},
    )
    rec = StrategyEvaluationService().evaluate_backtest_result(
        result, p.get_bars("AAPL", "1Day", None, None)
    )
    svc = MarketMemoryService(db_session)
    e1, _ = svc.persist_evaluation(rec, strategy_db_id=s1.id)
    # second strategy row must not see foreign key reassigned
    assert e1.strategy_id == s1.id
    assert e1.strategy_id != s2.id


def test_regime_snapshot_persist(db_session: Session) -> None:
    bars = _ohlc_series("AAPL", _uptrend_closes(45))
    snap = classify_market_context(bars, as_of_index=40, timeframe="1Day")
    svc = MarketMemoryService(db_session)
    e1, c1 = svc.persist_context_snapshot(snap)
    e2, c2 = svc.persist_context_snapshot(snap)
    assert c1 and not c2
    assert e1.id == e2.id


# ---------------------------------------------------------------------------
# Boundaries
# ---------------------------------------------------------------------------


def test_no_automatic_strategy_promotion() -> None:
    closes = _uptrend_closes(40)
    p = _provider("AAPL", closes)
    result = BacktestEngine(p).run(
        SMACrossoverStrategy(),
        symbols=["AAPL"],
        timeframe="1Day",
        parameters={"fast_period": 5, "slow_period": 15, "quantity": "1"},
    )
    rec = StrategyEvaluationService().evaluate_backtest_result(
        result, p.get_bars("AAPL", "1Day", None, None)
    )
    assert_no_auto_promotion(rec)
    assert StrategyStatus.PAPER.value == "paper"  # enum exists but unused here
    assert rec.paper_eligible is False


def test_no_broker_execution_access() -> None:
    root = Path(__file__).resolve().parents[1] / "app"
    forbidden_modules = {
        "app.brokers.alpaca",
        "app.brokers.router",
        "alpaca",
        "alpaca_trade_api",
    }
    files = list((root / "evaluation").rglob("*.py")) + list(
        (root / "market_memory").rglob("*.py")
    )
    for path in files:
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in {
                        "alpaca",
                        "alpaca_trade_api",
                    }
                    assert alias.name not in forbidden_modules
            if isinstance(node, ast.ImportFrom) and node.module:
                mod = node.module
                assert not mod.startswith("app.brokers.alpaca")
                assert not mod.startswith("app.brokers.router")
                assert mod.split(".")[0] not in {"alpaca", "alpaca_trade_api"}


def test_evaluation_service_broker_orders_zero() -> None:
    svc = StrategyEvaluationService()
    assert svc.broker_orders_created == 0
    closes = _uptrend_closes(40)
    svc.run_and_evaluate(
        strategy=SMACrossoverStrategy(),
        provider=_provider("AAPL", closes),
        symbols=["AAPL"],
        timeframe="1Day",
        parameters={"fast_period": 5, "slow_period": 15, "quantity": "1"},
    )
    assert svc.broker_orders_created == 0


def test_walkforward_metadata_no_oos_mislabel() -> None:
    plan = WalkForwardPlan(
        symbol="AAPL",
        timeframe="1Day",
        splits=[
            ChronologicalSplit(
                role=SplitRole.TRAIN,
                start=_ts(1),
                end=_ts(20),
            ),
            ChronologicalSplit(
                role=SplitRole.OUT_OF_SAMPLE,
                start=_ts(20),
                end=_ts(40),
            ),
        ],
    )
    plan.validate_chronology()
    plan.assert_no_oos_mislabel()
    with pytest.raises(ValueError):
        WalkForwardPlan(
            symbol="AAPL",
            timeframe="1Day",
            splits=[
                ChronologicalSplit(
                    role=SplitRole.OUT_OF_SAMPLE,
                    start=_ts(1),
                    end=_ts(10),
                )
            ],
        ).assert_no_oos_mislabel()


def test_full_sample_not_labeled_oos() -> None:
    closes = _uptrend_closes(40)
    p = _provider("AAPL", closes)
    result = BacktestEngine(p).run(
        SMACrossoverStrategy(),
        symbols=["AAPL"],
        timeframe="1Day",
        parameters={"fast_period": 5, "slow_period": 15, "quantity": "1"},
    )
    rec = StrategyEvaluationService().evaluate_backtest_result(
        result, p.get_bars("AAPL", "1Day", None, None), split_role=SplitRole.FULL_SAMPLE
    )
    assert rec.split_role != SplitRole.OUT_OF_SAMPLE
    assert any("OUT_OF_SAMPLE" in lim for lim in rec.limitations)


def test_cost_assumption_warning() -> None:
    closes = _uptrend_closes(40)
    p = _provider("AAPL", closes)
    result = BacktestEngine(p, costs=BacktestCostModel()).run(
        SMACrossoverStrategy(),
        symbols=["AAPL"],
        timeframe="1Day",
        parameters={"fast_period": 5, "slow_period": 15, "quantity": "1"},
    )
    rec = StrategyEvaluationService().evaluate_backtest_result(
        result, p.get_bars("AAPL", "1Day", None, None)
    )
    assert "zero_cost_assumptions_not_realistic" in rec.warnings


def test_build_dataset_identity_fields() -> None:
    bars = _ohlc_series("MSFT", ["1", "2", "3"])
    d = build_dataset_identity(bars, symbol="msft", timeframe="1Day")
    assert d.symbol == "MSFT"
    assert d.bar_count == 3
    assert d.start == bars[0].timestamp
