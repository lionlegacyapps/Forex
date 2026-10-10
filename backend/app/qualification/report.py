"""Qualification report models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.qualification.findings import QualificationFinding
from app.qualification.states import QualificationRecommendation


class QualificationReport(BaseModel):
    strategy_id: str
    strategy_version: str
    parameter_hash: str
    evaluation_id: str  # harness_id / evidence id
    dataset_fingerprint: str
    evidence_fingerprint: str
    policy_version: str
    oos_net_pnl: Decimal | None = None
    oos_return_pct: Decimal | None = None
    oos_trade_count: int = 0
    oos_window_count: int = 0
    max_drawdown: Decimal | None = None
    profit_factor: Decimal | None = None
    cost_assumptions: dict[str, Any] = Field(default_factory=dict)
    market_regime_notes: list[str] = Field(default_factory=list)
    robustness_findings: list[str] = Field(default_factory=list)
    hard_blockers: list[QualificationFinding] = Field(default_factory=list)
    warnings: list[QualificationFinding] = Field(default_factory=list)
    informational: list[QualificationFinding] = Field(default_factory=list)
    recommendation: QualificationRecommendation
    generated_at: datetime
    reproducibility: dict[str, Any] = Field(default_factory=dict)

    @property
    def has_hard_blockers(self) -> bool:
        return bool(self.hard_blockers)

    def to_serializable_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
