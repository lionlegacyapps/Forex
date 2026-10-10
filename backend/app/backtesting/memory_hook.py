"""Optional Market Memory hook for backtest events.

Provides a clean callback surface for future Market Memory / learning systems.
Does NOT implement AI learning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from app.strategies.decision import StrategyDecision


@dataclass
class BacktestMemoryEvent:
    event_type: str
    timestamp: datetime
    symbol: str
    strategy_id: str
    strategy_version: str
    market_context: dict[str, Any] = field(default_factory=dict)
    decision: dict[str, Any] | None = None
    outcome: dict[str, Any] | None = None


class BacktestMemoryHook(Protocol):
    def on_event(self, event: BacktestMemoryEvent) -> None:
        ...


class RecordingMemoryHook:
    """In-memory recorder for tests and future persistence adapters."""

    def __init__(self) -> None:
        self.events: list[BacktestMemoryEvent] = []

    def on_event(self, event: BacktestMemoryEvent) -> None:
        self.events.append(event)


def decision_event(
    *,
    timestamp: datetime,
    symbol: str,
    strategy_id: str,
    strategy_version: str,
    decision: StrategyDecision,
    market_context: dict[str, Any] | None = None,
) -> BacktestMemoryEvent:
    return BacktestMemoryEvent(
        event_type="strategy_decision",
        timestamp=timestamp,
        symbol=symbol,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        market_context=market_context or {},
        decision=decision.model_dump(mode="json"),
    )
