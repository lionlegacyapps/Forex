"""Evidence-quality warnings — no fabricated statistical confidence."""

from __future__ import annotations

from collections import Counter

from app.backtesting.result import BacktestResult
from app.evaluation.models import (
    RegimePerformanceBucket,
    SplitRole,
    StrategyEvaluationRecord,
)
from app.evaluation.regimes import MarketRegime

MIN_RELIABLE_REGIME_TRADES = 10
SMALL_SAMPLE_TRADES = 10


def collect_evaluation_warnings(
    *,
    result: BacktestResult,
    regime_breakdown: list[RegimePerformanceBucket],
    split_role: SplitRole,
    cost_assumptions: dict,
    warmup_incomplete: bool,
    missing_market_data: bool,
    lookahead_risk: bool = False,
) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    limitations: list[str] = []

    n = result.metrics.number_of_trades
    if n == 0:
        warnings.append("zero_completed_trades")
    elif n < SMALL_SAMPLE_TRADES:
        warnings.append("small_sample_size")

    if missing_market_data:
        warnings.append("missing_market_data")
    if warmup_incomplete:
        warnings.append("insufficient_warmup_history")

    slip = cost_assumptions.get("slippage_bps")
    commission_share = cost_assumptions.get("commission_per_share")
    commission_flat = cost_assumptions.get("commission_flat")
    if slip is None and commission_share is None and commission_flat is None:
        warnings.append("incomplete_cost_assumptions")
    elif (
        str(slip or "0") == "0"
        and str(commission_share or "0") == "0"
        and str(commission_flat or "0") == "0"
    ):
        warnings.append("zero_cost_assumptions_not_realistic")

    if split_role == SplitRole.FULL_SAMPLE:
        warnings.append("missing_out_of_sample_evaluation")
        limitations.append(
            "FULL_SAMPLE results must not be labeled as OUT_OF_SAMPLE evidence."
        )
    elif split_role == SplitRole.TRAIN:
        warnings.append("in_sample_train_split")
        limitations.append("TRAIN-split metrics are in-sample and must not be treated as OOS.")

    if lookahead_risk:
        warnings.append("lookahead_risk")

    if regime_breakdown:
        counts = {b.regime: b.trade_count for b in regime_breakdown}
        total = sum(counts.values()) or 1
        for regime, count in counts.items():
            if regime == MarketRegime.UNKNOWN:
                continue
            if count / total >= 0.85 and total >= 3:
                warnings.append("excessive_regime_concentration")
                break

    for bucket in regime_breakdown:
        if bucket.trade_count > 0 and not bucket.sample_reliable:
            warnings.append(f"unreliable_regime_sample:{bucket.regime.value}")

    limitations.append(
        "BACKTEST PERFORMANCE DOES NOT GUARANTEE FUTURE PERFORMANCE."
    )
    limitations.append(
        "Evaluation never enables strategies, brokers, or order submission."
    )
    return warnings, limitations


def regime_reliability_warning(trade_count: int) -> list[str]:
    if trade_count == 0:
        return ["no_trades_in_regime"]
    if trade_count < MIN_RELIABLE_REGIME_TRADES:
        return [
            f"small_regime_sample:{trade_count}"
            f"_lt_{MIN_RELIABLE_REGIME_TRADES}_not_reliable_evidence"
        ]
    return []


def concentration_from_attributions(regimes: list[MarketRegime]) -> dict[str, int]:
    return dict(Counter(r.value for r in regimes))


def assert_no_auto_promotion(record: StrategyEvaluationRecord) -> None:
    if record.paper_eligible:
        raise AssertionError("evaluation must not set paper_eligible=True")
    if not record.promotion_blocked:
        raise AssertionError("evaluation must keep promotion_blocked=True")
