"""Normalized strategy evaluation records."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.backtesting.metrics import PerformanceMetrics
from app.backtesting.result import BacktestResult
from app.evaluation.hashing import (
    configuration_hash,
    dataset_fingerprint,
    evaluation_identity,
)
from app.evaluation.regimes import MarketContextSnapshot, MarketRegime
from app.market_data.models import Bar


class SplitRole(StrEnum):
    """Walk-forward readiness labels — not an optimizer."""

    TRAIN = "train"
    VALIDATION = "validation"
    OUT_OF_SAMPLE = "out_of_sample"
    FULL_SAMPLE = "full_sample"  # must not be mislabeled as OOS


class ResearchProvenance(BaseModel):
    research_model_id: str | None = None
    source_repository: str | None = None
    pinned_commit: str | None = None
    model_version: str | None = None
    data_version: str | None = None
    is_trained_ai_policy: bool = False
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DatasetIdentity(BaseModel):
    symbol: str
    timeframe: str
    fingerprint: str
    start: datetime | None = None
    end: datetime | None = None
    bar_count: int = 0


class TradeOutcomeAttribution(BaseModel):
    strategy_id: str
    strategy_version: str
    symbol: str
    timeframe: str
    entry_time: datetime
    exit_time: datetime
    side: str
    gross_pnl: Decimal
    costs: Decimal
    net_pnl: Decimal
    holding_duration_seconds: float
    exit_reason: str
    entry_regimes: list[MarketRegime] = Field(default_factory=list)
    entry_context: MarketContextSnapshot | None = None
    research_source: str | None = None


class RegimePerformanceBucket(BaseModel):
    regime: MarketRegime
    trade_count: int
    net_pnl: Decimal
    win_rate: Decimal | None = None
    average_net_pnl: Decimal | None = None
    sample_reliable: bool = False
    warnings: list[str] = Field(default_factory=list)


class StrategyEvaluationRecord(BaseModel):
    """Traceable evaluation evidence — identity separate from wall-clock time."""

    evaluation_id: str
    strategy_id: str
    strategy_name: str
    strategy_version: str
    configuration_hash: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    dataset: DatasetIdentity
    execution_assumptions: dict[str, Any] = Field(default_factory=dict)
    cost_assumptions: dict[str, Any] = Field(default_factory=dict)
    research: ResearchProvenance = Field(default_factory=ResearchProvenance)
    evaluated_at: datetime
    split_role: SplitRole = SplitRole.FULL_SAMPLE
    metrics: PerformanceMetrics
    attributions: list[TradeOutcomeAttribution] = Field(default_factory=list)
    regime_breakdown: list[RegimePerformanceBucket] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    paper_eligible: bool = False  # never auto-set True by this module
    promotion_blocked: bool = True

    def to_serializable_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ComparisonMetric(BaseModel):
    strategy_id: str
    strategy_version: str
    evaluation_id: str
    net_pnl: Decimal
    total_return_pct: Decimal
    win_rate: Decimal | None
    profit_factor: Decimal | None
    expectancy: Decimal | None
    max_drawdown: Decimal | None
    max_drawdown_pct: Decimal | None
    number_of_trades: int
    average_win: Decimal | None
    average_loss: Decimal | None
    costs_total: Decimal | None = None


class StrategyComparisonReport(BaseModel):
    comparable: bool
    dataset_fingerprint: str | None = None
    reasons_not_comparable: list[str] = Field(default_factory=list)
    metrics: list[ComparisonMetric] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    ranking_note: str = (
        "Do not rank strategies on win rate alone. "
        "Consider net return, drawdown, expectancy, profit factor, and sample size."
    )


def build_dataset_identity(
    bars: list[Bar],
    *,
    symbol: str,
    timeframe: str,
) -> DatasetIdentity:
    fp = dataset_fingerprint(bars, symbol=symbol, timeframe=timeframe)
    return DatasetIdentity(
        symbol=symbol.strip().upper(),
        timeframe=timeframe,
        fingerprint=fp,
        start=bars[0].timestamp if bars else None,
        end=bars[-1].timestamp if bars else None,
        bar_count=len(bars),
    )


def evaluation_id_from_inputs(
    *,
    strategy_id: str,
    strategy_version: str,
    parameters: dict[str, Any],
    dataset: DatasetIdentity,
    execution_assumptions: dict[str, Any],
    cost_assumptions: dict[str, Any],
) -> tuple[str, str]:
    cfg = configuration_hash(parameters)
    eid = evaluation_identity(
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        configuration_hash=cfg,
        dataset_fingerprint=dataset.fingerprint,
        execution_assumptions=execution_assumptions,
        cost_assumptions=cost_assumptions,
    )
    return eid, cfg


def metrics_from_backtest(result: BacktestResult) -> PerformanceMetrics:
    return result.metrics
