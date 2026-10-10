"""Walk-forward evaluation harness (fixed parameters; no optimization)."""

from app.evaluation.walkforward.errors import (
    DataLeakageError,
    InsufficientHistoryError,
    InvalidSplitError,
    UnsupportedStrategyError,
    WalkForwardError,
)
from app.evaluation.walkforward.harness import WalkForwardHarness, WalkForwardResult
from app.evaluation.walkforward.plan import ChronologicalSplit, WalkForwardPlan
from app.evaluation.walkforward.windows import (
    EvaluationPeriod,
    SplitSpec,
    WalkForwardWindow,
    WindowMode,
    generate_windows,
)

__all__ = [
    "ChronologicalSplit",
    "DataLeakageError",
    "EvaluationPeriod",
    "InsufficientHistoryError",
    "InvalidSplitError",
    "SplitSpec",
    "UnsupportedStrategyError",
    "WalkForwardError",
    "WalkForwardHarness",
    "WalkForwardPlan",
    "WalkForwardResult",
    "WalkForwardWindow",
    "WindowMode",
    "generate_windows",
]
