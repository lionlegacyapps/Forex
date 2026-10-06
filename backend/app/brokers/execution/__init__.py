"""Broker execution adapters — mutation surface separate from read paths.

ALPACA PAPER EXECUTION DOES NOT ENABLE LIVE TRADING.
"""

from app.brokers.execution.adapter import BrokerExecutionAdapter
from app.brokers.execution.alpaca_paper import AlpacaPaperExecutionAdapter
from app.brokers.execution.client_order_id import build_client_order_id
from app.brokers.execution.errors import ExecutionAdapterError
from app.brokers.execution.fake import FakeExecutionAdapter
from app.brokers.execution.types import ExecutionResult, ExecutionSubmission

__all__ = [
    "AlpacaPaperExecutionAdapter",
    "BrokerExecutionAdapter",
    "ExecutionAdapterError",
    "ExecutionResult",
    "ExecutionSubmission",
    "FakeExecutionAdapter",
    "build_client_order_id",
]
