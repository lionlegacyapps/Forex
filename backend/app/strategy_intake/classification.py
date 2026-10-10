"""Repository architecture classification and integration decisions."""

from __future__ import annotations

from app.strategy_intake.models import (
    ClassificationResult,
    ExternalRepositoryIntake,
    IntegrationDecision,
    IntegrationRecommendation,
    LicenseReviewResult,
    RepoClassification,
    RiskLevel,
    SecurityReviewResult,
)


def classify_repository(intake: ExternalRepositoryIntake) -> ClassificationResult:
    classes: list[RepoClassification] = []
    reasons: list[str] = []

    if intake.strategy_files:
        classes.append(RepoClassification.STRATEGY_ALGORITHM)
        reasons.append("strategy_files present")
    if intake.backtesting_framework:
        classes.append(RepoClassification.BACKTESTING_LIBRARY)
        reasons.append(f"backtesting_framework={intake.backtesting_framework}")
    if intake.broker_integrations:
        classes.append(RepoClassification.EXECUTION_BROKER_TOOL)
        reasons.append("broker_integrations present")
    if intake.market_data_integrations:
        classes.append(RepoClassification.MARKET_DATA_TOOL)
        reasons.append("market_data_integrations present")
    if intake.ai_ml_components:
        classes.append(RepoClassification.ML_AI_RESEARCH)
        reasons.append("ai_ml_components present")

    # Heuristic: broker + strategy + backtest ≈ full bot
    if (
        RepoClassification.STRATEGY_ALGORITHM in classes
        and RepoClassification.EXECUTION_BROKER_TOOL in classes
        and RepoClassification.BACKTESTING_LIBRARY in classes
    ):
        classes.append(RepoClassification.FULL_TRADING_BOT)
        reasons.append("strategy + broker + backtest triad")

    meta = intake.metadata or {}
    for key, classification in (
        ("indicator_library", RepoClassification.INDICATOR_LIBRARY),
        ("portfolio_risk_library", RepoClassification.PORTFOLIO_RISK_LIBRARY),
        ("reference_only", RepoClassification.REFERENCE_ONLY),
    ):
        if meta.get(key):
            classes.append(classification)
            reasons.append(f"metadata.{key}=true")

    if not classes:
        classes.append(RepoClassification.UNKNOWN)
        reasons.append("insufficient signals")

    return ClassificationResult(classifications=classes, reasons=reasons)


def decide_integration(
    intake: ExternalRepositoryIntake,
    *,
    classification: ClassificationResult,
    license_review: LicenseReviewResult,
    security: SecurityReviewResult,
) -> IntegrationDecision:
    reasons: list[str] = []
    risk = RiskLevel.MEDIUM
    broker_isolation = True

    if not license_review.adaptation_allowed:
        reasons.append("license incompatible or unclear — do not copy code")
        return IntegrationDecision(
            recommendation=IntegrationRecommendation.REJECT,
            reasons=reasons + license_review.notes,
            risk_level=RiskLevel.CRITICAL,
            broker_isolation_required=True,
            preferred_method="none",
        )

    if security.broker_order_submission_detected:
        reasons.append("unsafe broker coupling — extract algorithm only; never reuse execution path")
        risk = RiskLevel.CRITICAL
        broker_isolation = True

    if security.dynamic_execution_detected:
        reasons.append("dynamic/shell execution patterns present")
        risk = RiskLevel.CRITICAL

    if not security.passed_static_gates:
        reasons.append("critical security findings — reject until remediated via adaptation")
        return IntegrationDecision(
            recommendation=IntegrationRecommendation.REJECT,
            reasons=reasons,
            risk_level=RiskLevel.CRITICAL,
            broker_isolation_required=True,
            preferred_method="none",
        )

    classes = set(classification.classifications)

    if RepoClassification.FULL_TRADING_BOT in classes:
        reasons.append("full trading bot — extract useful algorithm only")
        return IntegrationDecision(
            recommendation=IntegrationRecommendation.ADAPT_ALGORITHM,
            reasons=reasons,
            risk_level=risk,
            broker_isolation_required=True,
            preferred_method="algorithm_extraction_to_StrategyAdapter",
        )

    if RepoClassification.EXECUTION_BROKER_TOOL in classes and (
        RepoClassification.STRATEGY_ALGORITHM not in classes
    ):
        reasons.append("execution/broker tool duplicates or conflicts with our BrokerRouter")
        return IntegrationDecision(
            recommendation=IntegrationRecommendation.REJECT,
            reasons=reasons + ["duplicate capability / architecture mismatch"],
            risk_level=RiskLevel.HIGH,
            broker_isolation_required=True,
            preferred_method="none",
        )

    if RepoClassification.BACKTESTING_LIBRARY in classes and (
        RepoClassification.STRATEGY_ALGORITHM not in classes
    ):
        reasons.append("backtesting library — prefer our BacktestEngine unless clear benefit")
        return IntegrationDecision(
            recommendation=IntegrationRecommendation.REFERENCE_ONLY,
            reasons=reasons + ["avoid duplicate backtesting frameworks"],
            risk_level=RiskLevel.MEDIUM,
            broker_isolation_required=True,
            preferred_method="reference_docs_only",
        )

    if RepoClassification.INDICATOR_LIBRARY in classes or meta_flag(intake, "small_algorithm"):
        reasons.append("useful algorithm/library — prefer small typed reimplementation when practical")
        return IntegrationDecision(
            recommendation=IntegrationRecommendation.ADAPT_ALGORITHM,
            reasons=reasons,
            risk_level=RiskLevel.LOW if not security.findings else RiskLevel.MEDIUM,
            broker_isolation_required=broker_isolation,
            preferred_method="extract_or_wrap_into_ExternalStrategyAdapter",
        )

    if RepoClassification.STRATEGY_ALGORITHM in classes:
        reasons.append("strategy algorithm candidate for safe adapter")
        return IntegrationDecision(
            recommendation=IntegrationRecommendation.ADAPT_ALGORITHM,
            reasons=reasons,
            risk_level=risk,
            broker_isolation_required=True,
            preferred_method="ExternalStrategyAdapter",
        )

    if RepoClassification.REFERENCE_ONLY in classes:
        return IntegrationDecision(
            recommendation=IntegrationRecommendation.REFERENCE_ONLY,
            reasons=reasons or ["marked reference_only"],
            risk_level=RiskLevel.LOW,
            broker_isolation_required=True,
            preferred_method="docs_reference",
        )

    reasons.append("architecture unclear")
    return IntegrationDecision(
        recommendation=IntegrationRecommendation.REFERENCE_ONLY,
        reasons=reasons,
        risk_level=RiskLevel.HIGH,
        broker_isolation_required=True,
        preferred_method="manual_review",
    )


def meta_flag(intake: ExternalRepositoryIntake, key: str) -> bool:
    return bool((intake.metadata or {}).get(key))
