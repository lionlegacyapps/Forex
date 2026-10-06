"""Append-only audit event writer (no secrets)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent

# Well-known event types for the safety pipeline.
TRADE_PROPOSAL_CREATED = "TRADE_PROPOSAL_CREATED"
RISK_APPROVED = "RISK_APPROVED"
RISK_REJECTED = "RISK_REJECTED"
ORDER_VALIDATED = "ORDER_VALIDATED"
ORDER_VALIDATION_REJECTED = "ORDER_VALIDATION_REJECTED"
ORDER_ROUTED = "ORDER_ROUTED"
SIMULATION_ORDER_SUBMITTED = "SIMULATION_ORDER_SUBMITTED"
SIM_ORDER_ACCEPTED = "SIM_ORDER_ACCEPTED"
SIM_ORDER_FILLED = "SIM_ORDER_FILLED"
EXECUTION_RECORDED = "EXECUTION_RECORDED"
POSITION_OPENED = "POSITION_OPENED"
POSITION_INCREASED = "POSITION_INCREASED"
POSITION_REDUCED = "POSITION_REDUCED"
POSITION_CLOSED = "POSITION_CLOSED"
POSITION_REVERSED = "POSITION_REVERSED"
DAILY_LOSS_LIMIT_REACHED = "DAILY_LOSS_LIMIT_REACHED"
EXPOSURE_LIMIT_REJECTED = "EXPOSURE_LIMIT_REJECTED"
PIPELINE_ERROR = "PIPELINE_ERROR"

# Alpaca paper execution (V1)
ALPACA_PAPER_PRE_SUBMIT_CHECK = "ALPACA_PAPER_PRE_SUBMIT_CHECK"
ALPACA_PAPER_ORDER_SUBMITTED = "ALPACA_PAPER_ORDER_SUBMITTED"
ALPACA_PAPER_ORDER_ACCEPTED = "ALPACA_PAPER_ORDER_ACCEPTED"
ALPACA_PAPER_ORDER_REJECTED = "ALPACA_PAPER_ORDER_REJECTED"
ALPACA_PAPER_ORDER_STATUS_SYNCED = "ALPACA_PAPER_ORDER_STATUS_SYNCED"
ALPACA_PAPER_FILL_RECORDED = "ALPACA_PAPER_FILL_RECORDED"
ALPACA_RECONCILIATION_MISMATCH = "ALPACA_RECONCILIATION_MISMATCH"

# Paper order lifecycle V1
ALPACA_ORDER_STATUS_SYNCED = "ALPACA_ORDER_STATUS_SYNCED"
ALPACA_ORDER_PARTIALLY_FILLED = "ALPACA_ORDER_PARTIALLY_FILLED"
ALPACA_ORDER_FILLED = "ALPACA_ORDER_FILLED"
ALPACA_ORDER_CANCEL_REQUESTED = "ALPACA_ORDER_CANCEL_REQUESTED"
ALPACA_ORDER_CANCELLED = "ALPACA_ORDER_CANCELLED"
ALPACA_ORDER_CANCEL_FAILED = "ALPACA_ORDER_CANCEL_FAILED"
ALPACA_ORDER_REJECTED = "ALPACA_ORDER_REJECTED"
ALPACA_ORDER_EXPIRED = "ALPACA_ORDER_EXPIRED"
ALPACA_FILL_RECORDED = "ALPACA_FILL_RECORDED"

_FORBIDDEN_DETAIL_KEYS = frozenset(
    {
        "password",
        "secret",
        "token",
        "api_key",
        "apikey",
        "authorization",
        "database_url",
        "connection_string",
        "credentials",
        "private_key",
    }
)


def _sanitize_details(details: dict[str, Any] | None) -> dict[str, Any]:
    if not details:
        return {}
    cleaned: dict[str, Any] = {}
    for key, value in details.items():
        lowered = key.lower()
        if any(bad in lowered for bad in _FORBIDDEN_DETAIL_KEYS):
            continue
        cleaned[key] = value
    return cleaned


class AuditService:
    """Persist non-secret audit events for pipeline decisions."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def record(
        self,
        *,
        event_type: str,
        entity_type: str,
        entity_id: uuid.UUID | None = None,
        actor_type: str = "system",
        actor_reference: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_type=actor_type,
            actor_reference=actor_reference,
            details=_sanitize_details(details),
        )
        self._session.add(event)
        self._session.flush()
        return event
