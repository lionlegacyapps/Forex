"""Optional event-driven order update interface (future webhooks/websocket).

Polling via OrderStatusSyncService remains sufficient and required for V1.
This module is a foundation only — no websocket infrastructure.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class OrderUpdateEventSource(ABC):
    """Future trade-update stream. Not required for lifecycle V1."""

    @abstractmethod
    async def next_event(self) -> dict[str, Any] | None:
        """Return one normalized broker update or None if idle."""

    @abstractmethod
    async def close(self) -> None:
        ...


class NullOrderUpdateEventSource(OrderUpdateEventSource):
    """No-op source — polling only."""

    async def next_event(self) -> dict[str, Any] | None:
        return None

    async def close(self) -> None:
        return None
