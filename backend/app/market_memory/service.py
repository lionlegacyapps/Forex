"""Market Memory persistence service for evaluation evidence."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.evaluation.hashing import sha256_hex
from app.evaluation.models import StrategyEvaluationRecord
from app.evaluation.regimes import MarketContextSnapshot
from app.evaluation.walkforward.harness import WalkForwardResult
from app.market_memory.repository import (
    EVENT_TYPE_EVALUATION,
    EVENT_TYPE_WALK_FORWARD,
    MarketMemoryRepository,
)
from app.models.enums import AssetClass
from app.models.market_memory_event import MarketMemoryEvent


class MarketMemoryService:
    """Persist approved evaluation summaries — never promotes strategies."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = MarketMemoryRepository(session)

    def persist_evaluation(
        self,
        record: StrategyEvaluationRecord,
        *,
        asset_class: AssetClass = AssetClass.EQUITY,
        strategy_db_id: uuid.UUID | None = None,
    ) -> tuple[MarketMemoryEvent, bool]:
        if record.paper_eligible or not record.promotion_blocked:
            raise RuntimeError("refusing to persist auto-promoted evaluation")
        summary = record.to_serializable_dict()
        # Drop bulky attribution detail from DB payload (counts retained by repo)
        return self.repo.persist_evaluation_summary(
            evidence_id=record.evaluation_id,
            symbol=record.dataset.symbol,
            asset_class=asset_class,
            event_time=record.evaluated_at,
            summary=summary,
            strategy_db_id=strategy_db_id,
            engine_strategy_id=record.strategy_id,
        )

    def persist_context_snapshot(
        self,
        snapshot: MarketContextSnapshot,
        *,
        asset_class: AssetClass = AssetClass.EQUITY,
        strategy_db_id: uuid.UUID | None = None,
        event_time: datetime | None = None,
    ) -> tuple[MarketMemoryEvent, bool]:
        payload = snapshot.model_dump(mode="json")
        evidence_id = sha256_hex(
            f"regime:{snapshot.symbol}:{snapshot.timeframe}:{snapshot.timestamp}"
            f":{snapshot.bar_index}"
        )
        ts = event_time
        if ts is None:
            ts = datetime.fromisoformat(snapshot.timestamp)
        return self.repo.persist_regime_snapshot(
            evidence_id=evidence_id,
            symbol=snapshot.symbol,
            asset_class=asset_class,
            event_time=ts,
            snapshot=payload,
            strategy_db_id=strategy_db_id,
        )

    def get_evaluation_event(self, evaluation_id: str) -> MarketMemoryEvent | None:
        return self.repo.find_by_evidence_id(
            evaluation_id, event_type=EVENT_TYPE_EVALUATION
        )

    def persist_walk_forward(
        self,
        result: WalkForwardResult,
        *,
        asset_class: AssetClass = AssetClass.EQUITY,
        strategy_db_id: uuid.UUID | None = None,
    ) -> tuple[MarketMemoryEvent, bool]:
        if result.paper_eligible or not result.promotion_blocked:
            raise RuntimeError("refusing to persist auto-promoted walk-forward result")
        return self.repo.persist_walk_forward_summary(
            evidence_id=result.harness_id,
            symbol=result.symbol,
            asset_class=asset_class,
            event_time=result.evaluated_at,
            summary=result.persistence_summary(),
            strategy_db_id=strategy_db_id,
            engine_strategy_id=result.strategy_id,
        )

    def get_walk_forward_event(self, harness_id: str) -> MarketMemoryEvent | None:
        return self.repo.find_by_evidence_id(
            harness_id, event_type=EVENT_TYPE_WALK_FORWARD
        )
