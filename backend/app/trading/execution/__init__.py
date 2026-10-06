"""Paper execution & portfolio accounting (simulation only).

SIMULATION RESULTS DO NOT REPRESENT REAL MARKET EXECUTION.
"""

from app.trading.execution.cash_ledger import SimulatedCashLedger, default_cash_ledger
from app.trading.execution.daily_pnl import DailyPnlService
from app.trading.execution.exposure import ExposureService
from app.trading.execution.fill_logic import FillDecision, evaluate_fill
from app.trading.execution.market_data import (
    PriceUnavailableError,
    SimulationMarketData,
    default_simulation_market_data,
)
from app.trading.execution.order_transitions import (
    ALLOWED_ORDER_TRANSITIONS,
    assert_order_transition,
    can_order_transition,
)
from app.trading.execution.position_accounting import AccountingResult, PositionAccountingService
from app.trading.execution.service import PaperExecutionResult, PaperExecutionService

__all__ = [
    "SimulationMarketData",
    "default_simulation_market_data",
    "PriceUnavailableError",
    "evaluate_fill",
    "FillDecision",
    "ALLOWED_ORDER_TRANSITIONS",
    "assert_order_transition",
    "can_order_transition",
    "PositionAccountingService",
    "AccountingResult",
    "ExposureService",
    "DailyPnlService",
    "SimulatedCashLedger",
    "default_cash_ledger",
    "PaperExecutionService",
    "PaperExecutionResult",
]
