"""Stable idempotency keys for session decisions."""

from __future__ import annotations

import uuid
from datetime import datetime

from app.evaluation.hashing import sha256_hex
from app.strategies.decision import StrategyDecision


def decision_identity(decision: StrategyDecision) -> str:
    if not decision.is_actionable:
        return f"no_action:{decision.action.value}"
    return (
        f"{decision.action.value}:{decision.symbol}:{decision.side}:"
        f"{decision.order_type}:{decision.quantity}"
    )


def build_idempotency_key(
    *,
    session_id: uuid.UUID,
    strategy_id: str,
    strategy_version: str,
    broker_account_id: uuid.UUID,
    instrument: str,
    bar_timestamp: datetime,
    decision_id: str,
) -> str:
    raw = (
        f"{session_id}|{strategy_id}|{strategy_version}|{broker_account_id}|"
        f"{instrument.strip().upper()}|{bar_timestamp.isoformat()}|{decision_id}"
    )
    return sha256_hex(raw)[:64]
