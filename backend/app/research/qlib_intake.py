"""Pinned Microsoft Qlib intake artifacts.

Pinned commit reviewed: 54355232463878d2eebb91fe0ee5fa7fa1f5976c
(includes upstream security fix for config-driven code execution).

Full pyqlib is NOT executed and NOT added as a production dependency.
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

QLIB_REPOSITORY_URL = "https://github.com/microsoft/qlib"
QLIB_PINNED_COMMIT = "54355232463878d2eebb91fe0ee5fa7fa1f5976c"
QLIB_OWNER = "microsoft"
QLIB_NAME = "qlib"

# Component-level decisions (operator guidance; full-repo static scan is separate)
QLIB_COMPONENT_DECISIONS: dict[str, str] = {
    "quantitative_factor_engineering": "ADAPT",
    "technical_indicator_factor_expressions": "ADAPT",
    "feature_preprocessing": "ADAPT",
    "dataset_preparation": "WRAP",  # wrap onto our HistoricalMarketDataProvider
    "predictive_ml_models": "REFERENCE_ONLY",  # defer heavy ML deps (lightgbm/torch)
    "model_evaluation": "REFERENCE_ONLY",
    "research_experiment_tracking": "REFERENCE_ONLY",  # mlflow/redis not wanted in runtime
    "qlib_backtest_engine": "REJECT",
    "qlib_strategy_execution": "REJECT",
    "qlib_broker_order_paths": "REJECT",
    "data_download_scripts": "REJECT",
    "rl_modules": "REJECT",
}


def _load_static_snippets() -> list[SourceSnippet]:
    """Load optional local static snippets if present (never executed)."""
    root = Path("/tmp/qlib_intake_snippets")
    snippets: list[SourceSnippet] = []
    if not root.is_dir():
        # Minimal embedded evidence from reviewed tip (not full sources)
        snippets.extend(
            [
                SourceSnippet(
                    path="qlib/workflow/recorder.py",
                    content=(
                        "import subprocess\n"
                        "out = subprocess.check_output(cmd, shell=True)\n"
                        "loader = pickle.Unpickler(f)\n"
                    ),
                ),
                SourceSnippet(
                    path="qlib/utils/__init__.py",
                    content="res = requests.get(url, timeout=1, **kwargs)\n",
                ),
                SourceSnippet(
                    path="scripts/get_data.py",
                    content="# data download entrypoint\nimport fire\n",
                ),
            ]
        )
        return snippets
    for path in sorted(root.glob("*")):
        if path.is_file():
            snippets.append(
                SourceSnippet(path=path.name, content=path.read_text(encoding="utf-8", errors="replace"))
            )
    return snippets


def build_qlib_intake_metadata() -> ExternalRepositoryIntake:
    return ExternalRepositoryIntake(
        repository_url=QLIB_REPOSITORY_URL,
        repository_name=QLIB_NAME,
        owner=QLIB_OWNER,
        license="MIT",
        language="Python",
        dependency_files=["pyproject.toml", "setup.py", "package.json"],
        strategy_files=[
            "qlib/contrib/strategy/",
            "qlib/strategy/",
        ],
        backtesting_framework="qlib.backtest",
        broker_integrations=[],  # research platform; execution via its own backtest stack
        market_data_integrations=["yahooquery", "baostock", "custom providers"],
        ai_ml_components=["lightgbm", "torch(optional)", "gym/rl"],
        network_access=True,
        filesystem_access=True,
        shell_subprocess_usage=True,
        dynamic_code_execution=True,
        security_warnings=[
            "subprocess shell=True in workflow recorder",
            "pickle.Unpickler artifact loading",
            "HTTP requests in utils",
            "heavy optional ML/RL dependency surface",
            "data download scripts must not run in trading runtime",
        ],
        notes=[
            f"Pinned commit: {QLIB_PINNED_COMMIT}",
            "Full runtime REJECT for trading service; factor concepts ADAPT.",
        ],
        metadata={
            "pinned_commit": QLIB_PINNED_COMMIT,
            "component_decisions": QLIB_COMPONENT_DECISIONS,
            "indicator_library": True,
            "small_algorithm": True,
        },
    )


def build_qlib_intake_result() -> IntakeReviewResult:
    """Run intake pipeline on metadata + static snippets (no code execution)."""
    return review_repository_intake(
        build_qlib_intake_metadata(),
        source_snippets=_load_static_snippets(),
        purpose=(
            "AI-oriented quant research platform for factor engineering, "
            "ML modeling, and research workflows"
        ),
        maintenance_status="active (microsoft/qlib main, frequently updated)",
    )


def qlib_approved_adaptation_manifest() -> RepositoryManifest:
    """Manifest authorizing algorithm extraction only (not full package install).

    Full-repo static intake REJECTs installing/executing pyqlib (subprocess,
    pickle, network). Operator approval here is narrowly scoped to adapting
    factor-research concepts into our typed research package — commit-pinned.
    """
    return create_manifest(
        repository=QLIB_REPOSITORY_URL,
        revision=QLIB_PINNED_COMMIT,
        version_tag=None,
        license="MIT",
        classification=[
            RepoClassification.STRATEGY_ALGORITHM,
            RepoClassification.INDICATOR_LIBRARY,
            RepoClassification.ML_AI_RESEARCH,
            RepoClassification.BACKTESTING_LIBRARY,
            RepoClassification.FULL_TRADING_BOT,
        ],
        integration_mode=IntegrationRecommendation.ADAPT_ALGORITHM,
        approved_files=[
            # Conceptual surfaces only — we reimplement deterministically
            "docs/ (factor/research concepts)",
            "qlib/data/ (factor expression ideas — adapted, not imported)",
        ],
        rejected_files=[
            "qlib/backtest/**",
            "qlib/contrib/strategy/** (execution)",
            "qlib/rl/**",
            "scripts/get_data.py",
            "qlib/workflow/** (mlflow/pickle/subprocess)",
            "full pyqlib production dependency",
        ],
        dependencies=[],  # none added to trading runtime
        security_findings=[],
        adapter_name="QlibFactorSignalAdapter",
        status=ManifestStatus.APPROVED_FOR_ADAPTATION,
        risk_level=RiskLevel.HIGH,
        notes=[
            "APPROVED FOR ALGORITHM ADAPTATION ONLY.",
            "Full-repo intake rejects runtime install/execution; see build_qlib_intake_result().",
            "Do not install pyqlib into the trading/execution service.",
            "Do not reuse Qlib backtest or order paths.",
            "MIT notice required for adapted concepts.",
            f"Pinned: {QLIB_PINNED_COMMIT}",
            "EXTERNAL GITHUB CODE IS NEVER TRUSTED BY DEFAULT.",
        ],
    )
