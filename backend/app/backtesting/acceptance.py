"""Backtest acceptance / qualification foundation.

Defines the shape of future qualification rules. Does NOT choose
profitability thresholds and does NOT automatically promote strategies.
A passing backtest is evidence only — not automatic approval for paper/live.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.backtesting.result import BacktestResult


class AcceptanceRule(BaseModel):
    """Declarative rule placeholder — thresholds left unset by default."""

    name: str
    description: str = ""
    # Optional thresholds; None means "not configured / not enforced"
    min_trades: int | None = None
    min_win_rate: Decimal | None = None
    min_profit_factor: Decimal | None = None
    max_drawdown_pct: Decimal | None = None
    require_positive_expectancy: bool | None = None
    enabled: bool = False


class AcceptanceEvaluation(BaseModel):
    passed: bool
    rules_evaluated: int
    failures: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class BacktestAcceptanceGate:
    """Evaluate configured rules without promoting strategy status."""

    def __init__(self, rules: list[AcceptanceRule] | None = None) -> None:
        self.rules = list(rules or [])

    def evaluate(self, result: BacktestResult) -> AcceptanceEvaluation:
        enabled = [r for r in self.rules if r.enabled]
        if not enabled:
            return AcceptanceEvaluation(
                passed=False,
                rules_evaluated=0,
                notes=[
                    "No acceptance rules enabled. Backtest results are evidence only "
                    "and do not automatically change strategy lifecycle status.",
                ],
            )

        failures: list[str] = []
        details: dict[str, Any] = {}
        m = result.metrics

        for rule in enabled:
            rule_fail: list[str] = []
            if rule.min_trades is not None and m.number_of_trades < rule.min_trades:
                rule_fail.append(
                    f"trades {m.number_of_trades} < min_trades {rule.min_trades}"
                )
            if rule.min_win_rate is not None:
                if m.win_rate is None or m.win_rate < rule.min_win_rate:
                    rule_fail.append(
                        f"win_rate {m.win_rate} < min_win_rate {rule.min_win_rate}"
                    )
            if rule.min_profit_factor is not None:
                if m.profit_factor is None or m.profit_factor < rule.min_profit_factor:
                    rule_fail.append(
                        f"profit_factor {m.profit_factor} < min {rule.min_profit_factor}"
                    )
            if rule.max_drawdown_pct is not None:
                dd = m.max_drawdown_pct
                if dd is None or dd > rule.max_drawdown_pct:
                    rule_fail.append(
                        f"max_drawdown_pct {dd} > max {rule.max_drawdown_pct}"
                    )
            if rule.require_positive_expectancy:
                if m.expectancy is None or m.expectancy <= 0:
                    rule_fail.append(f"expectancy {m.expectancy} not positive")
            details[rule.name] = {"passed": not rule_fail, "failures": rule_fail}
            failures.extend(f"{rule.name}: {f}" for f in rule_fail)

        return AcceptanceEvaluation(
            passed=len(failures) == 0,
            rules_evaluated=len(enabled),
            failures=failures,
            notes=[
                "Acceptance evaluation does not mutate StrategyStatus. "
                "Promotion remains a manual operator decision.",
            ],
            details=details,
        )
