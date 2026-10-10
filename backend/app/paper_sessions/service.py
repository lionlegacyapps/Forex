"""Paper session lifecycle service — manual activation only.

No public HTTP start endpoint. No auto-start on deploy/restart.
PAPER_EXECUTE is rejected in V1 (disabled).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.audit.service import AuditService
from app.models.broker_account import BrokerAccount
from app.models.enums import (
    PaperSessionExecutionMode,
    PaperSessionState,
    TradingMode,
)
from app.models.mixins import utc_now
from app.models.paper_trading_session import PaperTradingSession
from app.models.strategy_paper_qualification import StrategyPaperQualification
from app.paper_sessions.errors import (
    ActivationRejectedError,
    PaperExecuteDisabledError,
    PaperSessionError,
)
from app.paper_sessions.memory import PaperSessionMemoryRecorder
from app.paper_sessions.reconciliation import (
    BrokerSnapshotSource,
    StaticBrokerSnapshotSource,
    assert_activation_safe,
    reconcile_before_activation,
)
from app.paper_sessions.repository import PaperSessionRepository
from app.paper_sessions.risk_limits import SessionRiskLimits
from app.paper_sessions.states import assert_transition
from app.qualification.auth import AuthenticatedOwner
from app.qualification.eligibility import PaperEligibilityService

logger = logging.getLogger(__name__)

SESSION_CREATED = "PAPER_SESSION_CREATED"
SESSION_READY = "PAPER_SESSION_READY"
SESSION_STARTED = "PAPER_SESSION_STARTED"
SESSION_PAUSED = "PAPER_SESSION_PAUSED"
SESSION_RESUMED = "PAPER_SESSION_RESUMED"
SESSION_STOPPING = "PAPER_SESSION_STOPPING"
SESSION_STOPPED = "PAPER_SESSION_STOPPED"
SESSION_KILL = "PAPER_SESSION_EMERGENCY_KILL"
SESSION_FAILED = "PAPER_SESSION_FAILED"

# V1: PAPER_EXECUTE cannot be activated.
ALLOW_PAPER_EXECUTE_ACTIVATION = False


class PaperSessionService:
    def __init__(
        self,
        db: Session,
        *,
        audit: AuditService | None = None,
        eligibility: PaperEligibilityService | None = None,
        memory: PaperSessionMemoryRecorder | None = None,
        broker_source: BrokerSnapshotSource | None = None,
        allow_paper_execute: bool = ALLOW_PAPER_EXECUTE_ACTIVATION,
    ) -> None:
        self.db = db
        self.repo = PaperSessionRepository(db)
        self.audit = audit or AuditService(db)
        self.eligibility = eligibility or PaperEligibilityService(db)
        self.memory = memory or PaperSessionMemoryRecorder(db)
        self.broker_source = broker_source or StaticBrokerSnapshotSource()
        self.allow_paper_execute = allow_paper_execute
        self._broker_orders_created = 0

    @property
    def broker_orders_created(self) -> int:
        return self._broker_orders_created

    def create_session(
        self,
        *,
        owner: AuthenticatedOwner,
        engine_strategy_id: str,
        strategy_version: str,
        parameter_hash: str,
        parameters: dict[str, Any],
        qualification_approval_id: uuid.UUID,
        evidence_fingerprint: str,
        broker_account_id: uuid.UUID,
        instrument: str,
        timeframe: str,
        risk_limits: SessionRiskLimits,
        strategy_db_id: uuid.UUID | None = None,
        execution_mode: PaperSessionExecutionMode = PaperSessionExecutionMode.DRY_RUN,
        max_orders_per_session: int | None = None,
    ) -> PaperTradingSession:
        if execution_mode == PaperSessionExecutionMode.PAPER_EXECUTE:
            if not self.allow_paper_execute:
                raise PaperExecuteDisabledError()

        account = self.db.get(BrokerAccount, broker_account_id)
        if account is None:
            raise ActivationRejectedError("broker account not found", code="account_missing")
        if account.trading_mode != TradingMode.PAPER:
            raise ActivationRejectedError("live account rejected", code="live_account")

        qual = self.db.get(StrategyPaperQualification, qualification_approval_id)
        if qual is None:
            raise ActivationRejectedError(
                "qualification approval not found", code="qualification_missing"
            )

        existing = self.repo.find_active_for_account(broker_account_id)
        if existing is not None:
            raise ActivationRejectedError(
                "conflicting active session on account",
                code="conflicting_session",
            )

        row = PaperTradingSession(
            strategy_db_id=strategy_db_id,
            engine_strategy_id=engine_strategy_id,
            strategy_version=strategy_version,
            parameter_hash=parameter_hash,
            parameters=dict(parameters or {}),
            qualification_approval_id=qualification_approval_id,
            evidence_fingerprint=evidence_fingerprint,
            broker_account_id=broker_account_id,
            instrument=instrument.strip().upper(),
            timeframe=timeframe,
            session_state=PaperSessionState.CREATED,
            execution_mode=execution_mode,
            created_by=owner.subject,
            risk_limits=risk_limits.to_storage(),
            max_orders_per_session=max_orders_per_session
            or risk_limits.max_orders_per_session,
            orders_submitted_count=0,
            state_version=0,
        )
        self.repo.add(row)
        self._audit(SESSION_CREATED, row, owner=owner)
        self.memory.record(
            session_id=row.id,
            symbol=row.instrument,
            event_time=utc_now(),
            event_kind="session_created",
            payload={
                "state": row.session_state.value,
                "execution_mode": row.execution_mode.value,
                "created_by": owner.subject,
            },
            strategy_db_id=strategy_db_id,
        )
        assert self._broker_orders_created == 0
        return row

    async def activate(
        self,
        session_id: uuid.UUID,
        *,
        owner: AuthenticatedOwner,
        now: datetime | None = None,
    ) -> PaperTradingSession:
        """Explicit manual start — never called automatically."""
        now = now or datetime.now(UTC)
        row = self._get(session_id)
        if row.created_by != owner.subject:
            # Owner must match creator OR be in allowlist (already authenticated).
            # Still require authenticated owner; allow any allowlisted owner.
            pass

        if row.execution_mode == PaperSessionExecutionMode.PAPER_EXECUTE:
            if not self.allow_paper_execute:
                raise PaperExecuteDisabledError()

        account = self.db.get(BrokerAccount, row.broker_account_id)
        if account is None or account.trading_mode != TradingMode.PAPER:
            raise ActivationRejectedError("live account rejected", code="live_account")
        if not account.is_enabled:
            raise ActivationRejectedError(
                "paper account is not enabled", code="account_disabled"
            )

        elig = self.eligibility.check(
            engine_strategy_id=row.engine_strategy_id,
            strategy_version=row.strategy_version,
            parameter_hash=row.parameter_hash,
            evidence_fingerprint=row.evidence_fingerprint,
            broker_account_id=row.broker_account_id,
            now=now,
        )
        if not elig.eligible:
            raise ActivationRejectedError(
                "qualification check failed: " + ",".join(elig.reasons),
                code="qualification_failed",
            )
        if elig.qualification_id != row.qualification_approval_id:
            # Binding must match the stored approval id when present on eligibility
            if elig.qualification_id is not None:
                raise ActivationRejectedError(
                    "qualification approval id mismatch",
                    code="qualification_mismatch",
                )

        # Risk limits present
        SessionRiskLimits.from_storage(row.risk_limits)

        recon = await reconcile_before_activation(
            self.db,
            account=account,
            broker_source=self.broker_source,
            instrument=row.instrument,
        )
        assert_activation_safe(recon)

        if row.session_state == PaperSessionState.CREATED:
            row = self._transition(
                row,
                PaperSessionState.READY,
                start_requested_at=now,
            )
            self._audit(SESSION_READY, row, owner=owner)

        if row.session_state != PaperSessionState.READY:
            raise ActivationRejectedError(
                f"cannot start from state {row.session_state.value}",
                code="invalid_start_state",
            )

        row = self._transition(
            row,
            PaperSessionState.RUNNING,
            started_at=now,
            last_heartbeat_at=now,
        )
        self._audit(SESSION_STARTED, row, owner=owner, details={"mode": row.execution_mode.value})
        self.memory.record(
            session_id=row.id,
            symbol=row.instrument,
            event_time=now,
            event_kind="session_started",
            payload={
                "state": row.session_state.value,
                "execution_mode": row.execution_mode.value,
                "reconciliation_ok": recon.ok,
            },
            strategy_db_id=row.strategy_db_id,
        )
        assert self._broker_orders_created == 0
        return row

    def pause(
        self, session_id: uuid.UUID, *, owner: AuthenticatedOwner
    ) -> PaperTradingSession:
        row = self._get(session_id)
        row = self._transition(row, PaperSessionState.PAUSING)
        row = self._transition(row, PaperSessionState.PAUSED)
        self._audit(SESSION_PAUSED, row, owner=owner)
        self.memory.record(
            session_id=row.id,
            symbol=row.instrument,
            event_time=utc_now(),
            event_kind="session_paused",
            payload={"state": row.session_state.value},
            strategy_db_id=row.strategy_db_id,
        )
        return row

    def resume(
        self, session_id: uuid.UUID, *, owner: AuthenticatedOwner
    ) -> PaperTradingSession:
        row = self._get(session_id)
        if row.session_state != PaperSessionState.PAUSED:
            raise PaperSessionError("resume requires PAUSED", code="invalid_resume")
        # Re-check eligibility before resume
        elig = self.eligibility.check(
            engine_strategy_id=row.engine_strategy_id,
            strategy_version=row.strategy_version,
            parameter_hash=row.parameter_hash,
            evidence_fingerprint=row.evidence_fingerprint,
            broker_account_id=row.broker_account_id,
        )
        if not elig.eligible:
            raise ActivationRejectedError(
                "cannot resume: " + ",".join(elig.reasons),
                code="qualification_failed",
            )
        row = self._transition(row, PaperSessionState.RUNNING, last_heartbeat_at=utc_now())
        self._audit(SESSION_RESUMED, row, owner=owner)
        return row

    def stop(
        self,
        session_id: uuid.UUID,
        *,
        owner: AuthenticatedOwner,
        reason: str = "manual_stop",
    ) -> PaperTradingSession:
        row = self._get(session_id)
        if row.session_state in {PaperSessionState.STOPPED, PaperSessionState.FAILED}:
            return row

        if row.session_state in {
            PaperSessionState.CREATED,
            PaperSessionState.READY,
        }:
            row = self._transition(
                row,
                PaperSessionState.STOPPED,
                stopped_at=utc_now(),
                stop_reason=reason,
            )
        else:
            if row.session_state != PaperSessionState.STOPPING:
                row = self._transition(row, PaperSessionState.STOPPING)
                self._audit(SESSION_STOPPING, row, owner=owner)
            row = self._transition(
                row,
                PaperSessionState.STOPPED,
                stopped_at=utc_now(),
                stop_reason=reason,
            )

        self._audit(SESSION_STOPPED, row, owner=owner, details={"reason": reason})
        self.memory.record(
            session_id=row.id,
            symbol=row.instrument,
            event_time=utc_now(),
            event_kind="session_stopped",
            payload={"reason": reason, "state": row.session_state.value},
            strategy_db_id=row.strategy_db_id,
        )
        # Does not claim open orders/positions are eliminated.
        return row

    def emergency_kill(
        self,
        session_id: uuid.UUID,
        *,
        owner: AuthenticatedOwner,
        reason: str = "emergency_kill",
    ) -> dict[str, Any]:
        """Immediately disable further strategy submissions.

        Does NOT claim submitted orders or positions are eliminated.
        Account-scoped: only affects this session.
        """
        row = self._get(session_id)
        row = self.stop(session_id, owner=owner, reason=reason)
        self._audit(SESSION_KILL, row, owner=owner, details={"reason": reason})
        return {
            "session_id": str(row.id),
            "session_state": row.session_state.value,
            "further_submissions_disabled": True,
            "orders_cancelled": False,
            "positions_liquidated": False,
            "note": (
                "Emergency kill disabled this session only. "
                "Already submitted orders and existing positions are NOT claimed eliminated."
            ),
        }

    def recover_stale_lease(
        self,
        session_id: uuid.UUID,
        *,
        now: datetime | None = None,
    ) -> PaperTradingSession:
        """Clear expired worker lease after crash (no auto-start)."""
        now = now or datetime.now(UTC)
        row = self._get(session_id)
        if (
            row.worker_lease_expires_at is not None
            and row.worker_lease_expires_at <= now
        ):
            row = self.repo.update_atomic(
                row,
                expected_version=row.state_version,
                worker_lease_owner=None,
                worker_lease_expires_at=None,
            )
        return row

    def _get(self, session_id: uuid.UUID) -> PaperTradingSession:
        row = self.repo.get(session_id)
        if row is None:
            raise PaperSessionError("session not found", code="not_found")
        return row

    def _transition(
        self,
        row: PaperTradingSession,
        target: PaperSessionState,
        **fields: Any,
    ) -> PaperTradingSession:
        assert_transition(row.session_state, target)
        return self.repo.transition_atomic(
            row,
            expected_version=row.state_version,
            new_state=target,
            **fields,
        )

    def _audit(
        self,
        event_type: str,
        row: PaperTradingSession,
        *,
        owner: AuthenticatedOwner | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "engine_strategy_id": row.engine_strategy_id,
            "strategy_version": row.strategy_version,
            "parameter_hash": row.parameter_hash,
            "broker_account_id": str(row.broker_account_id),
            "execution_mode": row.execution_mode.value,
            "session_state": row.session_state.value,
            **(details or {}),
        }
        self.audit.record(
            event_type=event_type,
            entity_type="paper_trading_session",
            entity_id=row.id,
            actor_type=owner.actor_type if owner else "system",
            actor_reference=owner.subject if owner else None,
            details=payload,
        )
