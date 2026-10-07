"""Standard test harness every adapted strategy must pass.

Checks StrategyContext I/O, determinism, broker isolation, proposal
compatibility, and backtest compatibility — without executing external
GitHub code.
"""

from __future__ import annotations

import ast
import inspect
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.backtesting import (
    BacktestEngine,
    InMemoryHistoricalMarketDataProvider,
    make_bar,
)
from app.models.enums import AssetClass, ProposalSource
from app.strategies.context import StrategyContext, StrategyPositionView
from app.strategies.decision import DecisionAction, StrategyDecision
from app.strategies.proposal_adapter import StrategyProposalAdapter
from app.strategies.protocol import Strategy
from app.strategy_intake.adapter import FORBIDDEN_ADAPTER_DEPENDENCIES, ExternalStrategyAdapter


@dataclass
class HarnessResult:
    passed: bool
    checks: dict[str, bool] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)


def _sample_context(
    *,
    action_hint: str = "neutral",
    parameters: dict[str, Any] | None = None,
) -> StrategyContext:
    closes = [Decimal("10"), Decimal("11"), Decimal("12"), Decimal("13"), Decimal("14")]
    if action_hint == "enter":
        closes = [Decimal("10"), Decimal("10"), Decimal("11"), Decimal("13"), Decimal("15")]
    elif action_hint == "exit":
        closes = [Decimal("15"), Decimal("14"), Decimal("13"), Decimal("12"), Decimal("11")]
    bars = [
        make_bar(
            "AAPL",
            datetime(2024, 1, i + 1, 16, 0, tzinfo=UTC),
            c,
            c + 1,
            c - 1,
            c,
        )
        for i, c in enumerate(closes)
    ]
    return StrategyContext(
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        timestamp=bars[-1].timestamp,
        timeframe="1Day",
        bars=bars,
        reference_price=bars[-1].close,
        position=StrategyPositionView(
            symbol="AAPL",
            quantity=Decimal("1") if action_hint == "exit" else Decimal("0"),
            side="long" if action_hint == "exit" else "flat",
            average_entry_price=Decimal("12") if action_hint == "exit" else None,
        ),
        parameters=parameters or {},
    )


def run_adapter_harness(
    strategy: Strategy,
    *,
    parameters: dict[str, Any] | None = None,
    expect_entry: bool = False,
    expect_exit: bool = False,
    source_file: Path | None = None,
) -> HarnessResult:
    checks: dict[str, bool] = {}
    failures: list[str] = []

    def mark(name: str, ok: bool, detail: str = "") -> None:
        checks[name] = ok
        if not ok:
            failures.append(f"{name}: {detail}" if detail else name)

    # Parameter validation
    try:
        params = strategy.validate_parameters(parameters or strategy.default_parameters())
        mark("parameter_validation", True)
    except Exception as exc:  # noqa: BLE001
        params = {}
        mark("parameter_validation", False, str(exc))

    # Valid context / NO_ACTION or decision
    ctx = _sample_context(parameters=params)
    try:
        d0 = strategy.evaluate(ctx)
        mark("valid_context_input", isinstance(d0, StrategyDecision))
        mark("no_action_or_decision", d0.action in set(DecisionAction))
    except Exception as exc:  # noqa: BLE001
        d0 = None
        mark("valid_context_input", False, str(exc))
        mark("no_action_or_decision", False, str(exc))

    # Determinism
    try:
        d1 = strategy.evaluate(ctx)
        d2 = strategy.evaluate(ctx)
        mark(
            "deterministic_output",
            d1.model_dump() == d2.model_dump(),
        )
    except Exception as exc:  # noqa: BLE001
        mark("deterministic_output", False, str(exc))

    if expect_entry:
        enter_ctx = _sample_context(action_hint="enter", parameters=params)
        try:
            de = strategy.evaluate(enter_ctx)
            mark(
                "entry_signal",
                de.action in {DecisionAction.ENTER_LONG, DecisionAction.ENTER_SHORT},
            )
        except Exception as exc:  # noqa: BLE001
            mark("entry_signal", False, str(exc))

    if expect_exit:
        exit_ctx = _sample_context(action_hint="exit", parameters=params)
        try:
            dx = strategy.evaluate(exit_ctx)
            mark(
                "exit_signal",
                dx.action in {DecisionAction.EXIT_LONG, DecisionAction.EXIT_SHORT},
            )
        except Exception as exc:  # noqa: BLE001
            mark("exit_signal", False, str(exc))

    # Explicit NO_ACTION path when flat/neutral if strategy supports it
    if d0 is not None:
        mark("produces_strategy_decision", True)
    else:
        mark("produces_strategy_decision", False)

    # No broker imports in adapter module
    if isinstance(strategy, ExternalStrategyAdapter):
        mod = inspect.getmodule(strategy.__class__)
        src = ""
        if source_file is not None and source_file.exists():
            src = source_file.read_text(encoding="utf-8")
        elif mod is not None and getattr(mod, "__file__", None):
            src = Path(mod.__file__).read_text(encoding="utf-8")
        if src:
            tree = ast.parse(src)
            bad = False
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    m = node.module or ""
                    if "brokers.execution" in m or m == "alpaca.trading":
                        bad = True
                    for alias in node.names:
                        if alias.name in FORBIDDEN_ADAPTER_DEPENDENCIES:
                            bad = True
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if any(f in alias.name for f in FORBIDDEN_ADAPTER_DEPENDENCIES):
                            bad = True
            mark("no_broker_imports", not bad)
        else:
            mark("no_broker_imports", True)

        # Signature / evaluate must not accept credentials
        sig = inspect.signature(strategy.evaluate)
        mark("no_credential_access", "credentials" not in sig.parameters)
        mark("no_network_execution_api", "session" not in sig.parameters)
    else:
        mark("no_broker_imports", True)
        mark("no_credential_access", True)
        mark("no_network_execution_api", True)

    # Decision → Trade Proposal compatibility
    adapter = StrategyProposalAdapter()
    try:
        probe = StrategyDecision(
            action=DecisionAction.ENTER_LONG,
            symbol="AAPL",
            asset_class=AssetClass.EQUITY,
            quantity=Decimal("1"),
        )
        # Prefer strategy-produced actionable decision if available
        candidate = d0 if d0 is not None and d0.is_actionable else probe
        if not candidate.is_actionable:
            candidate = probe
        proposal = adapter.to_proposal_input(
            candidate,
            broker_account_id=uuid4(),
            quantity=Decimal("1"),
            strategy_id=strategy.strategy_id,
            strategy_version=strategy.version,
        )
        mark(
            "decision_to_trade_proposal",
            proposal.source == ProposalSource.STRATEGY,
        )
    except Exception as exc:  # noqa: BLE001
        mark("decision_to_trade_proposal", False, str(exc))

    # Backtest compatibility + reproducibility
    try:
        provider = InMemoryHistoricalMarketDataProvider()
        bars = [
            make_bar(
                "AAPL",
                datetime(2024, 1, i + 1, 16, 0, tzinfo=UTC),
                Decimal(10 + i),
                Decimal(11 + i),
                Decimal(9 + i),
                Decimal(10 + i),
            )
            for i in range(12)
        ]
        provider.load_bars("AAPL", "1Day", bars)
        engine = BacktestEngine(provider)
        r1 = engine.run(
            strategy,
            symbols=["AAPL"],
            timeframe="1Day",
            starting_capital=Decimal("10000"),
            parameters=params,
        )
        r2 = engine.run(
            strategy,
            symbols=["AAPL"],
            timeframe="1Day",
            starting_capital=Decimal("10000"),
            parameters=params,
        )
        mark("backtest_compatibility", r1.strategy_id == strategy.strategy_id)
        mark(
            "reproducibility",
            r1.to_serializable_dict() == r2.to_serializable_dict(),
        )
    except Exception as exc:  # noqa: BLE001
        mark("backtest_compatibility", False, str(exc))
        mark("reproducibility", False, str(exc))

    return HarnessResult(passed=not failures, checks=checks, failures=failures)
