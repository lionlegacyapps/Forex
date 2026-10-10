"""Strategy registry wrapper that enforces intake gates for external adapters."""

from __future__ import annotations

from app.strategies.protocol import Strategy
from app.strategies.registry import StrategyRegistry
from app.strategy_intake.adapter import IntakeRegistrationGate
from app.strategy_intake.errors import AdapterGateError
from app.strategy_intake.models import ExternalRepositoryIntake
from app.strategy_intake.manifest import RepositoryManifest


class GatedStrategyRegistry:
    """Registers strategies only after intake gate checks.

    First-party Strategy implementations (non-adapters) register normally.
    ExternalStrategyAdapter instances require approved, commit-pinned manifests.
    Raw repository URLs / intake models are always rejected.
    """

    def __init__(self, registry: StrategyRegistry | None = None) -> None:
        self._registry = registry or StrategyRegistry()
        self._gate = IntakeRegistrationGate()

    @property
    def inner(self) -> StrategyRegistry:
        return self._registry

    def register(self, strategy: Strategy) -> None:
        self._gate.assert_can_register(strategy)
        self._registry.register(strategy)

    def register_candidate(self, candidate: object) -> None:
        """Explicit entrypoint that rejects untrusted repo objects."""
        self._gate.assert_not_raw_repository(candidate)
        if not isinstance(candidate, Strategy):
            raise AdapterGateError(
                "Candidate is not a Strategy implementation",
                code="not_a_strategy",
            )
        self.register(candidate)

    def get(self, strategy_id: str, version: str | None = None) -> Strategy:
        return self._registry.get(strategy_id, version)

    def contains(self, strategy_id: str, version: str | None = None) -> bool:
        return self._registry.contains(strategy_id, version)
