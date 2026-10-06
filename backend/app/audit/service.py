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
PIPELINE_ERROR = "PIPELINE_ERROR"

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
