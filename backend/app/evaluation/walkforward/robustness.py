"""Descriptive robustness analysis — no invented confidence levels."""

from __future__ import annotations

from decimal import Decimal
from statistics import mean, pstdev

from pydantic import BaseModel, Field

from app.evaluation.walkforward.reporting import PeriodReport, RoleAggregate


class RobustnessReport(BaseModel):
    oos_window_count: int
    oos_net_pnl_values: list[str] = Field(default_factory=list)
    oos_return_pct_values: list[str] = Field(default_factory=list)
    oos_return_consistency: str | None = None  # descriptive only
    drawdown_variation: str | None = None
    profitability_concentration: str | None = None
    cost_sensitivity_note: str | None = None
    regime_dependence_note: str | None = None
    small_sample: bool = False
    warnings: list[str] = Field(default_factory=list)
    disclaimer: str = (
        "Descriptive metrics only. No statistical confidence levels are claimed. "
        "A passing software test suite does not establish strategy profitability."
    )


def analyze_robustness(
    period_reports: list[PeriodReport],
    *,
    oos_aggregate: RoleAggregate | None = None,
    zero_cost: bool = False,
) -> RobustnessReport:
    oos = [r for r in period_reports if r.role.value == "out_of_sample"]
    warnings: list[str] = []
    if not oos:
        warnings.append("missing_oos_periods")
        return RobustnessReport(oos_window_count=0, warnings=warnings, small_sample=True)

    pnls = [r.evaluation.metrics.net_pnl for r in oos]
    rets = [r.net_return for r in oos]
    dds = [r.max_drawdown for r in oos if r.max_drawdown is not None]

    consistency = None
    if len(rets) >= 2:
        mu = mean([float(x) for x in rets])
        sd = pstdev([float(x) for x in rets])
        if sd == 0:
            consistency = "identical_oos_returns_across_windows"
        elif abs(mu) > 0 and sd / abs(mu) > 1.5:
            consistency = "high_oos_return_dispersion"
        else:
            consistency = "moderate_oos_return_dispersion"
    else:
        consistency = "single_oos_window_insufficient_for_consistency"
        warnings.append("single_oos_window")

    dd_var = None
    if len(dds) >= 2:
        dd_var = f"oos_max_drawdown_range=[{min(dds)}, {max(dds)}]"
    elif len(dds) == 1:
        dd_var = f"single_oos_drawdown={dds[0]}"

    # Concentration: share of total |pnl| from best window
    concentration = None
    abs_total = sum((abs(p) for p in pnls), Decimal("0"))
    if abs_total > 0 and pnls:
        best = max(pnls, key=lambda x: abs(x))
        share = abs(best) / abs_total
        concentration = f"largest_abs_pnl_share={share:.2f}"
        if share >= Decimal("0.85") and len(pnls) >= 2:
            warnings.append("profitability_concentrated_in_one_window")

    cost_note = None
    if zero_cost:
        cost_note = "zero_cost_assumptions_not_realistic"
        warnings.append("unrealistic_zero_cost_assumptions")

    regime_note = "see per-period regime_breakdown; unreliable buckets flagged separately"
    for r in oos:
        for b in r.evaluation.regime_breakdown:
            if b.trade_count > 0 and not b.sample_reliable:
                warnings.append("unreliable_regime_buckets_present")
                break

    total_trades = oos_aggregate.total_trades if oos_aggregate else sum(r.trade_count for r in oos)
    small = total_trades < 10
    if small:
        warnings.append("small_oos_trade_sample")

    return RobustnessReport(
        oos_window_count=len(oos),
        oos_net_pnl_values=[str(p) for p in pnls],
        oos_return_pct_values=[str(r) for r in rets],
        oos_return_consistency=consistency,
        drawdown_variation=dd_var,
        profitability_concentration=concentration,
        cost_sensitivity_note=cost_note,
        regime_dependence_note=regime_note,
        small_sample=small,
        warnings=warnings,
    )
