"""Session-scoped PAPER_EXECUTE authorization (consent) service."""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import AuditService
from app.core.config import Settings, get_settings
from app.models.broker_account import BrokerAccount
from app.models.enums import (
    PaperExecutionConsentState,
    PaperSessionExecutionMode,
    PaperSessionState,
    TradingMode,
)
from app.models.mixins import utc_now
from app.models.paper_execution_authorization import PaperExecutionAuthorization
from app.models.paper_trading_session import PaperTradingSession
from app.paper_sessions.errors import (
    ActivationRejectedError,
    ConsentError,
    PaperExecuteDisabledError,
)
from app.paper_sessions.memory import PaperSessionMemoryRecorder
from app.paper_sessions.paper_endpoint import (
    paper_base_url_fingerprint,
    verify_alpaca_paper_endpoint,
)
from app.qualification.auth import AuthenticatedOwner
from app.qualification.eligibility import PaperEligibilityService

logger = logging.getLogger(__name__)

CONSENT_GRANTED = "PAPER_EXECUTE_CONSENT_GRANTED"
CONSENT_REVOKED = "PAPER_EXECUTE_CONSENT_REVOKED"
CONSENT_EXPIRED = "PAPER_EXECUTE_CONSENT_EXPIRED"
CONSENT_CONSUMED = "PAPER_EXECUTE_CONSENT_CONSUMED"
CONSENT_CHECKED = "PAPER_EXECUTE_CONSENT_CHECKED"

DEFAULT_CONSENT_TTL_SECONDS = 900  # 15 minutes


def build_authorization_fingerprint(
    *,
    session_id: uuid.UUID,
    broker_account_id: uuid.UUID,
    owner_subject: str,
    engine_strategy_id: str,
    strategy_version: str,
    parameter_hash: str,
    evidence_fingerprint: str,
    paper_base_url: str,
) -> str:
    material = "|".join(
        [
            str(session_id),
            str(broker_account_id),
            owner_subject.strip(),
            engine_strategy_id,
            strategy_version,
            parameter_hash,
            evidence_fingerprint,
            paper_base_url,
            "paper_execute",
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class PaperExecutionAuthorizationService:
    """Grant / revoke / validate session-scoped PAPER_EXECUTE consent."""

    def __init__(
        self,
        db: Session,
        *,
        audit: AuditService | None = None,
        eligibility: PaperEligibilityService | None = None,
        memory: PaperSessionMemoryRecorder | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.db = db
        self.audit = audit or AuditService(db)
        self.eligibility = eligibility or PaperEligibilityService(db)
        self.memory = memory or PaperSessionMemoryRecorder(db)
        self.settings = settings or get_settings()

    @property
    def feature_enabled(self) -> bool:
        return bool(self.settings.paper_session_execute_enabled)

    def require_feature_enabled(self) -> None:
        if not self.feature_enabled:
            raise PaperExecuteDisabledError()

    def get_granted(
        self, session_id: uuid.UUID
    ) -> PaperExecutionAuthorization | None:
        return self.db.execute(
            select(PaperExecutionAuthorization).where(
                PaperExecutionAuthorization.session_id == session_id,
                PaperExecutionAuthorization.consent_state
                == PaperExecutionConsentState.GRANTED,
            )
        ).scalars().first()

    def get_latest(
        self, session_id: uuid.UUID
    ) -> PaperExecutionAuthorization | None:
        return self.db.execute(
            select(PaperExecutionAuthorization)
            .where(PaperExecutionAuthorization.session_id == session_id)
            .order_by(PaperExecutionAuthorization.granted_at.desc())
        ).scalars().first()

    def expire_if_needed(
        self,
        auth: PaperExecutionAuthorization,
        *,
        now: datetime | None = None,
    ) -> PaperExecutionAuthorization:
        now = now or datetime.now(UTC)
        if (
            auth.consent_state == PaperExecutionConsentState.GRANTED
            and auth.expires_at <= now
        ):
            auth.consent_state = PaperExecutionConsentState.EXPIRED
            auth.state_version += 1
            self.db.flush()
            self.audit.record(
                event_type=CONSENT_EXPIRED,
                entity_type="paper_execution_authorization",
                entity_id=auth.id,
                actor_type="system",
                details={"session_id": str(auth.session_id)},
            )
        return auth

    def grant(
        self,
        session: PaperTradingSession,
        *,
        owner: AuthenticatedOwner,
        expires_in_seconds: int | None = None,
        one_time: bool = False,
        now: datetime | None = None,
        paper_base_url: str | None = None,
    ) -> PaperExecutionAuthorization:
        """Explicit owner consent bound to session + paper account."""
        self.require_feature_enabled()
        now = now or datetime.now(UTC)

        if session.execution_mode != PaperSessionExecutionMode.PAPER_EXECUTE:
            raise ConsentError(
                "consent requires PAPER_EXECUTE session",
                code="wrong_execution_mode",
            )
        if session.session_state in {
            PaperSessionState.STOPPED,
            PaperSessionState.FAILED,
            PaperSessionState.STOPPING,
        }:
            raise ConsentError(
                f"cannot grant consent in state {session.session_state.value}",
                code="invalid_session_state",
            )
        if session.created_by != owner.subject:
            # Allowlisted owners may grant, but session creator is preferred.
            # Still require authenticated allowlisted owner (already proven).
            pass

        account = self.db.get(BrokerAccount, session.broker_account_id)
        if account is None:
            raise ActivationRejectedError("broker account not found", code="account_missing")
        if account.trading_mode != TradingMode.PAPER:
            raise ActivationRejectedError("live account rejected", code="live_account")
        if not account.is_enabled:
            raise ActivationRejectedError(
                "paper account is not enabled", code="account_disabled"
            )

        elig = self.eligibility.check(
            engine_strategy_id=session.engine_strategy_id,
            strategy_version=session.strategy_version,
            parameter_hash=session.parameter_hash,
            evidence_fingerprint=session.evidence_fingerprint,
            broker_account_id=session.broker_account_id,
            now=now,
        )
        if not elig.eligible:
            raise ActivationRejectedError(
                "qualification check failed: " + ",".join(elig.reasons),
                code="qualification_failed",
            )

        verified_url = verify_alpaca_paper_endpoint(
            paper_base_url, settings=self.settings
        )
        url_fp = paper_base_url_fingerprint(verified_url)

        ttl = expires_in_seconds
        if ttl is None:
            ttl = int(self.settings.paper_session_execute_consent_ttl_seconds)
        if ttl <= 0 or ttl > 86400:
            raise ConsentError(
                "consent TTL must be between 1 and 86400 seconds",
                code="invalid_ttl",
            )

        existing = self.get_granted(session.id)
        if existing is not None:
            existing = self.expire_if_needed(existing, now=now)
            if existing.consent_state == PaperExecutionConsentState.GRANTED:
                raise ConsentError(
                    "active consent already exists for session",
                    code="consent_already_granted",
                )

        fingerprint = build_authorization_fingerprint(
            session_id=session.id,
            broker_account_id=session.broker_account_id,
            owner_subject=owner.subject,
            engine_strategy_id=session.engine_strategy_id,
            strategy_version=session.strategy_version,
            parameter_hash=session.parameter_hash,
            evidence_fingerprint=session.evidence_fingerprint,
            paper_base_url=verified_url,
        )

        row = PaperExecutionAuthorization(
            session_id=session.id,
            broker_account_id=session.broker_account_id,
            owner_subject=owner.subject,
            scope="paper_execute",
            consent_state=PaperExecutionConsentState.GRANTED,
            authorization_fingerprint=fingerprint,
            paper_endpoint_verified=True,
            paper_base_url_fingerprint=url_fp,
            one_time=one_time,
            granted_at=now,
            expires_at=now + timedelta(seconds=ttl),
            state_version=0,
            details={
                "engine_strategy_id": session.engine_strategy_id,
                "strategy_version": session.strategy_version,
                "parameter_hash": session.parameter_hash,
                "evidence_fingerprint": session.evidence_fingerprint,
                "qualification_approval_id": str(session.qualification_approval_id),
            },
        )
        self.db.add(row)
        self.db.flush()
        self.audit.record(
            event_type=CONSENT_GRANTED,
            entity_type="paper_execution_authorization",
            entity_id=row.id,
            actor_type=owner.actor_type,
            actor_reference=owner.subject,
            details={
                "session_id": str(session.id),
                "broker_account_id": str(session.broker_account_id),
                "expires_at": row.expires_at.isoformat(),
                "one_time": one_time,
                "authorization_fingerprint": fingerprint,
            },
        )
        self.memory.record(
            session_id=session.id,
            symbol=session.instrument,
            event_time=now,
            event_kind="execution_consent_granted",
            payload={
                "authorization_id": str(row.id),
                "expires_at": row.expires_at.isoformat(),
                "one_time": one_time,
            },
            strategy_db_id=session.strategy_db_id,
        )
        return row

    def revoke(
        self,
        session_id: uuid.UUID,
        *,
        owner: AuthenticatedOwner | None = None,
        reason: str = "manual_revoke",
        now: datetime | None = None,
    ) -> PaperExecutionAuthorization | None:
        """Revoke GRANTED consent. Idempotent if already non-granted."""
        now = now or datetime.now(UTC)
        auth = self.get_granted(session_id)
        if auth is None:
            return None
        auth.consent_state = PaperExecutionConsentState.REVOKED
        auth.revoked_at = now
        auth.revoke_reason = reason
        auth.state_version += 1
        self.db.flush()
        self.audit.record(
            event_type=CONSENT_REVOKED,
            entity_type="paper_execution_authorization",
            entity_id=auth.id,
            actor_type=owner.actor_type if owner else "system",
            actor_reference=owner.subject if owner else None,
            details={"session_id": str(session_id), "reason": reason},
        )
        return auth

    def consume_if_one_time(
        self,
        auth: PaperExecutionAuthorization,
        *,
        now: datetime | None = None,
    ) -> PaperExecutionAuthorization:
        now = now or datetime.now(UTC)
        if not auth.one_time:
            return auth
        if auth.consent_state != PaperExecutionConsentState.GRANTED:
            return auth
        auth.consent_state = PaperExecutionConsentState.CONSUMED
        auth.consumed_at = now
        auth.state_version += 1
        self.db.flush()
        self.audit.record(
            event_type=CONSENT_CONSUMED,
            entity_type="paper_execution_authorization",
            entity_id=auth.id,
            actor_type="system",
            details={"session_id": str(auth.session_id)},
        )
        return auth

    def require_active_consent(
        self,
        session: PaperTradingSession,
        *,
        now: datetime | None = None,
        expected_fingerprint: str | None = None,
    ) -> PaperExecutionAuthorization:
        """Fail-closed check immediately before PAPER_EXECUTE submission."""
        self.require_feature_enabled()
        now = now or datetime.now(UTC)

        if session.execution_mode != PaperSessionExecutionMode.PAPER_EXECUTE:
            raise ConsentError(
                "session is not PAPER_EXECUTE",
                code="wrong_execution_mode",
            )
        if session.submissions_blocked:
            raise ConsentError(
                f"submissions blocked: {session.submissions_block_reason}",
                code="submissions_blocked",
            )

        auth = self.get_granted(session.id)
        if auth is None:
            latest = self.get_latest(session.id)
            if latest is None:
                raise ConsentError(
                    "no granted execution consent", code="consent_missing"
                )
            latest = self.expire_if_needed(latest, now=now)
            if latest.consent_state == PaperExecutionConsentState.EXPIRED:
                raise ConsentError("execution consent expired", code="consent_expired")
            if latest.consent_state == PaperExecutionConsentState.REVOKED:
                raise ConsentError("execution consent revoked", code="consent_revoked")
            if latest.consent_state == PaperExecutionConsentState.CONSUMED:
                raise ConsentError(
                    "execution consent consumed", code="consent_consumed"
                )
            raise ConsentError(
                "no granted execution consent", code="consent_missing"
            )

        auth = self.expire_if_needed(auth, now=now)
        if auth.consent_state == PaperExecutionConsentState.EXPIRED:
            raise ConsentError("execution consent expired", code="consent_expired")
        if auth.consent_state == PaperExecutionConsentState.REVOKED:
            raise ConsentError("execution consent revoked", code="consent_revoked")
        if auth.consent_state == PaperExecutionConsentState.CONSUMED:
            raise ConsentError("execution consent consumed", code="consent_consumed")
        if auth.consent_state != PaperExecutionConsentState.GRANTED:
            raise ConsentError("execution consent not active", code="consent_inactive")

        if auth.broker_account_id != session.broker_account_id:
            raise ConsentError(
                "consent account mismatch", code="consent_account_mismatch"
            )
        if not auth.paper_endpoint_verified:
            raise ConsentError(
                "paper endpoint not verified on consent",
                code="paper_endpoint_unverified",
            )

        # Re-verify configured endpoint still matches fingerprint
        current_url = verify_alpaca_paper_endpoint(None, settings=self.settings)
        if paper_base_url_fingerprint(current_url) != auth.paper_base_url_fingerprint:
            raise ConsentError(
                "paper endpoint changed since consent",
                code="paper_endpoint_changed",
            )

        expected = expected_fingerprint or build_authorization_fingerprint(
            session_id=session.id,
            broker_account_id=session.broker_account_id,
            owner_subject=auth.owner_subject,
            engine_strategy_id=session.engine_strategy_id,
            strategy_version=session.strategy_version,
            parameter_hash=session.parameter_hash,
            evidence_fingerprint=session.evidence_fingerprint,
            paper_base_url=current_url,
        )
        if auth.authorization_fingerprint != expected:
            raise ConsentError(
                "authorization fingerprint mismatch (stale approval)",
                code="consent_fingerprint_mismatch",
            )

        self.audit.record(
            event_type=CONSENT_CHECKED,
            entity_type="paper_execution_authorization",
            entity_id=auth.id,
            actor_type="system",
            details={
                "session_id": str(session.id),
                "checked_at": (now or utc_now()).isoformat(),
            },
        )
        return auth
