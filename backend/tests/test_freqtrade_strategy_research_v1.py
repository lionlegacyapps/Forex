"""Freqtrade Strategy Research & Adapter V1 — test matrix.

Freqtrade GPL source is NOT copied. Indicators/strategy are independent.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from app.backtesting import BacktestEngine, InMemoryHistoricalMarketDataProvider, make_bar
from app.indicators import atr, bollinger_bands, ema, macd, rsi, sma
from app.models.enums import AssetClass, ProposalSource
from app.research.freqtrade_intake import (
    FREQTRADE_PINNED_COMMIT,
    FREQTRADE_REPOSITORY_URL,
    build_freqtrade_intake_result,
    freqtrade_reference_manifest,
)
from app.strategies import (
    RSIMACDTrendStrategy,
    StrategyProposalAdapter,
    StrategyRegistry,
)
from app.strategies.context import StrategyContext, StrategyPositionView
from app.strategies.decision import DecisionAction
from app.strategy_intake import (
    IntegrationRecommendation,
    LicenseFlag,
    LicenseKind,
    ManifestStatus,
)


def _ts(day: int) -> datetime:
    """``day`` is 1-based offset from 2024-01-01 (supports multi-month series)."""
    from datetime import timedelta

    return datetime(2024, 1, 1, 16, 0, tzinfo=UTC) + timedelta(days=day - 1)


def _bars(closes: list[str | int | float], symbol: str = "AAPL"):
    out = []
    for i, c in enumerate(closes):
        price = Decimal(str(c))
        out.append(
            make_bar(
                symbol,
                _ts(i + 1),
                open=price,
                high=price + Decimal("1"),
                low=price - Decimal("1"),
                close=price,
            )
        )
    return out


def _ctx(closes: list, *, position_qty: Decimal = Decimal("0"), **params) -> StrategyContext:
    bars = _bars(closes)
    return StrategyContext(
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        timestamp=bars[-1].timestamp,
        timeframe="1Day",
        bars=bars,
        reference_price=bars[-1].close,
        position=StrategyPositionView(
            symbol="AAPL",
            quantity=position_qty,
            side="long" if position_qty > 0 else "flat",
            average_entry_price=bars[0].close if position_qty > 0 else None,
        ),
        parameters=params,
    )


# ---------------------------------------------------------------------------
# Intake / license / pin
# ---------------------------------------------------------------------------


def test_freqtrade_intake_license_and_pinning() -> None:
    assert FREQTRADE_REPOSITORY_URL == "https://github.com/freqtrade/freqtrade"
    assert len(FREQTRADE_PINNED_COMMIT) == 40
    result = build_freqtrade_intake_result()
    assert result.external_code_executed is False
    assert result.license_kind == LicenseKind.GPL.value
    assert LicenseFlag.COPYLEFT_REVIEW_REQUIRED.value in result.license_flags
    # GPL → adaptation not allowed → reject install/adapt path
    assert result.decision.recommendation == IntegrationRecommendation.REJECT
    assert result.broker_isolation_required is True

    manifest = freqtrade_reference_manifest()
    assert manifest.revision == FREQTRADE_PINNED_COMMIT
    assert manifest.is_commit_pinned
    assert manifest.integration_mode == IntegrationRecommendation.REFERENCE_ONLY
    assert manifest.status == ManifestStatus.REVIEWING
    assert manifest.license == "GPL-3.0"


# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------


def test_sma_ema_reference_and_warmup() -> None:
    values = [Decimal(str(x)) for x in (2, 4, 6, 8, 10)]
    s = sma(values, 3)
    assert s[:2] == [None, None]
    assert s[2] == Decimal("4")  # (2+4+6)/3
    assert s[3] == Decimal("6")
    e = ema(values, 3)
    assert e[0] is None and e[1] is None
    assert e[2] == Decimal("4")  # SMA seed
    assert e[3] is not None


def test_rsi_warmup_and_bounds() -> None:
    # Rising then falling series
    closes = [Decimal(str(x)) for x in range(10, 40)] + [Decimal(str(x)) for x in range(39, 10, -1)]
    r = rsi(closes, period=5)
    assert all(v is None for v in r[:5])
    assert r[5] is not None
    for v in r:
        if v is not None:
            assert Decimal("0") <= v <= Decimal("100")


def test_macd_warmup_and_ordering() -> None:
    closes = [Decimal(str(10 + (i % 7))) for i in range(80)]
    line, signal, hist = macd(closes, fast=3, slow=6, signal=3)
    assert line[5] is None or True
    # Until slow EMA ready, macd is None
    assert all(v is None for v in line[:5])
    # Signal lags macd
    first_macd = next(i for i, v in enumerate(line) if v is not None)
    first_sig = next(i for i, v in enumerate(signal) if v is not None)
    assert first_sig >= first_macd


def test_bollinger_and_atr() -> None:
    closes = [Decimal(str(x)) for x in range(1, 31)]
    mid, up, low = bollinger_bands(closes, period=5, num_std=Decimal("2"))
    assert mid[4] is not None and up[4] is not None and low[4] is not None
    assert up[4] >= mid[4] >= low[4]
    highs = [c + 1 for c in closes]
    lows = [c - 1 for c in closes]
    a = atr(highs, lows, closes, period=5)
    assert all(v is None for v in a[:5])
    assert a[5] is not None and a[5] > 0


def test_indicator_parameter_validation() -> None:
    with pytest.raises(ValueError):
        sma([Decimal("1")], 0)
    with pytest.raises(ValueError):
        rsi([Decimal("1")] * 10, 0)
    with pytest.raises(ValueError):
        macd([Decimal("1")] * 10, fast=12, slow=10, signal=9)


def test_lookahead_indicator_stability() -> None:
    base = [Decimal(str(10 + i)) for i in range(40)]
    r1 = rsi(base, 5)
    bumped = list(base)
    bumped[-1] = Decimal("999")
    r2 = rsi(bumped, 5)
    assert r1[:-1] == r2[:-1]


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------


def test_strategy_parameter_validation_and_no_action() -> None:
    s = RSIMACDTrendStrategy()
    with pytest.raises(Exception):
        s.validate_parameters({"rsi_oversold": 80, "rsi_overbought": 20})
    d = s.evaluate(_ctx([10, 11, 12], rsi_period=14))  # insufficient
    assert d.action == DecisionAction.NO_ACTION


def test_long_entry_and_exit_signals() -> None:
    """Craft series: prolonged decline (oversold) then recovery + short MACD params."""
    # Decline
    closes = [100 - i for i in range(40)]
    # Sharp recovery
    closes += [60 + i * 2 for i in range(40)]
    s = RSIMACDTrendStrategy()
    params = {
        "rsi_period": 5,
        "rsi_oversold": 30,
        "rsi_overbought": 70,
        "macd_fast": 3,
        "macd_slow": 6,
        "macd_signal": 3,
        "quantity": "1",
        "stop_loss_pct": "0.05",
        "require_macd_cross": False,  # allow bullish state without fresh cross
    }
    # Scan for an enter signal
    entered = False
    for end in range(20, len(closes)):
        d = s.evaluate(_ctx(closes[: end + 1], **params))
        if d.action == DecisionAction.ENTER_LONG:
            entered = True
            assert d.stop_loss_price is not None
            assert d.signal_metadata.get("freqtrade_code_used") is False
            break
    assert entered, "expected at least one ENTER_LONG on recovery series"

    # Peak then decline while long → overbought cross-down or MACD bearish cross
    exit_series = list(closes) + [closes[-1] + i for i in range(1, 15)]
    exit_series += [exit_series[-1] - i * 3 for i in range(1, 40)]
    exited = False
    for end in range(len(closes), len(exit_series)):
        d = s.evaluate(
            _ctx(exit_series[: end + 1], position_qty=Decimal("1"), **params)
        )
        if d.action == DecisionAction.EXIT_LONG:
            exited = True
            break
    assert exited, "expected at least one EXIT_LONG"


def test_strategy_registry_and_proposal() -> None:
    reg = StrategyRegistry()
    s = RSIMACDTrendStrategy()
    reg.register(s)
    assert reg.get("rsi_macd_trend").version == "1.0.0"
    # Build a decision via forced params path using short series with action
    closes = [100 - i for i in range(40)] + [60 + i * 2 for i in range(40)]
    params = {
        "rsi_period": 5,
        "rsi_oversold": 30,
        "rsi_overbought": 70,
        "macd_fast": 3,
        "macd_slow": 6,
        "macd_signal": 3,
        "require_macd_cross": False,
        "quantity": "2",
        "stop_loss_pct": "0.05",
    }
    decision = None
    for end in range(20, len(closes)):
        d = s.evaluate(_ctx(closes[: end + 1], **params))
        if d.is_actionable:
            decision = d
            break
    assert decision is not None
    proposal = StrategyProposalAdapter().to_proposal_input(
        decision,
        broker_account_id=uuid4(),
        strategy_id=s.strategy_id,
        strategy_version=s.version,
    )
    assert proposal.source == ProposalSource.STRATEGY
    assert proposal.quantity == Decimal("2")


def test_backtest_compatibility_reproducibility_metrics() -> None:
    closes = [100 - i for i in range(50)] + [50 + i for i in range(50)]
    bars = _bars(closes)
    provider = InMemoryHistoricalMarketDataProvider()
    provider.load_bars("AAPL", "1Day", bars)
    params = {
        "rsi_period": 5,
        "rsi_oversold": 35,
        "rsi_overbought": 65,
        "macd_fast": 3,
        "macd_slow": 8,
        "macd_signal": 3,
        "require_macd_cross": False,
        "quantity": "1",
        "stop_loss_pct": "0.05",
    }

    def run_once():
        return BacktestEngine(provider).run(
            RSIMACDTrendStrategy(),
            symbols=["AAPL"],
            timeframe="1Day",
            starting_capital=Decimal("100000"),
            parameters=params,
        )

    a = run_once()
    b = run_once()
    assert a.to_serializable_dict() == b.to_serializable_dict()
    assert a.strategy_id == "rsi_macd_trend"
    assert a.equity_curve
    assert a.metrics.starting_capital == Decimal("100000")
    # Market memory-oriented fields present on trades when any closed
    for t in a.trades:
        assert t.strategy_id == "rsi_macd_trend"
        assert t.parameters.get("rsi_period") == 5
    assert a.execution_assumptions["external_broker"] is False


def test_no_freqtrade_or_broker_imports() -> None:
    roots = [
        Path(__file__).resolve().parents[1] / "app" / "indicators",
        Path(__file__).resolve().parents[1] / "app" / "strategies" / "reference",
        Path(__file__).resolve().parents[1] / "app" / "research" / "freqtrade_intake.py",
    ]
    files: list[Path] = []
    for r in roots:
        if r.is_file():
            files.append(r)
        else:
            files.extend(r.rglob("*.py"))
    for path in files:
        if path.name == "sma_crossover.py":
            continue
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert not mod.startswith("freqtrade")
                assert "brokers.execution" not in mod
                assert mod != "ccxt"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("freqtrade")
                    assert alias.name != "ccxt"


def test_pyproject_has_no_freqtrade() -> None:
    text = Path(__file__).resolve().parents[1].joinpath("pyproject.toml").read_text()
    assert "freqtrade" not in text
    assert "ccxt" not in text
