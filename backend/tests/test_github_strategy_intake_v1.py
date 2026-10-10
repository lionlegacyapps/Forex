"""GitHub Strategy Intake & Adapter Framework V1 — test matrix."""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from app.models.enums import AssetClass, ProposalSource
from app.strategies import SMACrossoverStrategy, StrategyProposalAdapter, StrategyRegistry
from app.strategies.context import StrategyContext, StrategyPositionView
from app.strategies.decision import DecisionAction
from app.strategy_intake import (
    FORBIDDEN_ADAPTER_DEPENDENCIES,
    AdapterGateError,
    ExternalRepositoryIntake,
    ExternalStrategyAdapter,
    GatedStrategyRegistry,
    IntegrationRecommendation,
    LicenseFlag,
    LicenseKind,
    ManifestError,
    ManifestStatus,
    RepoClassification,
    RepositoryManifest,
    SandboxBoundarySpec,
    SourceSnippet,
    ThresholdMomentumAdapter,
    classify_license,
    classify_repository,
    create_manifest,
    review_license,
    review_repository_intake,
    review_sources,
    run_adapter_harness,
)
from app.backtesting import make_bar


def _ctx(**kwargs) -> StrategyContext:
    bars = kwargs.pop("bars", None)
    if bars is None:
        bars = [
            make_bar(
                "AAPL",
                datetime(2024, 1, i + 1, 16, 0, tzinfo=UTC),
                Decimal(10 + i),
                Decimal(11 + i),
                Decimal(9 + i),
                Decimal(10 + i),
            )
            for i in range(6)
        ]
    return StrategyContext(
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        timestamp=bars[-1].timestamp,
        timeframe="1Day",
        bars=bars,
        reference_price=bars[-1].close,
        position=kwargs.pop("position", StrategyPositionView(symbol="AAPL", quantity=Decimal("0"))),
        parameters=kwargs.pop("parameters", {}),
        **kwargs,
    )


def _approved_manifest(**overrides) -> RepositoryManifest:
    data = dict(
        repository="https://github.com/example/algo-ref",
        revision="abcdef0123456789abcdef0123456789abcdef01",
        license="MIT",
        classification=[RepoClassification.STRATEGY_ALGORITHM],
        integration_mode=IntegrationRecommendation.ADAPT_ALGORITHM,
        status=ManifestStatus.APPROVED_FOR_ADAPTATION,
        adapter_name="ThresholdMomentumAdapter",
    )
    data.update(overrides)
    return create_manifest(**data)


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def test_repo_classification() -> None:
    intake = ExternalRepositoryIntake(
        repository_url="https://github.com/example/strat",
        strategy_files=["strategy.py"],
        language="python",
    )
    result = classify_repository(intake)
    assert RepoClassification.STRATEGY_ALGORITHM in result.classifications


def test_multi_category_classification() -> None:
    intake = ExternalRepositoryIntake(
        repository_url="https://github.com/example/bot",
        strategy_files=["strat.py"],
        backtesting_framework="custom",
        broker_integrations=["alpaca"],
        market_data_integrations=["polygon"],
        ai_ml_components=["lstm"],
        metadata={"indicator_library": True},
    )
    result = classify_repository(intake)
    assert RepoClassification.STRATEGY_ALGORITHM in result.classifications
    assert RepoClassification.BACKTESTING_LIBRARY in result.classifications
    assert RepoClassification.EXECUTION_BROKER_TOOL in result.classifications
    assert RepoClassification.MARKET_DATA_TOOL in result.classifications
    assert RepoClassification.ML_AI_RESEARCH in result.classifications
    assert RepoClassification.FULL_TRADING_BOT in result.classifications
    assert RepoClassification.INDICATOR_LIBRARY in result.classifications


# ---------------------------------------------------------------------------
# License
# ---------------------------------------------------------------------------


def test_mit_license_recognized() -> None:
    result = review_license("MIT")
    assert result.license_kind == LicenseKind.MIT
    assert LicenseFlag.PERMISSIVE_OK in result.flags
    assert result.adaptation_allowed is True
    assert classify_license("MIT License") == LicenseKind.MIT


def test_gpl_flagged_for_review() -> None:
    result = review_license("GPL-3.0")
    assert result.license_kind == LicenseKind.GPL
    assert LicenseFlag.COPYLEFT_REVIEW_REQUIRED in result.flags
    assert result.adaptation_allowed is False


def test_agpl_flagged_for_review() -> None:
    result = review_license("AGPL-3.0")
    assert result.license_kind == LicenseKind.AGPL
    assert LicenseFlag.AGPL_REVIEW_REQUIRED in result.flags
    assert LicenseFlag.COPYLEFT_REVIEW_REQUIRED in result.flags
    assert result.adaptation_allowed is False


def test_no_license_rejected_flagged() -> None:
    result = review_license(None)
    assert result.license_kind == LicenseKind.NO_LICENSE
    assert LicenseFlag.NO_LICENSE in result.flags
    assert result.adaptation_allowed is False
    review = review_repository_intake(
        ExternalRepositoryIntake(
            repository_url="https://github.com/example/nolics",
            license=None,
            strategy_files=["a.py"],
        )
    )
    assert review.draft_manifest.status == ManifestStatus.REJECTED


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------


def test_unsafe_subprocess_detected() -> None:
    r = review_sources([SourceSnippet(path="a.py", content="import subprocess\nsubprocess.run('ls', shell=True)\n")])
    assert any(f.rule_id == "subprocess_usage" for f in r.findings)
    assert r.dynamic_execution_detected is True
    assert r.passed_static_gates is False


def test_eval_detected() -> None:
    r = review_sources([SourceSnippet(path="a.py", content="x = eval(user_input)\n")])
    assert any(f.rule_id == "eval_usage" for f in r.findings)


def test_exec_detected() -> None:
    r = review_sources([SourceSnippet(path="a.py", content="exec(code)\n")])
    assert any(f.rule_id == "exec_usage" for f in r.findings)


def test_broker_submission_detected() -> None:
    r = review_sources(
        [SourceSnippet(path="broker.py", content="client.submit_order(symbol='AAPL', qty=1)\n")]
    )
    assert r.broker_order_submission_detected is True
    assert any(f.rule_id == "broker_order_submission" for f in r.findings)
    assert r.requires_isolation is True


def test_network_access_detected() -> None:
    r = review_sources(
        [SourceSnippet(path="net.py", content="import requests\nrequests.get('https://evil.example')\n")]
    )
    assert r.network_access_detected is True


# ---------------------------------------------------------------------------
# Manifest / pinning
# ---------------------------------------------------------------------------


def test_manifest_creation() -> None:
    m = create_manifest(
        repository="https://github.com/example/x",
        revision="1234567890abcdef1234567890abcdef12345678",
        license="MIT",
        classification=[RepoClassification.STRATEGY_ALGORITHM],
        status=ManifestStatus.CANDIDATE,
    )
    assert m.repository.endswith("/x")
    assert m.is_commit_pinned
    payload = m.to_serializable_dict()
    assert payload["status"] == "candidate"


def test_commit_pin_required() -> None:
    m = create_manifest(
        repository="https://github.com/example/x",
        revision=None,
        status=ManifestStatus.APPROVED_FOR_ADAPTATION,
        integration_mode=IntegrationRecommendation.ADAPT_ALGORITHM,
    )
    with pytest.raises(ManifestError) as exc:
        m.require_commit_pin()
    assert exc.value.code == "commit_pin_required"

    with pytest.raises(ValueError):
        create_manifest(
            repository="https://github.com/example/x",
            revision="main",
        )


# ---------------------------------------------------------------------------
# Gates / adapter
# ---------------------------------------------------------------------------


def test_untrusted_repo_cannot_register_as_strategy_directly() -> None:
    gated = GatedStrategyRegistry()
    with pytest.raises(AdapterGateError) as exc:
        gated.register_candidate("https://github.com/evil/bot")
    assert exc.value.code == "untrusted_repo_registration"

    with pytest.raises(AdapterGateError):
        gated.register_candidate(
            ExternalRepositoryIntake(repository_url="https://github.com/evil/bot")
        )

    with pytest.raises(AdapterGateError):
        gated.register_candidate(
            create_manifest(repository="https://github.com/evil/bot", revision="a" * 40)
        )


def test_rejected_repo_cannot_become_active_strategy() -> None:
    gated = GatedStrategyRegistry()
    manifest = _approved_manifest(status=ManifestStatus.REJECTED)
    adapter = ThresholdMomentumAdapter(manifest)
    with pytest.raises(AdapterGateError):
        gated.register(adapter)


def test_external_strategy_adapter_contains_no_broker_execution_dependency() -> None:
    root = Path(__file__).resolve().parents[1] / "app" / "strategy_intake"
    for path in root.rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert "brokers.execution" not in mod
                assert mod != "alpaca.trading"
                assert "trading.routing" not in mod
                for alias in node.names:
                    assert alias.name not in {
                        "AlpacaPaperExecutionAdapter",
                        "BrokerExecutionAdapter",
                        "BrokerRouter",
                        "TradingClient",
                    }
        # FORBIDDEN set is documentation in adapter.py — ensure listed
        if path.name == "adapter.py":
            for name in FORBIDDEN_ADAPTER_DEPENDENCIES:
                assert name in src


def test_approved_adapter_converts_algorithm_result_to_strategy_decision() -> None:
    adapter = ThresholdMomentumAdapter(_approved_manifest())
    # Build closes that exceed mean by threshold
    closes = [Decimal("10"), Decimal("10"), Decimal("10"), Decimal("10"), Decimal("20")]
    bars = [
        make_bar(
            "AAPL",
            datetime(2024, 1, i + 1, 16, 0, tzinfo=UTC),
            c,
            c + 1,
            c - 1,
            c,
        )
        for i, c in enumerate(closes)
    ]
    decision = adapter.evaluate(
        _ctx(
            bars=bars,
            parameters={"lookback": 3, "threshold": "0.05", "quantity": "2"},
        )
    )
    assert decision.action == DecisionAction.ENTER_LONG
    assert decision.quantity == Decimal("2")
    assert decision.symbol == "AAPL"

    # Gate allows registration when approved + pinned
    gated = GatedStrategyRegistry()
    gated.register(adapter)
    assert gated.contains("threshold_momentum_adapted")

    # Proposal compatibility
    proposal = StrategyProposalAdapter().to_proposal_input(
        decision,
        broker_account_id=uuid4(),
        strategy_id=adapter.strategy_id,
        strategy_version=adapter.version,
    )
    assert proposal.source == ProposalSource.STRATEGY


def test_adapter_harness_passes_for_example_adapter() -> None:
    adapter = ThresholdMomentumAdapter(_approved_manifest())
    result = run_adapter_harness(
        adapter,
        parameters={"lookback": 3, "threshold": "0.01", "quantity": "1"},
        expect_entry=True,
    )
    assert result.passed, result.failures
    assert result.checks["no_broker_imports"]
    assert result.checks["decision_to_trade_proposal"]
    assert result.checks["backtest_compatibility"]
    assert result.checks["reproducibility"]


def test_first_party_strategy_still_registers() -> None:
    gated = GatedStrategyRegistry(StrategyRegistry())
    gated.register(SMACrossoverStrategy())
    assert gated.contains("sma_crossover")


def test_intake_pipeline_does_not_execute_external_code() -> None:
    intake = ExternalRepositoryIntake(
        repository_url="https://github.com/example/full-bot",
        license="MIT",
        strategy_files=["strategy.py"],
        backtesting_framework="backtrader",
        broker_integrations=["alpaca"],
        dependency_files=["requirements.txt"],
    )
    snippets = [
        SourceSnippet(
            path="broker.py",
            content="def go():\n    api.submit_order(symbol='AAPL')\n",
        )
    ]
    result = review_repository_intake(
        intake,
        source_snippets=snippets,
        purpose="example full bot",
        maintenance_status="unknown",
    )
    assert result.external_code_executed is False
    assert result.broker_isolation_required is True
    assert result.decision.recommendation in {
        IntegrationRecommendation.ADAPT_ALGORITHM,
        IntegrationRecommendation.REJECT,
    }
    assert result.report.repository.endswith("full-bot")
    assert "EXTERNAL GITHUB CODE IS NEVER TRUSTED BY DEFAULT." in " ".join(
        result.report.notes
    )


def test_sandbox_v1_defaults() -> None:
    spec = SandboxBoundarySpec()
    spec.assert_v1_safe_defaults()
    assert spec.v1_auto_execute_external_code is False


def test_external_adapter_is_strategy_subclass() -> None:
    from app.strategies.protocol import Strategy

    assert issubclass(ExternalStrategyAdapter, Strategy)
    assert issubclass(ThresholdMomentumAdapter, ExternalStrategyAdapter)
