"""ExternalStrategyAdapter — safe wrapper contract for adapted algorithms.

Maps StrategyContext → algorithm input, converts algorithm output →
StrategyDecision. Never exposes broker execution, credentials, or DB sessions.

EXTERNAL GITHUB CODE IS NEVER TRUSTED BY DEFAULT.
Adapted algorithms must be license/security/architecture approved and
pinned to an exact commit before registration.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from app.strategies.context import StrategyContext
from app.strategies.decision import StrategyDecision
from app.strategies.protocol import Strategy
from app.strategy_intake.errors import AdapterGateError, ManifestError
from app.strategy_intake.manifest import RepositoryManifest, assert_ready_for_adaptation


# Forbidden imports / types — documented for architecture tests.
FORBIDDEN_ADAPTER_DEPENDENCIES = frozenset(
    {
        "BrokerExecutionAdapter",
        "AlpacaPaperExecutionAdapter",
        "BrokerRouter",
        "TradingClient",
        "alpaca.trading",
    }
)


class ExternalStrategyAdapter(Strategy):
    """Base pattern for strategies adapted from reviewed external material.

    Subclasses implement algorithm mapping only. Registration requires an
    approved, commit-pinned RepositoryManifest via IntakeRegistrationGate.
    """

    def __init__(self, manifest: RepositoryManifest | None = None) -> None:
        self._manifest = manifest

    @property
    def source_manifest(self) -> RepositoryManifest | None:
        return self._manifest

    @abstractmethod
    def map_context(self, context: StrategyContext) -> Any:
        """Map normalized StrategyContext into algorithm-specific input."""

    @abstractmethod
    def run_algorithm(self, algorithm_input: Any) -> Any:
        """Run the adapted algorithm (internal typed code only in V1).

        Must not perform network I/O, broker calls, or credential access.
        """

    @abstractmethod
    def to_decision(self, algorithm_output: Any, context: StrategyContext) -> StrategyDecision:
        """Convert algorithm output into StrategyDecision."""

    def evaluate(self, context: StrategyContext) -> StrategyDecision:
        algorithm_input = self.map_context(context)
        algorithm_output = self.run_algorithm(algorithm_input)
        return self.to_decision(algorithm_output, context)


class IntakeRegistrationGate:
    """Prevents untrusted/unapproved repos from registering as Strategy."""

    def assert_can_register(self, strategy: Strategy) -> None:
        if isinstance(strategy, ExternalStrategyAdapter):
            manifest = strategy.source_manifest
            if manifest is None:
                raise AdapterGateError(
                    "ExternalStrategyAdapter requires an approved RepositoryManifest",
                    code="missing_manifest",
                )
            try:
                assert_ready_for_adaptation(manifest)
            except ManifestError as exc:
                raise AdapterGateError(str(exc), code=exc.code) from exc
            return
        # Native first-party strategies (not ExternalStrategyAdapter) are allowed.
        # Raw "repo objects" / dicts / untrusted callables cannot register.
        if not isinstance(strategy, Strategy):
            raise AdapterGateError(
                "Only Strategy implementations may register",
                code="not_a_strategy",
            )

    def assert_not_raw_repository(self, candidate: object) -> None:
        """Reject attempts to register a repo URL / intake blob as a Strategy."""
        from app.strategy_intake.models import ExternalRepositoryIntake

        if isinstance(candidate, (str, ExternalRepositoryIntake, RepositoryManifest)):
            raise AdapterGateError(
                "Untrusted repository metadata cannot register as Strategy directly",
                code="untrusted_repo_registration",
            )
        if isinstance(candidate, type) and issubclass(candidate, ExternalStrategyAdapter):
            # Class without approved instance/manifest is not registrable
            raise AdapterGateError(
                "ExternalStrategyAdapter class cannot register without approved instance",
                code="adapter_class_not_instance",
            )
