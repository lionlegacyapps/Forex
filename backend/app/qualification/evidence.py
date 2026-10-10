"""Review walk-forward evidence against qualification criteria."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.evaluation.hashing import canonical_json, sha256_hex
from app.evaluation.models import SplitRole
from app.evaluation.walkforward.harness import WalkForwardResult
from app.qualification.criteria import QualificationCriteria
from app.qualification.findings import FindingSeverity, QualificationFinding
from app.qualification.report import QualificationReport
from app.qualification.states import QualificationRecommendation


def evidence_fingerprint(
    *,
    harness_id: str,
    strategy_id: str,
    strategy_version: str,
    parameter_hash: str,
    dataset_fingerprint: str,
) -> str:
    """Immutable binding of strategy configuration to evaluation evidence."""
    return sha256_hex(
        canonical_json(
            {
                "harness_id": harness_id,
                "strategy_id": strategy_id,
                "strategy_version": strategy_version,
                "parameter_hash": parameter_hash,
                "dataset_fingerprint": dataset_fingerprint,
            }
        )
    )


def review_walk_forward_evidence(
    result: WalkForwardResult,
    *,
    criteria: QualificationCriteria | None = None,
    generated_at: datetime | None = None,
) -> QualificationReport:
    crit = criteria or QualificationCriteria()
    hard: list[QualificationFinding] = []
    warns: list[QualificationFinding] = []
    info: list[QualificationFinding] = []

    oos_reports = [r for r in result.period_reports if r.role == SplitRole.OUT_OF_SAMPLE]
    oos_agg = next(
        (a for a in result.aggregates if a.role == SplitRole.OUT_OF_SAMPLE), None
    )
    oos_trade_count = oos_agg.total_trades if oos_agg else sum(r.trade_count for r in oos_reports)
    oos_windows = oos_agg.window_count if oos_agg else len(oos_reports)
    oos_net = oos_agg.total_net_pnl if oos_agg else None
    oos_ret = oos_agg.compounded_return_pct if oos_agg else None
    max_dd = oos_agg.max_drawdown_worst if oos_agg else None

    # Profit factor: take from first OOS period with trades (descriptive)
    pf: Decimal | None = None
    for r in oos_reports:
        if r.profit_factor is not None:
            pf = r.profit_factor
            break

    cost_assumptions: dict = {}
    for r in result.period_reports:
        if r.evaluation.cost_assumptions:
            cost_assumptions = dict(r.evaluation.cost_assumptions)
            break

    efp = evidence_fingerprint(
        harness_id=result.harness_id,
        strategy_id=result.strategy_id,
        strategy_version=result.strategy_version,
        parameter_hash=result.configuration_hash,
        dataset_fingerprint=result.dataset_fingerprint,
    )

    # --- Hard blockers ---
    if crit.require_oos_period and oos_windows < 1:
        hard.append(
            QualificationFinding(
                code="missing_oos_evidence",
                severity=FindingSeverity.HARD_BLOCKER,
                message="No out-of-sample walk-forward periods present",
            )
        )

    if oos_windows < crit.min_oos_windows:
        hard.append(
            QualificationFinding(
                code="insufficient_oos_windows",
                severity=FindingSeverity.HARD_BLOCKER,
                message=f"OOS windows {oos_windows} < required {crit.min_oos_windows}",
                details={"oos_windows": oos_windows, "required": crit.min_oos_windows},
            )
        )

    if oos_trade_count < crit.min_oos_trade_count:
        hard.append(
            QualificationFinding(
                code="insufficient_oos_trades",
                severity=FindingSeverity.HARD_BLOCKER,
                message=(
                    f"OOS trade count {oos_trade_count} < required "
                    f"{crit.min_oos_trade_count}"
                ),
                details={
                    "oos_trade_count": oos_trade_count,
                    "required": crit.min_oos_trade_count,
                },
            )
        )

    if crit.max_drawdown_abs is not None and max_dd is not None:
        if max_dd > crit.max_drawdown_abs:
            hard.append(
                QualificationFinding(
                    code="excessive_drawdown",
                    severity=FindingSeverity.HARD_BLOCKER,
                    message=f"OOS max drawdown {max_dd} exceeds {crit.max_drawdown_abs}",
                    details={"max_drawdown": str(max_dd), "limit": str(crit.max_drawdown_abs)},
                )
            )

    if crit.require_nonzero_costs:
        slip = str(cost_assumptions.get("slippage_bps", "0"))
        c_share = str(cost_assumptions.get("commission_per_share", "0"))
        c_flat = str(cost_assumptions.get("commission_flat", "0"))
        if slip == "0" and c_share == "0" and c_flat == "0":
            hard.append(
                QualificationFinding(
                    code="unrealistic_zero_cost_assumptions",
                    severity=FindingSeverity.HARD_BLOCKER,
                    message="Zero transaction-cost assumptions are not acceptable for paper qualification",
                )
            )

    if crit.require_reproducibility_metadata:
        missing = []
        if not result.harness_id:
            missing.append("harness_id")
        if not result.configuration_hash:
            missing.append("configuration_hash")
        if not result.dataset_fingerprint:
            missing.append("dataset_fingerprint")
        if not result.strategy_version:
            missing.append("strategy_version")
        if missing:
            hard.append(
                QualificationFinding(
                    code="missing_reproducibility_metadata",
                    severity=FindingSeverity.HARD_BLOCKER,
                    message="Missing reproducibility metadata",
                    details={"missing": missing},
                )
            )

    # Never treat evaluation auto-eligibility as approval
    if result.paper_eligible:
        hard.append(
            QualificationFinding(
                code="evaluation_claimed_paper_eligible",
                severity=FindingSeverity.HARD_BLOCKER,
                message="Walk-forward result must not claim paper_eligible=True",
            )
        )
    if not result.promotion_blocked:
        hard.append(
            QualificationFinding(
                code="evaluation_promotion_not_blocked",
                severity=FindingSeverity.HARD_BLOCKER,
                message="Walk-forward result must keep promotion_blocked=True",
            )
        )

    # --- Warnings ---
    if crit.warn_negative_oos_net_pnl and oos_net is not None and oos_net < 0:
        warns.append(
            QualificationFinding(
                code="negative_oos_net_pnl",
                severity=FindingSeverity.WARNING,
                message="OOS aggregate net PnL is negative (descriptive; not auto-reject)",
                details={"oos_net_pnl": str(oos_net)},
            )
        )

    if crit.warn_profit_factor_below is not None and pf is not None:
        if pf < crit.warn_profit_factor_below:
            warns.append(
                QualificationFinding(
                    code="low_profit_factor",
                    severity=FindingSeverity.WARNING,
                    message=f"Profit factor {pf} below warning threshold",
                )
            )

    if oos_trade_count < crit.warn_small_sample_below_trades:
        warns.append(
            QualificationFinding(
                code="small_oos_sample_warning",
                severity=FindingSeverity.WARNING,
                message="OOS trade sample is small relative to soft warning threshold",
            )
        )

    if result.robustness:
        for w in result.robustness.warnings:
            if "concentrated" in w or "regime" in w:
                warns.append(
                    QualificationFinding(
                        code="robustness_warning",
                        severity=FindingSeverity.WARNING,
                        message=w,
                    )
                )
            else:
                info.append(
                    QualificationFinding(
                        code="robustness_info",
                        severity=FindingSeverity.INFORMATIONAL,
                        message=w,
                    )
                )

    regime_notes: list[str] = []
    for r in oos_reports:
        for b in r.evaluation.regime_breakdown:
            if b.trade_count > 0 and not b.sample_reliable:
                regime_notes.append(f"unreliable_regime:{b.regime.value}")
                warns.append(
                    QualificationFinding(
                        code="unreliable_regime_bucket",
                        severity=FindingSeverity.WARNING,
                        message=f"Unreliable regime sample for {b.regime.value}",
                    )
                )

    info.append(
        QualificationFinding(
            code="no_profitability_claim",
            severity=FindingSeverity.INFORMATIONAL,
            message=(
                "Qualification criteria are configurable gates, not proof of profitability. "
                "A passing software test suite does not establish strategy profitability."
            ),
        )
    )

    sample_codes = {
        "missing_oos_evidence",
        "insufficient_oos_windows",
        "insufficient_oos_trades",
        "missing_reproducibility_metadata",
    }
    if not hard:
        recommendation = QualificationRecommendation.ELIGIBLE_FOR_REVIEW
    elif all(f.code in sample_codes for f in hard):
        recommendation = QualificationRecommendation.INSUFFICIENT_EVIDENCE
    else:
        recommendation = QualificationRecommendation.REJECT_RECOMMENDED

    return QualificationReport(
        strategy_id=result.strategy_id,
        strategy_version=result.strategy_version,
        parameter_hash=result.configuration_hash,
        evaluation_id=result.harness_id,
        dataset_fingerprint=result.dataset_fingerprint,
        evidence_fingerprint=efp,
        policy_version=crit.policy_version,
        oos_net_pnl=oos_net,
        oos_return_pct=oos_ret,
        oos_trade_count=oos_trade_count,
        oos_window_count=oos_windows,
        max_drawdown=max_dd,
        profit_factor=pf,
        cost_assumptions=cost_assumptions,
        market_regime_notes=regime_notes,
        robustness_findings=list(result.robustness.warnings) if result.robustness else [],
        hard_blockers=hard,
        warnings=warns,
        informational=info,
        recommendation=recommendation,
        generated_at=generated_at or datetime.now(UTC),
        reproducibility={
            "harness_id": result.harness_id,
            "configuration_hash": result.configuration_hash,
            "dataset_fingerprint": result.dataset_fingerprint,
            "mode": result.mode,
        },
    )
