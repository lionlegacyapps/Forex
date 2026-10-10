"""Configurable paper-qualification criteria (documented conservative defaults).

Thresholds are NOT universal claims of profitability.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


POLICY_VERSION = "paper_qualification_policy_v1"


class QualificationCriteria(BaseModel):
    """Evidence gates for paper-session eligibility review."""

    policy_version: str = POLICY_VERSION

    # Hard blockers (defaults are conservative examples)
    min_oos_trade_count: int = 10
    min_oos_windows: int = 1
    max_drawdown_abs: Decimal | None = Field(
        default=Decimal("50000"),
        description="Hard block if OOS aggregate worst max_drawdown exceeds this",
    )
    require_nonzero_costs: bool = True
    require_reproducibility_metadata: bool = True
    require_oos_period: bool = True

    # Soft / warning thresholds
    warn_negative_oos_net_pnl: bool = True
    warn_profit_factor_below: Decimal | None = Field(default=Decimal("1.0"))
    warn_regime_concentration_above: float = 0.85
    warn_small_sample_below_trades: int = 20

    # Approval TTL
    approval_ttl_days: int = 30

    def model_copy_strict(self) -> QualificationCriteria:
        return self.model_copy(deep=True)
