"""Freqtrade intake — GPL-3.0 reference only (no source adaptation).

Official repository: https://github.com/freqtrade/freqtrade
Pinned commit: fccc94d9bb7a85023e946bf75774bd903888fc45

COMPLIANT APPROACH:
  Independent implementation of public-domain indicator formulas and
  strategy rules. Do NOT copy, translate, or closely port GPL-covered
  Freqtrade implementation code into this proprietary codebase.
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

FREQTRADE_REPOSITORY_URL = "https://github.com/freqtrade/freqtrade"
FREQTRADE_PINNED_COMMIT = "fccc94d9bb7a85023e946bf75774bd903888fc45"

FREQTRADE_COMPONENT_DECISIONS: dict[str, str] = {
    "rsi_strategy_concepts": "INDEPENDENT_IMPLEMENTATION",
    "macd_strategy_concepts": "INDEPENDENT_IMPLEMENTATION",
    "ma_crossover_concepts": "INDEPENDENT_IMPLEMENTATION",
    "bollinger_concepts": "INDEPENDENT_IMPLEMENTATION",
    "momentum_trend_concepts": "INDEPENDENT_IMPLEMENTATION",
    "multi_indicator_confirmation": "INDEPENDENT_IMPLEMENTATION",
    "stop_loss_take_profit_concepts": "INDEPENDENT_IMPLEMENTATION",
    "strategy_parameter_config_concepts": "REFERENCE_ONLY",
    "hyperopt_optimization_concepts": "REFERENCE_ONLY",
    "freqtrade_bot_runtime": "REJECT",
    "ccxt_exchange_adapters": "REJECT",
    "freqtrade_backtesting_engine": "REJECT",
    "gpl_source_adaptation": "REJECT",
}


def _load_static_snippets() -> list[SourceSnippet]:
    root = Path("/tmp/freqtrade_intake_snippets")
    snippets: list[SourceSnippet] = []
    if root.is_dir():
        for path in sorted(root.glob("*")):
            if path.is_file() and path.stat().st_size < 200_000:
                # Cap large exchange.py for scanner
                content = path.read_text(encoding="utf-8", errors="replace")
                snippets.append(SourceSnippet(path=path.name, content=content[:100000]))
        if snippets:
            return snippets
    return [
        SourceSnippet(
            path="requirements.txt",
            content="ccxt==4.5.85\n",
        ),
        SourceSnippet(
            path="freqtrade/exchange/exchange.py",
            content=(
                "import ccxt\n"
                "self._api = self._init_ccxt(...)\n"
                "create_order / exchange credentials\n"
            ),
        ),
        SourceSnippet(
            path="LICENSE",
            content="GNU GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007\n",
        ),
    ]


def build_freqtrade_intake_metadata() -> ExternalRepositoryIntake:
    return ExternalRepositoryIntake(
        repository_url=FREQTRADE_REPOSITORY_URL,
        repository_name="freqtrade",
        owner="freqtrade",
        license="GPL-3.0",
        language="Python",
        dependency_files=["requirements.txt"],
        strategy_files=["freqtrade/strategy/"],
        backtesting_framework="freqtrade backtesting",
        broker_integrations=["ccxt exchanges"],
        market_data_integrations=["ccxt OHLCV"],
        ai_ml_components=["hyperopt (optional)"],
        network_access=True,
        filesystem_access=True,
        shell_subprocess_usage=None,
        dynamic_code_execution=True,  # user strategies loaded dynamically
        security_warnings=[
            "GPL-3.0 copyleft — do not adapt source into proprietary codebase",
            "ccxt exchange order submission surfaces",
            "Dynamic loading of third-party strategy modules",
            "Full trading bot runtime unsuitable for our execution service",
        ],
        notes=[
            f"Pinned commit: {FREQTRADE_PINNED_COMMIT}",
            "Compliant path: independent public-domain indicator/strategy implementations only.",
        ],
        metadata={
            "pinned_commit": FREQTRADE_PINNED_COMMIT,
            "component_decisions": FREQTRADE_COMPONENT_DECISIONS,
            "reference_only": True,
        },
    )


def build_freqtrade_intake_result() -> IntakeReviewResult:
    return review_repository_intake(
        build_freqtrade_intake_metadata(),
        source_snippets=_load_static_snippets(),
        purpose="Open-source crypto trading bot (strategy/TA concepts reference)",
        maintenance_status="active (freqtrade/freqtrade develop)",
    )


def freqtrade_reference_manifest() -> RepositoryManifest:
    """Manifest: REFERENCE ONLY — GPL blocks source adaptation."""
    return create_manifest(
        repository=FREQTRADE_REPOSITORY_URL,
        revision=FREQTRADE_PINNED_COMMIT,
        license="GPL-3.0",
        classification=[
            RepoClassification.STRATEGY_ALGORITHM,
            RepoClassification.FULL_TRADING_BOT,
            RepoClassification.EXECUTION_BROKER_TOOL,
            RepoClassification.BACKTESTING_LIBRARY,
            RepoClassification.REFERENCE_ONLY,
        ],
        integration_mode=IntegrationRecommendation.REFERENCE_ONLY,
        approved_files=[],  # no GPL files approved for copying
        rejected_files=[
            "freqtrade/** source adaptation",
            "ccxt exchange adapters",
            "freqtrade backtesting engine",
            "hyperopt engine copy",
            "full freqtrade bot runtime",
        ],
        dependencies=[],
        security_findings=[],
        adapter_name=None,
        status=ManifestStatus.REVIEWING,  # not approved_for_adaptation of GPL code
        risk_level=RiskLevel.CRITICAL,
        notes=[
            "GPL-3.0: COPYLEFT_REVIEW_REQUIRED — source adaptation REJECTED.",
            "Independent indicator/strategy implementations are first-party code.",
            "Do not install or run the Freqtrade trading bot in our runtime.",
            f"Pinned: {FREQTRADE_PINNED_COMMIT}",
            "EXTERNAL GITHUB CODE IS NEVER TRUSTED BY DEFAULT.",
        ],
    )
