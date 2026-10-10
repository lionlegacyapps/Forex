"""Microsoft Qlib Research Integration V1 — test matrix."""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from app.backtesting import BacktestEngine, InMemoryHistoricalMarketDataProvider, make_bar
from app.models.enums import AssetClass, ProposalSource
from app.research import (
    QLIB_PINNED_COMMIT,
    QLIB_REPOSITORY_URL,
    QlibFactorSignalAdapter,
    QlibInspiredResearchPipeline,
    bars_to_research_frame,
    build_qlib_intake_result,
    compute_momentum_factor,
    qlib_approved_adaptation_manifest,
)
from app.research.factors import assert_no_lookahead_factor
from app.research.pipeline import TrainEvalSplit
from app.research.strategy_adapter import prediction_map_from_output
from app.strategies import StrategyProposalAdapter
from app.strategies.context import StrategyContext, StrategyPositionView
from app.strategies.decision import DecisionAction
from app.strategy_intake import (
    GatedStrategyRegistry,
    IntegrationRecommendation,
    LicenseFlag,
    LicenseKind,
    ManifestStatus,
)


def _ts(day: int) -> datetime:
    return datetime(2024, 1, day, 16, 0, tzinfo=UTC)


def _bars(closes: list[str], symbol: str = "AAPL"):
    out = []
    for i, c in enumerate(closes):
        price = Decimal(c)
        out.append(
            make_bar(
                symbol,
                _ts(i + 1),
                open=price,
                high=price + 1,
                low=price - 1,
                close=price,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Intake / pinning / license / security
# ---------------------------------------------------------------------------


def test_qlib_manifest_and_commit_pinning() -> None:
    manifest = qlib_approved_adaptation_manifest()
    assert manifest.repository == QLIB_REPOSITORY_URL
    assert manifest.revision == QLIB_PINNED_COMMIT
    assert len(QLIB_PINNED_COMMIT) == 40
    assert manifest.is_commit_pinned
    assert manifest.status == ManifestStatus.APPROVED_FOR_ADAPTATION
    assert manifest.integration_mode == IntegrationRecommendation.ADAPT_ALGORITHM
    assert "qlib/backtest" in " ".join(manifest.rejected_files)


def test_qlib_license_and_security_intake() -> None:
    result = build_qlib_intake_result()
    assert result.external_code_executed is False
    assert result.license_kind == LicenseKind.MIT.value
    assert LicenseFlag.PERMISSIVE_OK.value in result.license_flags
    # Critical patterns in reviewed snippets → full runtime not trusted
    assert result.security_finding_count >= 1
    assert result.broker_isolation_required is True
    # Full-repo recommendation rejects install/execute path
    assert result.decision.recommendation == IntegrationRecommendation.REJECT
    assert "EXTERNAL GITHUB CODE IS NEVER TRUSTED BY DEFAULT." in " ".join(
        result.report.notes
    )


# ---------------------------------------------------------------------------
# Data / factors / lookahead / train-test
# ---------------------------------------------------------------------------


def test_historical_data_conversion_and_validation() -> None:
    bars = _bars(["10", "11", "12"])
    frame = bars_to_research_frame(bars, data_version="fixture-1")
    assert frame.symbol == "AAPL"
    assert len(frame.rows) == 3
    assert frame.price_convention == "as_provided"

    naive = make_bar("AAPL", datetime(2024, 1, 1, 16, 0), "10", "11", "9", "10")
    with pytest.raises(Exception):
        bars_to_research_frame([naive])


def test_feature_calculations_and_lookahead_prevention() -> None:
    frame = bars_to_research_frame(_bars([str(10 + i) for i in range(12)]))
    mom = compute_momentum_factor(frame, lookback=5)
    assert_no_lookahead_factor(mom, min_history=5)
    assert mom[5] is not None
    # Factor at t uses only prior window — mutating a future close must not change past factors
    closes_future_bump = _bars([str(10 + i) for i in range(12)])
    closes_future_bump[-1] = make_bar(
        "AAPL",
        _ts(12),
        open=Decimal("999"),
        high=Decimal("1000"),
        low=Decimal("998"),
        close=Decimal("999"),
    )
    mom2 = compute_momentum_factor(bars_to_research_frame(closes_future_bump), lookback=5)
    assert mom[:-1] == mom2[:-1]


def test_training_test_separation() -> None:
    bars = _bars([str(10 + i) for i in range(20)])
    split = TrainEvalSplit(train_end_exclusive=_ts(11))
    pipe = QlibInspiredResearchPipeline(lookback=3)
    output = pipe.run(bars, split, data_version="sep-1")
    assert output.training_period_end is not None
    assert output.evaluation_period_start is not None
    assert output.training_period_end < output.evaluation_period_start
    for pred in output.predictions:
        assert pred.prediction_timestamp >= split.train_end_exclusive


def test_deterministic_research_results_and_normalization() -> None:
    bars = _bars([str(10 + (i % 5)) for i in range(24)])
    split = TrainEvalSplit(train_end_exclusive=_ts(12))
    pipe = QlibInspiredResearchPipeline(lookback=4)
    a = pipe.run(bars, split)
    b = pipe.run(bars, split)
    assert a.to_serializable_dict() == b.to_serializable_dict()
    assert a.research_model_id == "qlib_inspired_momentum_v1"
    assert a.source_repository == QLIB_REPOSITORY_URL
    assert a.pinned_commit == QLIB_PINNED_COMMIT
    assert a.predictions
    assert a.warnings


# ---------------------------------------------------------------------------
# Strategy adapter / registry / backtest / broker isolation
# ---------------------------------------------------------------------------


def test_prediction_to_strategy_decision_and_no_action() -> None:
    adapter = QlibFactorSignalAdapter()
    ctx = StrategyContext(
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        timestamp=_ts(15),
        timeframe="1Day",
        bars=_bars(["10", "11", "12", "13", "14", "15"]),
        reference_price=Decimal("15"),
        position=StrategyPositionView(symbol="AAPL", quantity=Decimal("0")),
        parameters={
            "entry_threshold": "0.02",
            "exit_threshold": "-0.01",
            "quantity": "1",
            "research_score": "0.05",
        },
    )
    decision = adapter.evaluate(ctx)
    assert decision.action == DecisionAction.ENTER_LONG

    quiet = adapter.evaluate(
        ctx.model_copy(
            update={
                "parameters": {
                    "entry_threshold": "0.50",
                    "exit_threshold": "-0.01",
                    "quantity": "1",
                    "research_score": "0.01",
                }
            }
        )
    )
    assert quiet.action == DecisionAction.NO_ACTION

    proposal = StrategyProposalAdapter().to_proposal_input(
        decision,
        broker_account_id=uuid4(),
        strategy_id=adapter.strategy_id,
        strategy_version=adapter.version,
    )
    assert proposal.source == ProposalSource.STRATEGY


def test_strategy_registry_compatibility() -> None:
    gated = GatedStrategyRegistry()
    adapter = QlibFactorSignalAdapter()
    gated.register(adapter)
    assert gated.contains("qlib_factor_signal", "1.0.0")


def test_backtest_integration_and_reproducibility() -> None:
    # Down then up then down — research scores drive entries via bound output
    closes = [
        "50", "49", "48", "47", "46", "45", "44", "43", "42", "41",
        "42", "44", "47", "50", "54", "58", "62", "66", "70", "74",
        "70", "65", "60", "55", "50", "45", "40", "35", "30", "25",
    ]
    bars = _bars(closes)
    split = TrainEvalSplit(train_end_exclusive=_ts(12))
    research = QlibInspiredResearchPipeline(lookback=3).run(bars, split)
    assert research.predictions

    provider = InMemoryHistoricalMarketDataProvider()
    provider.load_bars("AAPL", "1Day", bars)

    def run_once():
        adapter = QlibFactorSignalAdapter()
        adapter.bind_research_output(research)
        return BacktestEngine(provider).run(
            adapter,
            symbols=["AAPL"],
            timeframe="1Day",
            starting_capital=Decimal("100000"),
            parameters={
                "entry_threshold": "0.01",
                "exit_threshold": "-0.005",
                "quantity": "1",
                "research_predictions": prediction_map_from_output(research),
            },
        )

    r1 = run_once()
    r2 = run_once()
    assert r1.to_serializable_dict() == r2.to_serializable_dict()
    assert r1.strategy_id == "qlib_factor_signal"
    assert r1.execution_assumptions["external_broker"] is False


def test_broker_isolation_no_qlib_or_execution_imports() -> None:
    root = Path(__file__).resolve().parents[1] / "app" / "research"
    forbidden_mods = ("brokers.execution", "alpaca.trading", "trading.routing")
    for path in root.rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for f in forbidden_mods:
                    assert f not in mod
                for alias in node.names:
                    assert alias.name not in {
                        "AlpacaPaperExecutionAdapter",
                        "BrokerExecutionAdapter",
                        "BrokerRouter",
                        "TradingClient",
                    }
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "qlib"
                    assert not alias.name.startswith("qlib.")
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert mod != "qlib" and not mod.startswith("qlib.")


def test_pyproject_does_not_add_pyqlib_dependency() -> None:
    text = Path(__file__).resolve().parents[1].joinpath("pyproject.toml").read_text()
    assert "pyqlib" not in text
    assert "microsoft/qlib" not in text
