"""Guarantees that pilot preparation never imports/calls live Alpaca order APIs."""

from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN_MODULES = frozenset(
    {
        "alpaca_trade_api",
        "alpaca",
        "alpaca.trading",
    }
)


def assert_pilot_package_isolation() -> None:
    """Static check: pilot package must not import Alpaca trading SDKs."""
    root = Path(__file__).resolve().parent
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in FORBIDDEN_MODULES:
                        raise AssertionError(f"forbidden import in {path}: {alias.name}")
            if isinstance(node, ast.ImportFrom) and node.module:
                top = node.module.split(".")[0]
                if top in FORBIDDEN_MODULES:
                    raise AssertionError(f"forbidden import in {path}: {node.module}")
                # Never import the real Alpaca paper adapter for submit from pilot.
                if node.module == "app.brokers.execution.alpaca_paper":
                    raise AssertionError(
                        f"pilot must not import AlpacaPaperExecutionAdapter ({path})"
                    )


def assert_no_real_adapter_in_router(execution_adapters: dict) -> None:
    """Runtime check: router must not hold a real AlpacaPaperExecutionAdapter."""
    for slug, adapter in (execution_adapters or {}).items():
        cls = type(adapter).__name__
        if cls == "AlpacaPaperExecutionAdapter":
            raise AssertionError(
                f"real AlpacaPaperExecutionAdapter injected for {slug!r} — forbidden in pilot prep"
            )
