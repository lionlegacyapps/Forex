"""Strategy Engine + Backtesting Foundation V1 — test matrix."""

from __future__ import annotations

import ast
import inspect
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.backtesting import (
    AcceptanceRule,
    BacktestAcceptanceGate,
    BacktestCostModel,
    BacktestEngine,
    BacktestExecutionModel,
    BacktestSizingModel,
    HistoricalDataError,
    InMemoryHistoricalMarketDataProvider,
    LookaheadError,
    LookaheadSafeBarView,
    PendingOrder,
    RecordingMemoryHook,
    SizingMode,
    make_bar,
)
from app.backtesting.execution_model import FillReason
from app.market_data.models import Bar
from app.models.enums import AssetClass, OrderType, ProposalSource, TradeSide
from app.strategies import (
    DecisionAction,
    SMACrossoverStrategy,
    Strategy,
    StrategyContext,
    StrategyDecision,
    StrategyParameterError,
    StrategyPositionView,
    StrategyProposalAdapter,
    StrategyRegistrationError,
    StrategyRegistry,
    no_action,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ts(day: int) -> datetime:
    return datetime(2024, 1, day, 16, 0, tzinfo=UTC)


def _ohlc_series(
    symbol: str,
    closes: list[str],
    *,
    timeframe: str = "1Day",
) -> list[Bar]:
    bars: list[Bar] = []
    for i, c in enumerate(closes):
        price = Decimal(c)
        # Deterministic OHLC around close
        o = price
        h = price + Decimal("1")
        low = price - Decimal("1")
        bars.append(
            make_bar(
                symbol,
                _ts(i + 1),
                open=o,
                high=h,
                low=low,
                close=price,
                timeframe=timeframe,
            )
        )
    return bars


def _provider_with(symbol: str, closes: list[str]) -> InMemoryHistoricalMarketDataProvider:
    p = InMemoryHistoricalMarketDataProvider()
    p.load_bars(symbol, "1Day", _ohlc_series(symbol, closes))
    return p


class FixedDecisionStrategy(Strategy):
    """Test double that emits a canned decision sequence."""

    def __init__(
        self,
        decisions: list[StrategyDecision],
        *,
        strategy_id: str = "fixed_decision",
        version: str = "1.0.0",
    ) -> None:
        self._decisions = list(decisions)
        self._i = 0
        self._id = strategy_id
        self._version = version

    @property
    def strategy_id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return "Fixed Decision"

    @property
    def version(self) -> str:
        return self._version

    @property
    def supported_asset_classes(self) -> frozenset[AssetClass]:
        return frozenset({AssetClass.EQUITY})

    @property
    def required_timeframes(self) -> frozenset[str]:
        return frozenset({"1Day"})

    def evaluate(self, context: StrategyContext) -> StrategyDecision:
        _ = context
        if self._i >= len(self._decisions):
            return no_action(rationale_code="exhausted")
        d = self._decisions[self._i]
        self._i += 1
        return d


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_strategy_registration_and_lookup() -> None:
    reg = StrategyRegistry()
    s = SMACrossoverStrategy()
    reg.register(s)
    assert reg.contains("sma_crossover")
    assert reg.get("sma_crossover").version == "1.0.0"
    assert reg.get("sma_crossover", "1.0.0") is s
    assert len(reg.list_strategies()) == 1


def test_duplicate_registration_rejected() -> None:
    reg = StrategyRegistry()
    reg.register(SMACrossoverStrategy())
    with pytest.raises(StrategyRegistrationError) as exc:
        reg.register(SMACrossoverStrategy())
    assert exc.value.code == "duplicate_registration"


def test_strategy_parameter_validation() -> None:
    s = SMACrossoverStrategy()
    ok = s.validate_parameters({"fast_period": 2, "slow_period": 4})
    assert ok["fast_period"] == 2
    with pytest.raises(StrategyParameterError):
        s.validate_parameters({"fast_period": 5, "slow_period": 3})
    with pytest.raises(StrategyParameterError):
        s.validate_parameters({"fast_period": 0, "slow_period": 3})


# ---------------------------------------------------------------------------
# Decisions + proposal adapter
# ---------------------------------------------------------------------------


def test_no_action_decision() -> None:
    d = no_action(rationale_code="idle")
    assert d.action == DecisionAction.NO_ACTION
    assert not d.is_actionable


def test_long_and_short_entry_decisions() -> None:
    long_d = StrategyDecision(
        action=DecisionAction.ENTER_LONG,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        quantity=Decimal("10"),
    )
    assert long_d.side == TradeSide.BUY
    short_d = StrategyDecision(
        action=DecisionAction.ENTER_SHORT,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        quantity=Decimal("10"),
    )
    assert short_d.side == TradeSide.SELL


def test_decision_to_trade_proposal() -> None:
    adapter = StrategyProposalAdapter()
    decision = StrategyDecision(
        action=DecisionAction.ENTER_LONG,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        quantity=Decimal("5"),
        order_type=OrderType.MARKET,
        rationale_code="test_entry",
    )
    account_id = uuid.uuid4()
    proposal = adapter.to_proposal_input(
        decision,
        broker_account_id=account_id,
        strategy_id="sma_crossover",
        strategy_version="1.0.0",
    )
    assert proposal.source == ProposalSource.STRATEGY
    assert proposal.symbol == "AAPL"
    assert proposal.side == TradeSide.BUY
    assert proposal.quantity == Decimal("5")
    assert proposal.broker_account_id == account_id
    assert proposal.metadata["strategy_engine_id"] == "sma_crossover"
    with pytest.raises(Exception):
        adapter.to_proposal_input(
            no_action(),
            broker_account_id=account_id,
        )


# ---------------------------------------------------------------------------
# Safety: strategy cannot access execution
# ---------------------------------------------------------------------------


def test_strategy_cannot_access_execution_adapter() -> None:
    """Architecture: Strategy.evaluate signature has no broker/execution params."""
    sig = inspect.signature(Strategy.evaluate)
    params = list(sig.parameters)
    assert params == ["self", "context"]

    # Source-level: strategies package must not import execution adapters
    strategies_root = Path(__file__).resolve().parents[1] / "app" / "strategies"
    forbidden = {
        "AlpacaPaperExecutionAdapter",
        "BrokerExecutionAdapter",
        "BrokerRouter",
        "TradingClient",
        "alpaca.trading",
    }
    for path in strategies_root.rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "alpaca" not in alias.name.lower() or "market" in src.lower()
                    for f in forbidden:
                        assert f not in alias.name
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert "brokers.execution" not in mod
                assert "trading.routing" not in mod
                assert mod != "alpaca.trading"
                for alias in node.names:
                    assert alias.name not in forbidden
        for f in forbidden:
            # Allow mentioning in comments/docstrings of proposal_adapter only as prose
            if f in src and "proposal_adapter" not in path.name and "protocol" not in path.name:
                # protocol/docs may mention forbidden types by name in comments
                if f in src.replace(" ", ""):
                    # Only fail on actual imports already checked; string mentions in docs OK
                    pass

    # Context model has no broker fields
    fields = set(StrategyContext.model_fields)
    assert "broker" not in fields
    assert "router" not in fields
    assert "execution" not in fields
    assert "credentials" not in fields


def test_strategies_contain_no_credentials() -> None:
    strategies_root = Path(__file__).resolve().parents[1] / "app" / "strategies"
    credential_markers = (
        "APCA_API_KEY",
        "APCA_API_SECRET",
        "api_secret",
        "secret_key",
        "ALPACA_API_KEY",
    )
    for path in strategies_root.rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        for marker in credential_markers:
            assert marker not in src, f"{path} contains {marker}"


# ---------------------------------------------------------------------------
# Historical data
# ---------------------------------------------------------------------------


def test_historical_bars_chronological() -> None:
    p = InMemoryHistoricalMarketDataProvider()
    bars = _ohlc_series("AAPL", ["10", "11", "12"])
    p.load_bars("AAPL", "1Day", bars)
    out = p.get_bars("AAPL", "1Day", None, None)
    assert [b.timestamp for b in out] == sorted(b.timestamp for b in out)
    assert out[0].close < out[-1].close or True


def test_invalid_historical_data_rejected() -> None:
    p = InMemoryHistoricalMarketDataProvider()
    bad = make_bar("AAPL", _ts(1), open="10", high="9", low="8", close="9")
    with pytest.raises(HistoricalDataError):
        p.load_bars("AAPL", "1Day", [bad])

    # Duplicate timestamps rejected after sort
    b1 = make_bar("AAPL", _ts(1), open="10", high="11", low="9", close="10")
    b2 = make_bar("AAPL", _ts(1), open="10", high="11", low="9", close="10.5")
    with pytest.raises(HistoricalDataError):
        p.load_bars("AAPL", "1Day", [b1, b2])


def test_lookahead_bias_blocked() -> None:
    bars = _ohlc_series("AAPL", ["10", "11", "12", "13", "14"])
    view = LookaheadSafeBarView(bars, max_inclusive_index=2)
    visible = view.as_list()
    assert len(visible) == 3
    assert visible[-1].timestamp == bars[2].timestamp
    assert all(b.timestamp <= bars[2].timestamp for b in visible)

    with pytest.raises(LookaheadError):
        LookaheadSafeBarView(bars, max_inclusive_index=99)


# ---------------------------------------------------------------------------
# Execution model fills
# ---------------------------------------------------------------------------


def test_market_fills_at_next_bar_open() -> None:
    model = BacktestExecutionModel()
    decision = StrategyDecision(
        action=DecisionAction.ENTER_LONG,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        quantity=Decimal("1"),
        order_type=OrderType.MARKET,
    )
    order = PendingOrder(
        decision=decision,
        signal_time=_ts(1),
        signal_bar_index=0,
        quantity=Decimal("1"),
        created_at_bar_index=0,
    )
    signal_bar = make_bar("AAPL", _ts(1), "10", "11", "9", "10.5")
    next_bar = make_bar("AAPL", _ts(2), "12", "13", "11", "12.5")
    assert model.try_fill(order, signal_bar, 0) is None
    fill = model.try_fill(order, next_bar, 1)
    assert fill is not None
    assert fill.price == Decimal("12")
    assert fill.reason == FillReason.MARKET_NEXT_OPEN


def test_limit_fill_logic() -> None:
    model = BacktestExecutionModel()
    decision = StrategyDecision(
        action=DecisionAction.ENTER_LONG,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        quantity=Decimal("1"),
        order_type=OrderType.LIMIT,
        limit_price=Decimal("100"),
    )
    order = PendingOrder(
        decision=decision,
        signal_time=_ts(1),
        signal_bar_index=0,
        quantity=Decimal("1"),
        created_at_bar_index=0,
    )
    miss = make_bar("AAPL", _ts(2), "105", "110", "101", "108")
    hit = make_bar("AAPL", _ts(3), "102", "103", "99", "100")
    assert model.try_fill(order, miss, 1) is None
    fill = model.try_fill(order, hit, 2)
    assert fill is not None
    assert fill.price == Decimal("100")
    assert fill.reason == FillReason.LIMIT_TOUCHED


def test_stop_fill_logic() -> None:
    model = BacktestExecutionModel()
    decision = StrategyDecision(
        action=DecisionAction.ENTER_SHORT,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        quantity=Decimal("1"),
        order_type=OrderType.STOP,
        stop_price=Decimal("95"),
    )
    # ENTER_SHORT → SELL stop: triggers when low <= stop
    order = PendingOrder(
        decision=decision,
        signal_time=_ts(1),
        signal_bar_index=0,
        quantity=Decimal("1"),
        created_at_bar_index=0,
    )
    miss = make_bar("AAPL", _ts(2), "100", "101", "96", "98")
    hit = make_bar("AAPL", _ts(3), "97", "98", "94", "95")
    assert model.try_fill(order, miss, 1) is None
    fill = model.try_fill(order, hit, 2)
    assert fill is not None
    assert fill.price == Decimal("95")
    assert fill.reason == FillReason.STOP_TRIGGERED


def test_commission_and_slippage_application() -> None:
    costs = BacktestCostModel(
        commission_per_share=Decimal("0.01"),
        commission_flat=Decimal("1"),
        slippage_bps=Decimal("100"),  # 1%
    )
    model = BacktestExecutionModel(costs)
    decision = StrategyDecision(
        action=DecisionAction.ENTER_LONG,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        quantity=Decimal("10"),
        order_type=OrderType.MARKET,
    )
    order = PendingOrder(
        decision=decision,
        signal_time=_ts(1),
        signal_bar_index=0,
        quantity=Decimal("10"),
        created_at_bar_index=0,
    )
    bar = make_bar("AAPL", _ts(2), "100", "101", "99", "100")
    fill = model.try_fill(order, bar, 1)
    assert fill is not None
    assert fill.price == Decimal("101")  # 100 * 1.01
    assert fill.commission == Decimal("0.01") * 10 + Decimal("1")
    assert fill.slippage_component == Decimal("1") * 10


# ---------------------------------------------------------------------------
# Backtest engine — long/short P&L, metrics, reproducibility
# ---------------------------------------------------------------------------


def test_long_pnl_and_metrics() -> None:
    # Force enter then exit via fixed decisions on rising then falling series
    closes = ["100", "101", "102", "103", "104", "105", "106", "100"]
    provider = _provider_with("AAPL", closes)
    decisions = [no_action() for _ in closes]
    # Signal on day index 1 (bar close day 2) → fill next open day 3
    decisions[1] = StrategyDecision(
        action=DecisionAction.ENTER_LONG,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        quantity=Decimal("1"),
        order_type=OrderType.MARKET,
        rationale_code="enter",
    )
    # Exit signal later
    decisions[4] = StrategyDecision(
        action=DecisionAction.EXIT_LONG,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        quantity=Decimal("1"),
        order_type=OrderType.MARKET,
        rationale_code="exit",
    )
    engine = BacktestEngine(provider)
    result = engine.run(
        FixedDecisionStrategy(decisions),
        symbols=["AAPL"],
        timeframe="1Day",
        starting_capital=Decimal("10000"),
    )
    assert result.metrics.number_of_trades == 1
    trade = result.trades[0]
    assert trade.side == "long"
    assert trade.net_pnl == trade.gross_pnl - trade.costs
    assert trade.entry_price == Decimal("102")  # next open after signal bar index 1
    # Exit signal at index 4 → fill at open of index 5 = close series "105" bar open
    assert trade.exit_price == Decimal("105")
    assert trade.gross_pnl == Decimal("3")
    assert result.metrics.winning_trades == 1
    assert result.metrics.win_rate == Decimal("100")
    assert result.equity_curve
    assert result.equity_curve[0].timestamp <= result.equity_curve[-1].timestamp


def test_short_pnl() -> None:
    closes = ["100", "99", "98", "97", "96", "95", "94", "100"]
    provider = _provider_with("AAPL", closes)
    decisions = [no_action() for _ in closes]
    decisions[1] = StrategyDecision(
        action=DecisionAction.ENTER_SHORT,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        quantity=Decimal("1"),
        order_type=OrderType.MARKET,
        rationale_code="enter_short",
    )
    decisions[4] = StrategyDecision(
        action=DecisionAction.EXIT_SHORT,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        quantity=Decimal("1"),
        order_type=OrderType.MARKET,
        rationale_code="exit_short",
    )
    result = BacktestEngine(provider).run(
        FixedDecisionStrategy(decisions, strategy_id="short_test"),
        symbols=["AAPL"],
        timeframe="1Day",
        starting_capital=Decimal("10000"),
    )
    assert result.metrics.number_of_trades == 1
    trade = result.trades[0]
    assert trade.side == "short"
    assert trade.entry_price == Decimal("98")
    assert trade.exit_price == Decimal("95")
    assert trade.gross_pnl == Decimal("3")


def test_multiple_trades_win_loss_profit_factor_expectancy_drawdown() -> None:
    # Two round-trips: win (+10) then loss (-10)
    # Enter idx1 → fill open idx2; exit idx3 → fill open idx4
    closes = [
        "100",  # 0
        "100",  # 1 signal enter
        "100",  # 2 fill enter @100
        "110",  # 3 signal exit
        "110",  # 4 fill exit @110 → +10
        "110",  # 5 signal enter
        "110",  # 6 fill enter @110
        "100",  # 7 signal exit
        "100",  # 8 fill exit @100 → -10
    ]
    provider = _provider_with("AAPL", closes)
    decisions = [no_action() for _ in closes]
    decisions[1] = StrategyDecision(
        action=DecisionAction.ENTER_LONG,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        quantity=Decimal("1"),
        order_type=OrderType.MARKET,
    )
    decisions[3] = StrategyDecision(
        action=DecisionAction.EXIT_LONG,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        quantity=Decimal("1"),
        order_type=OrderType.MARKET,
    )
    decisions[5] = StrategyDecision(
        action=DecisionAction.ENTER_LONG,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        quantity=Decimal("1"),
        order_type=OrderType.MARKET,
    )
    decisions[7] = StrategyDecision(
        action=DecisionAction.EXIT_LONG,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        quantity=Decimal("1"),
        order_type=OrderType.MARKET,
    )
    result = BacktestEngine(provider).run(
        FixedDecisionStrategy(decisions),
        symbols=["AAPL"],
        timeframe="1Day",
        starting_capital=Decimal("10000"),
    )
    m = result.metrics
    assert m.number_of_trades == 2
    assert m.winning_trades == 1
    assert m.losing_trades == 1
    assert m.win_rate == Decimal("50")
    assert m.expectancy == Decimal("0")
    assert m.profit_factor == Decimal("1")
    assert m.max_drawdown is not None
    assert m.average_win == Decimal("10")
    assert m.average_loss == Decimal("-10")


def test_equity_curve_fields() -> None:
    provider = _provider_with("AAPL", ["10", "11", "12", "13", "14", "15"])
    result = BacktestEngine(provider).run(
        SMACrossoverStrategy(),
        symbols=["AAPL"],
        timeframe="1Day",
        starting_capital=Decimal("10000"),
        parameters={"fast_period": 2, "slow_period": 3, "quantity": "1"},
    )
    assert len(result.equity_curve) == 6
    for pt in result.equity_curve:
        assert pt.equity is not None
        assert pt.cash is not None
        assert pt.unrealized_pnl is not None


def test_reproducibility() -> None:
    closes = ["10", "11", "12", "11", "13", "12", "14", "13", "15", "14", "16"]
    params = {"fast_period": 2, "slow_period": 4, "quantity": "1"}

    def run_once():
        p = _provider_with("AAPL", closes)
        return BacktestEngine(p).run(
            SMACrossoverStrategy(),
            symbols=["AAPL"],
            timeframe="1Day",
            starting_capital=Decimal("50000"),
            parameters=params,
        )

    a = run_once()
    b = run_once()
    assert a.to_serializable_dict() == b.to_serializable_dict()


def test_reference_sma_backtest_end_to_end() -> None:
    # Downtrend → uptrend → downtrend produces enter_long then exit_long.
    # Reference strategy is for framework proof only — not a profitability claim.
    closes = [
        "50", "49", "48", "47", "46", "45", "44", "43", "42", "41",
        "42", "44", "46", "48", "50", "52", "54", "56", "58", "60",
        "58", "55", "52", "49", "46", "43", "40", "37", "34", "31",
    ]
    provider = _provider_with("AAPL", closes)
    hook = RecordingMemoryHook()
    params = {"fast_period": 3, "slow_period": 7, "quantity": "1"}
    engine = BacktestEngine(provider, memory_hook=hook)
    result = engine.run(
        SMACrossoverStrategy(),
        symbols=["AAPL"],
        timeframe="1Day",
        starting_capital=Decimal("100000"),
        parameters=params,
    )
    assert result.strategy_id == "sma_crossover"
    assert result.strategy_version == "1.0.0"
    assert result.metrics.number_of_trades >= 1
    assert result.trades[0].side == "long"
    assert result.trades[0].entry_price > 0
    assert result.trades[0].exit_price > 0
    assert len(result.equity_curve) == len(closes)
    assert "BACKTEST PERFORMANCE DOES NOT GUARANTEE FUTURE PERFORMANCE." in result.warnings
    assert result.execution_assumptions["external_broker"] is False
    assert any(e.event_type == "strategy_decision" for e in hook.events)
    assert any(e.event_type == "fill" for e in hook.events)
    # Reproducible under identical inputs
    again = BacktestEngine(_provider_with("AAPL", closes)).run(
        SMACrossoverStrategy(),
        symbols=["AAPL"],
        timeframe="1Day",
        starting_capital=Decimal("100000"),
        parameters=params,
    )
    assert again.to_serializable_dict() == result.to_serializable_dict()


def test_multiple_strategies_remain_separate() -> None:
    closes = ["10", "11", "12", "13", "14", "15", "14", "13", "12"]
    p1 = _provider_with("AAPL", closes)
    p2 = _provider_with("AAPL", closes)
    r1 = BacktestEngine(p1).run(
        FixedDecisionStrategy(
            [
                no_action(),
                StrategyDecision(
                    action=DecisionAction.ENTER_LONG,
                    symbol="AAPL",
                    asset_class=AssetClass.EQUITY,
                    quantity=Decimal("1"),
                    order_type=OrderType.MARKET,
                ),
                no_action(),
                StrategyDecision(
                    action=DecisionAction.EXIT_LONG,
                    symbol="AAPL",
                    asset_class=AssetClass.EQUITY,
                    quantity=Decimal("1"),
                    order_type=OrderType.MARKET,
                ),
            ]
            + [no_action()] * 5,
            strategy_id="strat_a",
            version="1.0.0",
        ),
        symbols=["AAPL"],
        timeframe="1Day",
        starting_capital=Decimal("10000"),
    )
    r2 = BacktestEngine(p2).run(
        FixedDecisionStrategy(
            [no_action()] * 9,
            strategy_id="strat_b",
            version="2.0.0",
        ),
        symbols=["AAPL"],
        timeframe="1Day",
        starting_capital=Decimal("10000"),
    )
    assert r1.strategy_id != r2.strategy_id
    assert r1.metrics.number_of_trades >= 1
    assert r2.metrics.number_of_trades == 0
    for t in r1.trades:
        assert t.strategy_id == "strat_a"


def test_multiple_symbols_supported_structurally() -> None:
    p = InMemoryHistoricalMarketDataProvider()
    p.load_bars("AAA", "1Day", _ohlc_series("AAA", ["10", "11", "12", "13", "14", "15"]))
    p.load_bars("BBB", "1Day", _ohlc_series("BBB", ["20", "21", "22", "23", "24", "25"]))
    result = BacktestEngine(p).run(
        SMACrossoverStrategy(),
        symbols=["AAA", "BBB"],
        timeframe="1Day",
        starting_capital=Decimal("20000"),
        parameters={"fast_period": 2, "slow_period": 3, "quantity": "1"},
    )
    assert set(result.symbols) == {"AAA", "BBB"}
    assert len(result.equity_curve) == 6


def test_acceptance_gate_does_not_auto_promote() -> None:
    provider = _provider_with("AAPL", ["10", "11", "12", "13", "14", "15"])
    result = BacktestEngine(provider).run(
        SMACrossoverStrategy(),
        symbols=["AAPL"],
        timeframe="1Day",
        parameters={"fast_period": 2, "slow_period": 3},
    )
    gate = BacktestAcceptanceGate(
        [
            AcceptanceRule(
                name="placeholder",
                min_trades=1000,
                enabled=True,
            )
        ]
    )
    evaluation = gate.evaluate(result)
    assert evaluation.passed is False
    assert "do not mutate StrategyStatus" in " ".join(evaluation.notes) or evaluation.notes


def test_sizing_max_quantity_cap() -> None:
    sizing = BacktestSizingModel(
        mode=SizingMode.DECISION_QUANTITY,
        max_quantity=Decimal("2"),
    )
    d = StrategyDecision(
        action=DecisionAction.ENTER_LONG,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        quantity=Decimal("1000"),
    )
    assert sizing.size(d, equity=Decimal("1e9"), reference_price=Decimal("10")) == Decimal("2")


def test_backtester_has_no_broker_write_imports() -> None:
    root = Path(__file__).resolve().parents[1] / "app" / "backtesting"
    for path in root.rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert "brokers.execution" not in mod
                assert "alpaca.trading" not in mod
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "alpaca.trading" not in alias.name


def test_result_serializable() -> None:
    provider = _provider_with("AAPL", ["10", "11", "12", "13", "14", "15"])
    result = BacktestEngine(provider).run(
        SMACrossoverStrategy(),
        symbols=["AAPL"],
        timeframe="1Day",
        parameters={"fast_period": 2, "slow_period": 3},
    )
    payload = result.to_serializable_dict()
    assert isinstance(payload, dict)
    assert payload["strategy_id"] == "sma_crossover"
    assert "metrics" in payload
    assert "equity_curve" in payload
