"""In-process StrategyRegistry — no dynamic untrusted code execution."""

from __future__ import annotations

from app.strategies.errors import StrategyRegistrationError
from app.strategies.protocol import Strategy, assert_strategy_metadata


class StrategyRegistry:
    """Register and look up strategy implementations by id/version.

    Does not load plugins from disk, GitHub, or arbitrary modules.
    """

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], Strategy] = {}
        self._by_id_latest: dict[str, Strategy] = {}

    def register(self, strategy: Strategy) -> None:
        assert_strategy_metadata(strategy)
        key = (strategy.strategy_id, strategy.version)
        if key in self._by_key:
            raise StrategyRegistrationError(
                f"Duplicate registration for {strategy.strategy_id}@{strategy.version}",
                code="duplicate_registration",
            )
        # Validate default parameters early
        strategy.validate_parameters(strategy.default_parameters())
        self._by_key[key] = strategy
        existing = self._by_id_latest.get(strategy.strategy_id)
        if existing is None or _version_tuple(strategy.version) >= _version_tuple(existing.version):
            self._by_id_latest[strategy.strategy_id] = strategy

    def get(self, strategy_id: str, version: str | None = None) -> Strategy:
        if version is None:
            strategy = self._by_id_latest.get(strategy_id)
            if strategy is None:
                raise StrategyRegistrationError(
                    f"Unknown strategy_id={strategy_id!r}",
                    code="strategy_not_found",
                )
            return strategy
        strategy = self._by_key.get((strategy_id, version))
        if strategy is None:
            raise StrategyRegistrationError(
                f"Unknown strategy {strategy_id}@{version}",
                code="strategy_not_found",
            )
        return strategy

    def contains(self, strategy_id: str, version: str | None = None) -> bool:
        if version is None:
            return strategy_id in self._by_id_latest
        return (strategy_id, version) in self._by_key

    def list_strategies(self) -> list[Strategy]:
        return list(self._by_key.values())

    def clear(self) -> None:
        self._by_key.clear()
        self._by_id_latest.clear()


def _version_tuple(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in version.split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)
