"""Broker state read-path package.

Capability separation
---------------------
- MarketDataProvider / AlpacaMarketDataProvider → READ MARKET DATA
- BrokerAccountReader / AlpacaPaperAccountReader → READ PAPER ACCOUNT STATE
- BrokerExecutionAdapter (future) → NOT IMPLEMENTED

CONNECTING AN ALPACA ACCOUNT DOES NOT AUTHORIZE TRADING.
"""

from app.broker_state.errors import BrokerStateError
from app.broker_state.models import (
    AccountSnapshot,
    BrokerFillSnapshot,
    BrokerOrderSnapshot,
    BrokerPositionSnapshot,
    ReconciliationCategory,
    ReconciliationFinding,
    ReconciliationReport,
)
from app.broker_state.reader import BrokerAccountReader
from app.broker_state.reconciliation import ReconciliationEngine
from app.broker_state.registration import register_alpaca_paper_account
from app.broker_state.risk_bridge import VerifiedBrokerState
from app.broker_state.service import BrokerStateService, build_alpaca_paper_state_service

__all__ = [
    "AccountSnapshot",
    "BrokerAccountReader",
    "BrokerFillSnapshot",
    "BrokerOrderSnapshot",
    "BrokerPositionSnapshot",
    "BrokerStateError",
    "BrokerStateService",
    "ReconciliationCategory",
    "ReconciliationEngine",
    "ReconciliationFinding",
    "ReconciliationReport",
    "VerifiedBrokerState",
    "build_alpaca_paper_state_service",
    "register_alpaca_paper_account",
]
