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
from app.evaluation.walkforward import (
    ChronologicalSplit,
    SplitSpec,
    WalkForwardHarness,
    WalkForwardPlan,
    WalkForwardResult,
    WindowMode,
)

__all__ = [
    "ChronologicalSplit",
    "DatasetIdentity",
    "MarketContextSnapshot",
    "MarketRegime",
    "RegimeClassifierConfig",
    "RegimePerformanceBucket",
    "ResearchProvenance",
    "SplitRole",
    "SplitSpec",
    "StrategyComparisonReport",
    "StrategyEvaluationRecord",
    "StrategyEvaluationService",
    "TradeOutcomeAttribution",
    "WalkForwardHarness",
    "WalkForwardPlan",
    "WalkForwardResult",
    "WindowMode",
]
