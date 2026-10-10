"""Backtesting package — offline strategy simulation only.

Never routes to Alpaca or any external broker.
BACKTEST PERFORMANCE DOES NOT GUARANTEE FUTURE PERFORMANCE.
"""

from app.backtesting.acceptance import (
    AcceptanceEvaluation,
    AcceptanceRule,
    BacktestAcceptanceGate,
)
from app.backtesting.costs import BacktestCostModel
from app.backtesting.engine import BacktestEngine, LookaheadSafeBarView
from app.backtesting.errors import BacktestError, HistoricalDataError, LookaheadError
from app.backtesting.execution_model import (
    BacktestExecutionModel,
    FillReason,
    PendingOrder,
    SimulatedFill,
)
from app.backtesting.historical import (
    HistoricalMarketDataProvider,
    InMemoryHistoricalMarketDataProvider,
    make_bar,
)
from app.backtesting.memory_hook import (
    BacktestMemoryEvent,
    BacktestMemoryHook,
    RecordingMemoryHook,
)
from app.backtesting.metrics import PerformanceMetrics, calculate_metrics
from app.backtesting.portfolio import BacktestPortfolio, ClosedTrade
from app.backtesting.result import BacktestResult, BacktestTradeRecord, EquityPoint
from app.backtesting.sizing import BacktestSizingModel, SizingMode

__all__ = [
    "AcceptanceEvaluation",
    "AcceptanceRule",
    "BacktestAcceptanceGate",
    "BacktestCostModel",
    "BacktestEngine",
    "BacktestError",
    "BacktestExecutionModel",
    "BacktestMemoryEvent",
    "BacktestMemoryHook",
    "BacktestPortfolio",
    "BacktestResult",
    "BacktestSizingModel",
    "BacktestTradeRecord",
    "ClosedTrade",
    "EquityPoint",
    "FillReason",
    "HistoricalDataError",
    "HistoricalMarketDataProvider",
    "InMemoryHistoricalMarketDataProvider",
    "LookaheadError",
    "LookaheadSafeBarView",
    "PendingOrder",
    "PerformanceMetrics",
    "RecordingMemoryHook",
    "SimulatedFill",
    "SizingMode",
    "calculate_metrics",
    "make_bar",
]
