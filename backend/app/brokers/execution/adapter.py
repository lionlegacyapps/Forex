"""BrokerExecutionAdapter — controlled mutation surface (submit only in V1).

Separate from:
  - MarketDataProvider
  - BrokerAccountReader

ALPACA PAPER EXECUTION DOES NOT ENABLE LIVE TRADING.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.brokers.execution.types import ExecutionResult, ExecutionSubmission


class BrokerExecutionAdapter(ABC):
    """Minimal write capability for broker order submission."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...

    @abstractmethod
    async def submit_order(self, submission: ExecutionSubmission) -> ExecutionResult:
        """Submit exactly one order after enforcing pipeline preconditions.

        Must NOT expose cancel/replace/close in V1 application surface.
        """
