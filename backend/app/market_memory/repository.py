"""Repository for market_memory_events — idempotent, non-destructive writes.

Uses existing table columns only (no migration). Stable evidence_id lives in
market_context JSONB for application-level idempotency.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.evaluation.hashing import canonical_json, sha256_hex
from app.market_memory.errors import EvidenceConflictError, EvidenceImmutabilityError
from app.models.enums import AssetClass
from app.models.market_memory_event import MarketMemoryEvent

SOURCE_EVALUATION = "strategy_evaluation_v1"
SOURCE_WALK_FORWARD = "walk_forward_evaluation_v1"
EVENT_TYPE_EVALUATION = "strategy_evaluation_summary"
EVENT_TYPE_REGIME = "market_context_snapshot"
EVENT_TYPE_WALK_FORWARD = "walk_forward_evaluation_summary"


def _payload_hash(payload: dict[str, Any]) -> str:
    return sha256_hex(canonical_json(payload))


class MarketMemoryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_by_evidence_id(
        self,
        evidence_id: str,
        *,
        event_type: str | None = None,
    ) -> MarketMemoryEvent | None:
        # JSONB containment / as_string lookup
        q = select(MarketMemoryEvent).where(
            MarketMemoryEvent.market_context["evidence_id"].as_string() == evidence_id
        )
        if event_type is not None:
            q = q.where(MarketMemoryEvent.event_type == event_type)
        return self.session.execute(q).scalars().first()

    def persist_evaluation_summary(
        self,
        *,
        evidence_id: str,
        symbol: str,
        asset_class: AssetClass,
        event_time: datetime,
        summary: dict[str, Any],
        strategy_db_id: uuid.UUID | None = None,
        engine_strategy_id: str | None = None,
        source: str = SOURCE_EVALUATION,
    ) -> tuple[MarketMemoryEvent, bool]:
        """Insert evaluation summary or return existing (idempotent).

        Returns (event, created).
        """
        # Strip huge fields — never store full OHLCV or model binaries
        safe_summary = {
            k: v
            for k, v in summary.items()
            if k
            not in {
                "bars",
                "ohlcv",
                "equity_curve",
                "model_binary",
                "attributions",  # can be large; store counts only at top level
            }
        }
        if "attributions" in summary:
            safe_summary["attribution_count"] = len(summary["attributions"])

        context = {
            "evidence_id": evidence_id,
            "payload_hash": _payload_hash(safe_summary),
            "engine_strategy_id": engine_strategy_id,
            "kind": "evaluation_summary",
        }
        existing = self.find_by_evidence_id(
            evidence_id, event_type=EVENT_TYPE_EVALUATION
        )
        if existing is not None:
            existing_hash = (existing.market_context or {}).get("payload_hash")
            new_hash = context["payload_hash"]
            if existing_hash and existing_hash != new_hash:
                raise EvidenceConflictError(
                    f"evidence_id {evidence_id} already stored with different payload"
                )
            return existing, False

        event = MarketMemoryEvent(
            symbol=symbol.strip().upper(),
            asset_class=asset_class,
            event_type=EVENT_TYPE_EVALUATION,
            event_time=event_time,
            market_context=context,
            source=source,
            strategy_id=strategy_db_id,
            trade_proposal_id=None,
            outcome=safe_summary,
        )
        self.session.add(event)
        self.session.flush()
        return event, True

    def persist_regime_snapshot(
        self,
        *,
        evidence_id: str,
        symbol: str,
        asset_class: AssetClass,
        event_time: datetime,
        snapshot: dict[str, Any],
        strategy_db_id: uuid.UUID | None = None,
        source: str = SOURCE_EVALUATION,
    ) -> tuple[MarketMemoryEvent, bool]:
        context = {
            "evidence_id": evidence_id,
            "payload_hash": _payload_hash(snapshot),
            "kind": "regime_snapshot",
            "regimes": snapshot.get("regimes", []),
        }
        existing = self.find_by_evidence_id(evidence_id, event_type=EVENT_TYPE_REGIME)
        if existing is not None:
            if (existing.market_context or {}).get("payload_hash") != context["payload_hash"]:
                raise EvidenceConflictError(
                    f"regime evidence_id {evidence_id} conflict"
                )
            return existing, False
        event = MarketMemoryEvent(
            symbol=symbol.strip().upper(),
            asset_class=asset_class,
            event_type=EVENT_TYPE_REGIME,
            event_time=event_time,
            market_context=context,
            source=source,
            strategy_id=strategy_db_id,
            outcome={"snapshot": snapshot},
        )
        self.session.add(event)
        self.session.flush()
        return event, True

    def persist_walk_forward_summary(
        self,
        *,
        evidence_id: str,
        symbol: str,
        asset_class: AssetClass,
        event_time: datetime,
        summary: dict[str, Any],
        strategy_db_id: uuid.UUID | None = None,
        engine_strategy_id: str | None = None,
        source: str = SOURCE_WALK_FORWARD,
    ) -> tuple[MarketMemoryEvent, bool]:
        """Persist compact walk-forward harness summary (idempotent)."""
        safe_summary = {
            k: v
            for k, v in summary.items()
            if k
            not in {
                "bars",
                "ohlcv",
                "equity_curve",
                "model_binary",
                "period_reports",  # use period_summaries instead
            }
        }
        context = {
            "evidence_id": evidence_id,
            "payload_hash": _payload_hash(safe_summary),
            "engine_strategy_id": engine_strategy_id,
            "kind": "walk_forward_summary",
        }
        existing = self.find_by_evidence_id(
            evidence_id, event_type=EVENT_TYPE_WALK_FORWARD
        )
        if existing is not None:
            existing_hash = (existing.market_context or {}).get("payload_hash")
            if existing_hash and existing_hash != context["payload_hash"]:
                raise EvidenceConflictError(
                    f"walk-forward evidence_id {evidence_id} conflict"
                )
            return existing, False

        event = MarketMemoryEvent(
            symbol=symbol.strip().upper(),
            asset_class=asset_class,
            event_type=EVENT_TYPE_WALK_FORWARD,
            event_time=event_time,
            market_context=context,
            source=source,
            strategy_id=strategy_db_id,
            trade_proposal_id=None,
            outcome=safe_summary,
        )
        self.session.add(event)
        self.session.flush()
        return event, True

    def update_outcome_forbidden(self, event_id: uuid.UUID, new_outcome: dict) -> None:
        """Historical evidence is immutable — always raise."""
        _ = event_id, new_outcome
        raise EvidenceImmutabilityError()
