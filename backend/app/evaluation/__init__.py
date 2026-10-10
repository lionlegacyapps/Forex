"""Strategy evaluation & market-context analysis (offline research evidence)."""

from app.evaluation.models import (
    DatasetIdentity,
    RegimePerformanceBucket,
    ResearchProvenance,
    SplitRole,
    StrategyComparisonReport,
    StrategyEvaluationRecord,
    TradeOutcomeAttribution,
)
from app.evaluation.regimes import MarketContextSnapshot, MarketRegime, RegimeClassifierConfig
from app.evaluation.service import StrategyEvaluationService

__all__ = [
    "DatasetIdentity",
    "MarketContextSnapshot",
    "MarketRegime",
    "RegimeClassifierConfig",
    "RegimePerformanceBucket",
    "ResearchProvenance",
    "SplitRole",
    "StrategyComparisonReport",
    "StrategyEvaluationRecord",
    "StrategyEvaluationService",
    "TradeOutcomeAttribution",
]
