"""Durable repository for paper trading sessions."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.enums import PaperSessionState
from app.models.mixins import utc_now
from app.models.paper_trading_session import PaperSessionProcessedBar, PaperTradingSession
from app.paper_sessions.errors import ConcurrentSessionError
from app.paper_sessions.states import ACTIVE_STATES


class PaperSessionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, session_id: uuid.UUID) -> PaperTradingSession | None:
        return self.session.get(PaperTradingSession, session_id)

    def add(self, row: PaperTradingSession) -> PaperTradingSession:
        self.session.add(row)
        self.session.flush()
        return row

    def find_active_for_account(
        self, broker_account_id: uuid.UUID
    ) -> PaperTradingSession | None:
        q = select(PaperTradingSession).where(
            PaperTradingSession.broker_account_id == broker_account_id,
            PaperTradingSession.session_state.in_(tuple(ACTIVE_STATES)),
        )
        return self.session.execute(q).scalars().first()

    def transition_atomic(
        self,
        row: PaperTradingSession,
        *,
        expected_version: int,
        new_state: PaperSessionState,
        **fields: object,
    ) -> PaperTradingSession:
        values = {
            "session_state": new_state,
            "state_version": expected_version + 1,
            "updated_at": utc_now(),
            **fields,
        }
        stmt = (
            update(PaperTradingSession)
            .where(
                PaperTradingSession.id == row.id,
                PaperTradingSession.state_version == expected_version,
                PaperTradingSession.session_state == row.session_state,
            )
            .values(**values)
        )
        result = self.session.execute(stmt)
        if result.rowcount != 1:  # type: ignore[attr-defined]
            raise ConcurrentSessionError(
                "session state changed concurrently; transition aborted"
            )
        self.session.refresh(row)
        return row

    def find_processed(
        self, session_id: uuid.UUID, idempotency_key: str
    ) -> PaperSessionProcessedBar | None:
        q = select(PaperSessionProcessedBar).where(
            PaperSessionProcessedBar.session_id == session_id,
            PaperSessionProcessedBar.idempotency_key == idempotency_key,
        )
        return self.session.execute(q).scalars().first()

    def record_processed(
        self,
        *,
        session_id: uuid.UUID,
        bar_timestamp: datetime,
        decision_identity: str,
        idempotency_key: str,
        proposal_id: uuid.UUID | None,
        outcome: dict,
    ) -> PaperSessionProcessedBar:
        existing = self.find_processed(session_id, idempotency_key)
        if existing is not None:
            return existing
        from sqlalchemy.exc import IntegrityError

        row = PaperSessionProcessedBar(
            session_id=session_id,
            bar_timestamp=bar_timestamp,
            decision_identity=decision_identity,
            idempotency_key=idempotency_key,
            proposal_id=proposal_id,
            outcome=outcome,
        )
        try:
            with self.session.begin_nested():
                self.session.add(row)
                self.session.flush()
        except IntegrityError:
            existing = self.find_processed(session_id, idempotency_key)
            if existing is not None:
                return existing
            raise
        return row

    def update_atomic(
        self,
        row: PaperTradingSession,
        *,
        expected_version: int,
        **fields: object,
    ) -> PaperTradingSession:
        """Optimistic field update without requiring a state change."""
        values = {
            "state_version": expected_version + 1,
            "updated_at": utc_now(),
            **fields,
        }
        stmt = (
            update(PaperTradingSession)
            .where(
                PaperTradingSession.id == row.id,
                PaperTradingSession.state_version == expected_version,
            )
            .values(**values)
        )
        result = self.session.execute(stmt)
        if result.rowcount != 1:  # type: ignore[attr-defined]
            raise ConcurrentSessionError("session update conflict")
        self.session.refresh(row)
        return row

    def acquire_lease(
        self,
        row: PaperTradingSession,
        *,
        owner: str,
        expires_at: datetime,
        now: datetime,
    ) -> PaperTradingSession:
        """Acquire or renew worker lease if free/expired/owned by caller."""
        if (
            row.worker_lease_owner
            and row.worker_lease_owner != owner
            and row.worker_lease_expires_at
            and row.worker_lease_expires_at > now
        ):
            raise ConcurrentSessionError(
                f"session leased by {row.worker_lease_owner}"
            )
        return self.update_atomic(
            row,
            expected_version=row.state_version,
            worker_lease_owner=owner,
            worker_lease_expires_at=expires_at,
            last_heartbeat_at=now,
        )
