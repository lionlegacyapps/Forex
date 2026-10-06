"""Broker execution adapters — mutation + paper lifecycle.

ALPACA PAPER EXECUTION DOES NOT ENABLE LIVE TRADING.
ALL EXTERNAL EXECUTION REMAINS ALPACA PAPER ONLY.
"""

from app.brokers.execution.adapter import BrokerExecutionAdapter
from app.brokers.execution.alpaca_paper import AlpacaPaperExecutionAdapter
from app.brokers.execution.cancellation import (
    CancellationRequest,
    CancellationResult,
    ControlledCancellationService,
)
from app.brokers.execution.client_order_id import build_client_order_id
from app.brokers.execution.errors import ExecutionAdapterError
from app.brokers.execution.event_source import NullOrderUpdateEventSource, OrderUpdateEventSource
from app.brokers.execution.fake import FakeExecutionAdapter
from app.brokers.execution.fill_sync import AlpacaFillSyncService
from app.brokers.execution.order_status_sync import OrderStatusSyncService, SyncResult
from app.brokers.execution.types import ExecutionResult, ExecutionSubmission

__all__ = [
    "AlpacaFillSyncService",
    "AlpacaPaperExecutionAdapter",
    "BrokerExecutionAdapter",
    "CancellationRequest",
    "CancellationResult",
    "ControlledCancellationService",
    "ExecutionAdapterError",
    "ExecutionResult",
    "ExecutionSubmission",
    "FakeExecutionAdapter",
    "NullOrderUpdateEventSource",
    "OrderStatusSyncService",
    "OrderUpdateEventSource",
    "SyncResult",
    "build_client_order_id",
]
