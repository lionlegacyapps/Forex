"""Policies for offline RL research evaluation.

DeterministicMomentumBaselinePolicy is NOT a trained RL model and is NOT
claimed to be profitable. Heavyweight DRL training is deferred.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal

from app.research.rl.environment import Action, Observation


class Policy(ABC):
    @abstractmethod
    def act(self, observation: Observation) -> Action:
        ...


class DeterministicMomentumBaselinePolicy(Policy):
    """Simple rule: BUY if momentum > entry; SELL if momentum < exit; else HOLD."""

    def __init__(
        self,
        *,
        entry_threshold: Decimal = Decimal("0.02"),
        exit_threshold: Decimal = Decimal("-0.01"),
    ) -> None:
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold

    def act(self, observation: Observation) -> Action:
        mom = observation.momentum
        if mom is None:
            return Action.HOLD
        if observation.position_qty <= 0 and mom >= self.entry_threshold:
            return Action.BUY
        if observation.position_qty > 0 and mom <= self.exit_threshold:
            return Action.SELL
        return Action.HOLD
