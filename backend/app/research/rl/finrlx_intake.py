"""Pinned FinRL-X (FinRL-Trading) intake artifacts.

Official identity (verified via AI4Finance Foundation + arXiv:2603.21330):
  https://github.com/AI4Finance-Foundation/FinRL-Trading

Pinned commit: 4409abe925c904e570be78ebfb5e77ac3491dff8

Full FinRL-X runtime is NOT executed and NOT added as a production dependency.
"""

from __future__ import annotations

from pathlib import Path

from app.strategy_intake.manifest import RepositoryManifest, create_manifest
from app.strategy_intake.models import (
    ExternalRepositoryIntake,
    IntegrationRecommendation,
    ManifestStatus,
    RepoClassification,
    RiskLevel,
    SourceSnippet,
)
from app.strategy_intake.pipeline import IntakeReviewResult, review_repository_intake

FINRLX_REPOSITORY_URL = "https://github.com/AI4Finance-Foundation/FinRL-Trading"
FINRLX_PINNED_COMMIT = "4409abe925c904e570be78ebfb5e77ac3491dff8"
FINRLX_OWNER = "AI4Finance-Foundation"
FINRLX_NAME = "FinRL-Trading"

FINRLX_COMPONENT_DECISIONS: dict[str, str] = {
    "rl_environment_design": "ADAPT",
    "historical_market_observations": "ADAPT",
    "action_spaces": "ADAPT",
    "reward_calculations": "ADAPT",
    "transaction_cost_modeling": "ADAPT",
    "position_portfolio_constraints": "ADAPT",
    "offline_policy_evaluation": "ADAPT",
    "drl_training_stack_torch_sb3": "REFERENCE_ONLY",  # deferred — heavy deps
    "finrlx_backtest_engine": "REJECT",
    "alpaca_broker_execution": "REJECT",
    "deploy_scripts_live_trading": "REJECT",
    "credential_env_templates": "REJECT",
}


def _load_static_snippets() -> list[SourceSnippet]:
    root = Path("/tmp/finrlx_intake_snippets")
    snippets: list[SourceSnippet] = []
    if root.is_dir():
        for path in sorted(root.glob("*")):
            if path.is_file():
                snippets.append(
                    SourceSnippet(
                        path=path.name,
                        content=path.read_text(encoding="utf-8", errors="replace")[:80000],
                    )
                )
        if snippets:
            return snippets
    # Embedded evidence from reviewed tip (not executed)
    return [
        SourceSnippet(
            path="src/trading/alpaca_manager.py",
            content=(
                "def place_order(self, order: OrderRequest):\n"
                "    ...\n"
                "APCA_API_KEY / APCA_API_SECRET\n"
                "base_url: str = 'https://paper-api.alpaca.markets'\n"
            ),
        ),
        SourceSnippet(
            path="src/strategies/rl_model.py",
            content=(
                "import torch\n"
                "import gymnasium as gym\n"
                "from stable_baselines3.common.vec_env import DummyVecEnv\n"
            ),
        ),
        SourceSnippet(
            path="requirements.txt",
            content="alpaca-py>=0.13.0\ntorch>=2.0.0\nrequests>=2.31.0\n",
        ),
        SourceSnippet(
            path="deploy.sh",
            content="Set APCA_API_KEY and APCA_API_SECRET to your actual keys\n",
        ),
    ]


def build_finrlx_intake_metadata() -> ExternalRepositoryIntake:
    return ExternalRepositoryIntake(
        repository_url=FINRLX_REPOSITORY_URL,
        repository_name=FINRLX_NAME,
        owner=FINRLX_OWNER,
        license="Apache-2.0",
        language="Python",
        dependency_files=["requirements.txt", "setup.py"],
        strategy_files=[
            "src/strategies/rl_model.py",
            "src/strategies/fundamental_portfolio_drl.py",
        ],
        backtesting_framework="FinRL-X / bt",
        broker_integrations=["alpaca-py", "AlpacaManager.place_order"],
        market_data_integrations=["yfinance", "finnhub", "alpaca data"],
        ai_ml_components=["torch", "gymnasium/gym", "stable-baselines3", "lightgbm", "xgboost"],
        network_access=True,
        filesystem_access=True,
        shell_subprocess_usage=True,
        dynamic_code_execution=False,
        security_warnings=[
            "Direct Alpaca place_order / batch order paths",
            "APCA_* credential environment templates",
            "deploy.sh provisions broker credentials",
            "Heavy optional DRL stack (torch/gym/SB3)",
            "Must not install into trading execution service",
        ],
        notes=[
            f"Pinned commit: {FINRLX_PINNED_COMMIT}",
            "Described as FinRL-X in README/arXiv; repo name FinRL-Trading.",
            "Full runtime REJECT; RL env concepts ADAPT.",
        ],
        metadata={
            "pinned_commit": FINRLX_PINNED_COMMIT,
            "aka": "FinRL-X",
            "component_decisions": FINRLX_COMPONENT_DECISIONS,
            "arxiv": "2603.21330",
            "small_algorithm": True,
        },
    )


def build_finrlx_intake_result() -> IntakeReviewResult:
    return review_repository_intake(
        build_finrlx_intake_metadata(),
        source_snippets=_load_static_snippets(),
        purpose=(
            "FinRL-X: AI-native modular quant trading infrastructure with "
            "RL allocators and broker-connected execution (research reference)"
        ),
        maintenance_status="active (AI4Finance-Foundation/FinRL-Trading)",
    )


def finrlx_approved_adaptation_manifest() -> RepositoryManifest:
    """Approve algorithm adaptation only — not FinRL-X runtime install."""
    return create_manifest(
        repository=FINRLX_REPOSITORY_URL,
        revision=FINRLX_PINNED_COMMIT,
        license="Apache-2.0",
        classification=[
            RepoClassification.ML_AI_RESEARCH,
            RepoClassification.STRATEGY_ALGORITHM,
            RepoClassification.EXECUTION_BROKER_TOOL,
            RepoClassification.FULL_TRADING_BOT,
            RepoClassification.BACKTESTING_LIBRARY,
        ],
        integration_mode=IntegrationRecommendation.ADAPT_ALGORITHM,
        approved_files=[
            "docs/ / conceptual RL env, reward, action ideas (adapted)",
            "src/strategies/rl_model.py (environment concepts — reimplemented)",
        ],
        rejected_files=[
            "src/trading/alpaca_manager.py",
            "src/trading/trade_executor.py",
            "src/strategies/execution_engine.py",
            "deploy.sh",
            ".env.example credential templates",
            "alpaca-py / torch / stable-baselines3 production dependency",
        ],
        dependencies=[],
        security_findings=[],
        adapter_name="FinRLXBaselineSignalAdapter",
        status=ManifestStatus.APPROVED_FOR_ADAPTATION,
        risk_level=RiskLevel.HIGH,
        notes=[
            "APPROVED FOR RL ENVIRONMENT CONCEPT ADAPTATION ONLY.",
            "Full-repo intake rejects runtime install/execution; see build_finrlx_intake_result().",
            "Do not install FinRL-X, alpaca-py, torch, or SB3 into the trading service.",
            "Do not reuse FinRL-X broker order paths.",
            "Apache-2.0 notice required for adapted concepts.",
            f"Pinned: {FINRLX_PINNED_COMMIT}",
            "EXTERNAL GITHUB CODE IS NEVER TRUSTED BY DEFAULT.",
            "RL training deferred — no training workers in V1.",
        ],
    )
