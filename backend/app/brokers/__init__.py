"""Broker integration package.

Public contract: ``BrokerAdapter``. Adapters are selected only via the
trading pipeline's broker router — never from strategies or signals.
"""

from app.brokers.base import BrokerAdapter

__all__ = ["BrokerAdapter"]
