"""Market Memory recording for paper session events."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.evaluation.hashing import sha256_hex
from app.market_memory.repository import MarketMemoryRepository
from app.models.enums import AssetClass


SOURCE = "paper_session_runner_v1"
EVENT_TYPE_SESSION = "paper_session_event"


class PaperSessionMemoryRecorder:
    def __init__(self, session: Session) -> None:
        self.repo = MarketMemoryRepository(session)

    def record(
        self,
        *,
        session_id: uuid.UUID,
        symbol: str,
        event_time: datetime,
        event_kind: str,
        payload: dict[str, Any],
        strategy_db_id: uuid.UUID | None = None,
        asset_class: AssetClass = AssetClass.EQUITY,
    ) -> None:
        evidence_id = sha256_hex(
            f"paper_session:{session_id}:{event_kind}:{event_time.isoformat()}:"
            f"{payload.get('idempotency_key', '')}"
        )
        # Reuse evaluation summary path shape with distinct event_type via direct insert
        # through persist_evaluation_summary would wrong-type; use regime-like path.
        from app.models.market_memory_event import MarketMemoryEvent

        existing = self.repo.find_by_evidence_id(evidence_id, event_type=EVENT_TYPE_SESSION)
        if existing is not None:
            return
        event = MarketMemoryEvent(
            symbol=symbol.strip().upper(),
            asset_class=asset_class,
            event_type=EVENT_TYPE_SESSION,
            event_time=event_time,
            market_context={
                "evidence_id": evidence_id,
                "kind": event_kind,
                "session_id": str(session_id),
                "payload_hash": sha256_hex(str(sorted(payload.items()))),
            },
            source=SOURCE,
            strategy_id=strategy_db_id,
            outcome=payload,
        )
        self.repo.session.add(event)
        self.repo.session.flush()
