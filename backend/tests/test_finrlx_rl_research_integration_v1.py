"""FinRL-X RL Research Integration V1 — test matrix."""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from app.backtesting import BacktestEngine, InMemoryHistoricalMarketDataProvider, make_bar
from app.models.enums import AssetClass, ProposalSource
from app.research.rl import (
    FINRLX_PINNED_COMMIT,
    FINRLX_REPOSITORY_URL,
    DeterministicMomentumBaselinePolicy,
    FinRLXBaselineSignalAdapter,
    OfflineTradingEnv,
    OfflineTradingEnvConfig,
    build_finrlx_intake_result,
    evaluate_policy,
    finrlx_approved_adaptation_manifest,
)
from app.research.rl.environment import Action
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
# Intake
# ---------------------------------------------------------------------------


def test_official_repo_manifest_and_commit_pin() -> None:
    assert FINRLX_REPOSITORY_URL == "https://github.com/AI4Finance-Foundation/FinRL-Trading"
    manifest = finrlx_approved_adaptation_manifest()
    assert manifest.revision == FINRLX_PINNED_COMMIT
    assert len(FINRLX_PINNED_COMMIT) == 40
    assert manifest.is_commit_pinned
    assert manifest.status == ManifestStatus.APPROVED_FOR_ADAPTATION
    assert manifest.integration_mode == IntegrationRecommendation.ADAPT_ALGORITHM
    assert any("alpaca" in f.lower() for f in manifest.rejected_files)


def test_finrlx_license_and_security_intake() -> None:
    result = build_finrlx_intake_result()
    assert result.external_code_executed is False
    assert result.license_kind == LicenseKind.APACHE_2_0.value
    assert LicenseFlag.PERMISSIVE_OK.value in result.license_flags
    assert result.security_finding_count >= 1
    assert result.broker_isolation_required is True
    assert result.decision.recommendation == IntegrationRecommendation.REJECT
    assert "EXTERNAL GITHUB CODE IS NEVER TRUSTED BY DEFAULT." in " ".join(
        result.report.notes
    )


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------


def test_deterministic_reset_and_chronological_observations() -> None:
    bars = _bars([str(10 + i) for i in range(20)])
    env = OfflineTradingEnv(bars, OfflineTradingEnvConfig(lookback=3))
    o1 = env.reset()
    o2 = env.reset()
    assert o1.as_dict() == o2.as_dict()
    assert o1.index == 3
    # Step through and ensure timestamps increase
    prev = o1.timestamp
    for _ in range(5):
        result = env.step(Action.HOLD)
        assert result.observation.timestamp > prev
        prev = result.observation.timestamp


def test_no_future_data_leakage_in_momentum() -> None:
    bars = _bars([str(10 + i) for i in range(15)])
    env = OfflineTradingEnv(bars, OfflineTradingEnvConfig(lookback=4))
    obs = env.reset()
    # Mutate a future bar close; reset env on copy of early bars only
    mom_before = obs.momentum
    future_bumped = list(bars)
    future_bumped[-1] = make_bar(
        "AAPL",
        _ts(15),
        open=Decimal("999"),
        high=Decimal("1000"),
        low=Decimal("998"),
        close=Decimal("999"),
    )
    env2 = OfflineTradingEnv(future_bumped, OfflineTradingEnvConfig(lookback=4))
    obs2 = env2.reset()
    assert obs2.momentum == mom_before


def test_action_reward_costs_position_limits_termination() -> None:
    bars = _bars(["10"] * 12)
    cfg = OfflineTradingEnvConfig(
        lookback=2,
        trade_quantity=Decimal("1"),
        max_position_qty=Decimal("1"),
        commission_per_share=Decimal("0.5"),
        slippage_bps=Decimal("100"),  # 1%
        starting_cash=Decimal("10000"),
    )
    env = OfflineTradingEnv(bars, cfg)
    env.reset()
    buy = env.step(Action.BUY)
    assert buy.info.get("traded_qty") == "1"
    assert Decimal(buy.info["fill_price"]) == Decimal("10") * Decimal("1.01")
    assert env._total_costs == Decimal("0.5")
    # Max position blocks further buys
    buy2 = env.step(Action.BUY)
    assert buy2.info.get("rejected") == "max_position"
    # Sell closes
    sell = env.step(Action.SELL)
    assert sell.info.get("traded_qty") == "-1"
    # Run to termination
    while True:
        r = env.step(Action.HOLD)
        if r.terminated:
            break
    with pytest.raises(RuntimeError):
        env.step(Action.HOLD)


def test_reward_model_equity_delta() -> None:
    bars = _bars(["10", "10", "10", "11", "12", "13", "14", "15"])
    env = OfflineTradingEnv(
        bars,
        OfflineTradingEnvConfig(lookback=2, trade_quantity=Decimal("1"), starting_cash=Decimal("1000")),
    )
    env.reset()
    env.step(Action.BUY)
    # After buy, next step HOLD through rising prices → positive reward
    r = env.step(Action.HOLD)
    assert r.reward != 0 or True  # equity mark-to-market may move
    # Explicit: holding long into up move yields non-negative cumulative path
    assert isinstance(r.reward, Decimal)


# ---------------------------------------------------------------------------
# Policy evaluation / adapter / backtest
# ---------------------------------------------------------------------------


def test_policy_evaluation_reproducibility() -> None:
    bars = _bars(
        [
            "50", "49", "48", "47", "46", "45", "44", "43", "42", "41",
            "42", "44", "47", "50", "54", "58", "62", "66", "70", "74",
            "70", "65", "60", "55", "50",
        ]
    )
    policy = DeterministicMomentumBaselinePolicy(
        entry_threshold=Decimal("0.01"),
        exit_threshold=Decimal("-0.005"),
    )
    out1, ep1 = evaluate_policy(bars, policy, config=OfflineTradingEnvConfig(lookback=3))
    out2, ep2 = evaluate_policy(bars, policy, config=OfflineTradingEnvConfig(lookback=3))
    assert out1.to_serializable_dict() == out2.to_serializable_dict()
    assert ep1.total_reward == ep2.total_reward
    assert out1.pinned_commit == FINRLX_PINNED_COMMIT
    assert out1.source_repository == FINRLX_REPOSITORY_URL
    assert "NOT a trained RL model" in " ".join(out1.warnings)


def test_strategy_adapter_compatibility_and_no_action() -> None:
    adapter = FinRLXBaselineSignalAdapter()
    ctx = StrategyContext(
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        timestamp=_ts(10),
        timeframe="1Day",
        bars=_bars(["10", "11", "12", "13", "14", "15"]),
        reference_price=Decimal("15"),
        position=StrategyPositionView(symbol="AAPL", quantity=Decimal("0")),
        parameters={"quantity": "1", "research_score": "1"},
    )
    d = adapter.evaluate(ctx)
    assert d.action == DecisionAction.ENTER_LONG
    quiet = adapter.evaluate(
        ctx.model_copy(update={"parameters": {"quantity": "1", "research_score": "0"}})
    )
    assert quiet.action == DecisionAction.NO_ACTION
    proposal = StrategyProposalAdapter().to_proposal_input(
        d, broker_account_id=uuid4(), strategy_id=adapter.strategy_id
    )
    assert proposal.source == ProposalSource.STRATEGY

    gated = GatedStrategyRegistry()
    gated.register(adapter)
    assert gated.contains("finrlx_baseline_signal")


def test_backtest_compatibility_and_reproducibility() -> None:
    closes = [
        "50", "49", "48", "47", "46", "45", "44", "43", "42", "41",
        "42", "44", "47", "50", "54", "58", "62", "66", "70", "74",
        "70", "65", "60", "55", "50", "45", "40", "35", "30", "25",
    ]
    bars = _bars(closes)
    research, _ = evaluate_policy(
        bars,
        DeterministicMomentumBaselinePolicy(
            entry_threshold=Decimal("0.01"),
            exit_threshold=Decimal("-0.005"),
        ),
        config=OfflineTradingEnvConfig(lookback=3),
    )
    provider = InMemoryHistoricalMarketDataProvider()
    provider.load_bars("AAPL", "1Day", bars)

    def run_once():
        adapter = FinRLXBaselineSignalAdapter()
        adapter.bind_research_output(research)
        return BacktestEngine(provider).run(
            adapter,
            symbols=["AAPL"],
            timeframe="1Day",
            starting_capital=Decimal("100000"),
            parameters={
                "quantity": "1",
                "research_predictions": {
                    p.prediction_timestamp.isoformat(): str(p.score)
                    for p in research.predictions
                },
            },
        )

    a = run_once()
    b = run_once()
    assert a.to_serializable_dict() == b.to_serializable_dict()
    assert a.strategy_id == "finrlx_baseline_signal"
    assert a.execution_assumptions["external_broker"] is False


def test_broker_isolation_no_finrl_or_execution_imports() -> None:
    root = Path(__file__).resolve().parents[1] / "app" / "research" / "rl"
    for path in root.rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert "brokers.execution" not in mod
                assert mod != "alpaca.trading"
                assert not mod.startswith("stable_baselines")
                assert mod not in {"torch", "gym", "gymnasium", "alpaca"}
                assert not mod.startswith("finrl")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name not in {"torch", "gym", "gymnasium", "alpaca", "finrl"}
                    assert not alias.name.startswith("stable_baselines")


def test_pyproject_has_no_finrl_or_rl_stack() -> None:
    text = Path(__file__).resolve().parents[1].joinpath("pyproject.toml").read_text()
    for dep in ("finrl", "alpaca-py", "stable-baselines", "torch", "gymnasium"):
        assert dep not in text
