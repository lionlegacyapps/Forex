"""Simulated PAPER_EXECUTE pilot scenarios — FakeExecutionAdapter only.

Never injects AlpacaPaperExecutionAdapter. Never places real orders.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.brokers.execution.errors import (
    AMBIGUOUS_IDEMPOTENCY_STATE,
    NETWORK_TIMEOUT,
    ORDER_REJECTED_BY_BROKER,
    ExecutionAdapterError,
)
from app.brokers.execution.fake import FakeExecutionAdapter
from app.core.config import Settings, get_settings
from app.evaluation.hashing import configuration_hash
from app.models.enums import (
    AssetClass,
    OrderType,
    PaperSessionExecutionMode,
    PaperSessionState,
)
from app.paper_sessions.errors import (
    ConsentError,
    PaperSessionError,
    UncertainOrderAcknowledgmentError,
)
from app.paper_sessions.market_data import InMemorySessionBarSource, SessionBarSource
from app.paper_sessions.reconciliation import BrokerSnapshotSource, StaticBrokerSnapshotSource
from app.paper_sessions.runner import PaperSessionRunner
from app.paper_sessions.service import PaperSessionService
from app.pilot.config import PilotConfig, assert_deployment_execute_disabled
from app.pilot.isolation import assert_no_real_adapter_in_router
from app.qualification.auth import AuthenticatedOwner
from app.strategies import DecisionAction, StrategyDecision, no_action
from app.strategies.protocol import Strategy
from app.trading.execution.market_data import SimulationMarketData
from app.trading.proposals.service import TradeProposalService
from app.trading.routing.router import BrokerRouter

logger = logging.getLogger(__name__)


class FixedDecisionStrategy(Strategy):
    """Test double that emits a fixed decision sequence."""

    def __init__(
        self,
        decisions: list[StrategyDecision],
        *,
        strategy_id: str = "sma_crossover",
        version: str = "1.0.0",
    ) -> None:
        self._decisions = list(decisions)
        self._i = 0
        self._id = strategy_id
        self._version = version

    @property
    def strategy_id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return "Pilot Fixed Decision"

    @property
    def version(self) -> str:
        return self._version

    @property
    def supported_asset_classes(self):
        return frozenset({AssetClass.EQUITY})

    @property
    def required_timeframes(self):
        return frozenset({"1Day"})

    def evaluate(self, context) -> StrategyDecision:
        _ = context
        if self._i >= len(self._decisions):
            return no_action()
        d = self._decisions[self._i]
        self._i += 1
        return d


def pilot_enter_limit(symbol: str = "AAPL", qty: Decimal = Decimal("1")) -> StrategyDecision:
    return StrategyDecision(
        action=DecisionAction.ENTER_LONG,
        symbol=symbol,
        asset_class=AssetClass.EQUITY,
        quantity=qty,
        order_type=OrderType.LIMIT,
        limit_price=Decimal("50"),
        stop_loss_price=Decimal("40"),
    )


class ScenarioResult(BaseModel):
    name: str
    ok: bool
    detail: str = ""
    fake_post_count: int = 0
    submitted: bool = False
    extras: dict[str, Any] = Field(default_factory=dict)


class KillSwitchRehearsalResult(BaseModel):
    ok: bool
    session_state: str
    further_submissions_disabled: bool
    consent_revoked: bool
    orders_cancelled_claimed: bool
    positions_liquidated_claimed: bool
    additional_submits_blocked: bool
    fake_post_count: int
    notes: list[str] = Field(default_factory=list)


class SimulatedPilotHarness:
    """Drive PAPER_EXECUTE path exclusively through FakeExecutionAdapter."""

    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        broker_source: BrokerSnapshotSource | None = None,
    ) -> None:
        # Force execute-enabled settings for in-process simulation only.
        base = settings or get_settings()
        self.settings = Settings(
            paper_qualification_owner_subjects=base.paper_qualification_owner_subjects
            or "owner@example.com",
            paper_session_execute_enabled=True,
            paper_session_execute_consent_ttl_seconds=900,
            alpaca_paper_base_url=base.alpaca_paper_base_url
            or "https://paper-api.alpaca.markets",
        )
        self.db = db
        self.broker_source = broker_source or StaticBrokerSnapshotSource(
            paper_verified=True,
            buying_power="100000",
            paper_base_url="https://paper-api.alpaca.markets",
        )

    def _pipeline(self, fake: FakeExecutionAdapter) -> TradeProposalService:
        assert_no_real_adapter_in_router({"alpaca": fake})
        market = SimulationMarketData()
        market.set_price("AAPL", Decimal("100"))
        router = BrokerRouter(
            self.db,
            execution_adapters={"alpaca": fake},
            adapters={},
            market_data=market,
        )
        assert_no_real_adapter_in_router(router._execution_adapters)  # noqa: SLF001
        return TradeProposalService(self.db, broker_router=router, market_data=market)

    async def _prepare_session(
        self,
        *,
        owner: AuthenticatedOwner,
        config: PilotConfig,
        broker_account_id: uuid.UUID,
        qualification_id: uuid.UUID,
        evidence_fingerprint: str,
        strategy_db_id: uuid.UUID | None,
        external_account_id: str,
        now: datetime,
    ):
        # Align broker source identity with account
        self.broker_source = StaticBrokerSnapshotSource(
            external_account_id=external_account_id,
            paper_verified=True,
            buying_power="100000",
            paper_base_url="https://paper-api.alpaca.markets",
        )
        svc = PaperSessionService(
            self.db,
            settings=self.settings,
            allow_paper_execute=True,
            broker_source=self.broker_source,
        )
        session = svc.create_session(
            owner=owner,
            engine_strategy_id=config.strategy_id,
            strategy_version=config.strategy_version,
            parameter_hash=configuration_hash(config.parameters),
            parameters=dict(config.parameters),
            qualification_approval_id=qualification_id,
            evidence_fingerprint=evidence_fingerprint,
            broker_account_id=broker_account_id,
            instrument=config.symbol,
            timeframe=config.timeframe,
            risk_limits=config.to_session_risk_limits(),
            strategy_db_id=strategy_db_id,
            execution_mode=PaperSessionExecutionMode.PAPER_EXECUTE,
            max_orders_per_session=config.max_orders_per_session,
        )
        svc.grant_execution_consent(
            session.id, owner=owner, expires_in_seconds=config.consent_ttl_seconds, now=now
        )
        await svc.activate(session.id, owner=owner, now=now)
        return svc, session

    async def run_success(
        self,
        *,
        owner: AuthenticatedOwner,
        config: PilotConfig,
        broker_account_id: uuid.UUID,
        qualification_id: uuid.UUID,
        evidence_fingerprint: str,
        strategy_db_id: uuid.UUID | None,
        external_account_id: str,
        bar_source: SessionBarSource,
        now: datetime | None = None,
    ) -> ScenarioResult:
        now = now or datetime.now(UTC)
        svc, session = await self._prepare_session(
            owner=owner,
            config=config,
            broker_account_id=broker_account_id,
            qualification_id=qualification_id,
            evidence_fingerprint=evidence_fingerprint,
            strategy_db_id=strategy_db_id,
            external_account_id=external_account_id,
            now=now,
        )
        fake = FakeExecutionAdapter()
        runner = PaperSessionRunner(
            self.db,
            bar_source=bar_source,
            strategy=FixedDecisionStrategy(
                [pilot_enter_limit(config.symbol, config.max_quantity)],
                strategy_id=config.strategy_id,
                version=config.strategy_version,
            ),
            proposal_service=self._pipeline(fake),
            authorization=svc.authorization,
            paper_execute_enabled=True,
            max_outstanding_orders=1,
            worker_id="pilot-sim-ok",
        )
        result = await runner.run_once(session.id, now=now)
        return ScenarioResult(
            name="successful_ack",
            ok=result.submitted is True and fake.post_count == 1,
            detail=f"submitted={result.submitted} posts={fake.post_count}",
            fake_post_count=fake.post_count,
            submitted=result.submitted,
        )

    async def run_rejection(self, **kwargs: Any) -> ScenarioResult:
        now = kwargs.get("now") or datetime.now(UTC)
        kwargs = {**kwargs, "now": now}
        owner = kwargs["owner"]
        config = kwargs["config"]
        svc, session = await self._prepare_session(
            owner=owner,
            config=config,
            broker_account_id=kwargs["broker_account_id"],
            qualification_id=kwargs["qualification_id"],
            evidence_fingerprint=kwargs["evidence_fingerprint"],
            strategy_db_id=kwargs.get("strategy_db_id"),
            external_account_id=kwargs["external_account_id"],
            now=now,
        )
        fake = FakeExecutionAdapter(fail_code=ORDER_REJECTED_BY_BROKER)
        runner = PaperSessionRunner(
            self.db,
            bar_source=kwargs["bar_source"],
            strategy=FixedDecisionStrategy(
                [pilot_enter_limit(config.symbol)],
                strategy_id=config.strategy_id,
                version=config.strategy_version,
            ),
            proposal_service=self._pipeline(fake),
            authorization=svc.authorization,
            paper_execute_enabled=True,
            worker_id="pilot-sim-rej",
        )
        result = await runner.run_once(session.id, now=now)
        return ScenarioResult(
            name="order_rejection",
            ok=result.submitted is False and fake.post_count == 0,
            detail=f"submitted={result.submitted} posts={fake.post_count}",
            fake_post_count=fake.post_count,
            submitted=result.submitted,
        )

    async def run_timeout_reconcile(self, **kwargs: Any) -> ScenarioResult:
        now = kwargs.get("now") or datetime.now(UTC)
        owner = kwargs["owner"]
        config = kwargs["config"]
        svc, session = await self._prepare_session(
            owner=owner,
            config=config,
            broker_account_id=kwargs["broker_account_id"],
            qualification_id=kwargs["qualification_id"],
            evidence_fingerprint=kwargs["evidence_fingerprint"],
            strategy_db_id=kwargs.get("strategy_db_id"),
            external_account_id=kwargs["external_account_id"],
            now=now,
        )
        fake = FakeExecutionAdapter(timeout_after_accept=True)
        runner = PaperSessionRunner(
            self.db,
            bar_source=kwargs["bar_source"],
            strategy=FixedDecisionStrategy(
                [pilot_enter_limit(config.symbol)],
                strategy_id=config.strategy_id,
                version=config.strategy_version,
            ),
            proposal_service=self._pipeline(fake),
            authorization=svc.authorization,
            paper_execute_enabled=True,
            worker_id="pilot-sim-to",
        )
        result = await runner.run_once(session.id, now=now)
        self.db.refresh(session)
        ok = (
            result.uncertain is True
            and session.submissions_blocked is True
            and fake.post_count == 1
        )
        return ScenarioResult(
            name="timeout_reconciliation",
            ok=ok,
            detail=f"uncertain={result.uncertain} blocked={session.submissions_blocked}",
            fake_post_count=fake.post_count,
            extras={"submissions_blocked": session.submissions_blocked},
        )

    async def run_unknown_outcome(self, **kwargs: Any) -> ScenarioResult:
        now = kwargs.get("now") or datetime.now(UTC)
        owner = kwargs["owner"]
        config = kwargs["config"]
        svc, session = await self._prepare_session(
            owner=owner,
            config=config,
            broker_account_id=kwargs["broker_account_id"],
            qualification_id=kwargs["qualification_id"],
            evidence_fingerprint=kwargs["evidence_fingerprint"],
            strategy_db_id=kwargs.get("strategy_db_id"),
            external_account_id=kwargs["external_account_id"],
            now=now,
        )

        class Ambiguous(FakeExecutionAdapter):
            async def submit_order(self, submission):  # type: ignore[no-untyped-def]
                raise ExecutionAdapterError("ambiguous", code=AMBIGUOUS_IDEMPOTENCY_STATE)

            async def get_order_by_client_order_id(self, client_order_id: str):
                return None

        fake = Ambiguous()
        runner = PaperSessionRunner(
            self.db,
            bar_source=kwargs["bar_source"],
            strategy=FixedDecisionStrategy(
                [pilot_enter_limit(config.symbol)],
                strategy_id=config.strategy_id,
                version=config.strategy_version,
            ),
            proposal_service=self._pipeline(fake),
            authorization=svc.authorization,
            paper_execute_enabled=True,
            worker_id="pilot-sim-unk",
        )
        raised = False
        try:
            await runner.run_once(session.id, now=now)
        except UncertainOrderAcknowledgmentError:
            raised = True
        self.db.refresh(session)
        return ScenarioResult(
            name="unknown_broker_outcome",
            ok=raised and session.submissions_blocked,
            detail=f"raised={raised} blocked={session.submissions_blocked}",
            fake_post_count=fake.post_count,
        )

    async def run_partial_fill(self, **kwargs: Any) -> ScenarioResult:
        now = kwargs.get("now") or datetime.now(UTC)
        owner = kwargs["owner"]
        config = kwargs["config"]
        svc, session = await self._prepare_session(
            owner=owner,
            config=config,
            broker_account_id=kwargs["broker_account_id"],
            qualification_id=kwargs["qualification_id"],
            evidence_fingerprint=kwargs["evidence_fingerprint"],
            strategy_db_id=kwargs.get("strategy_db_id"),
            external_account_id=kwargs["external_account_id"],
            now=now,
        )
        fake = FakeExecutionAdapter()
        runner = PaperSessionRunner(
            self.db,
            bar_source=kwargs["bar_source"],
            strategy=FixedDecisionStrategy(
                [pilot_enter_limit(config.symbol)],
                strategy_id=config.strategy_id,
                version=config.strategy_version,
            ),
            proposal_service=self._pipeline(fake),
            authorization=svc.authorization,
            paper_execute_enabled=True,
            worker_id="pilot-sim-pf",
        )
        result = await runner.run_once(session.id, now=now)
        if not result.submitted:
            return ScenarioResult(name="partial_fill", ok=False, detail="submit failed")
        broker_id = next(iter(fake.broker_orders))
        fake.add_fill(broker_id, fill_id="pf1", qty=Decimal("0.5"), price=Decimal("50"))
        snap = await fake.get_order_by_id(broker_id)
        return ScenarioResult(
            name="partial_fill",
            ok=snap.get("status") == "partially_filled",
            detail=f"status={snap.get('status')}",
            fake_post_count=fake.post_count,
            submitted=True,
        )

    async def run_cancellation(self, **kwargs: Any) -> ScenarioResult:
        now = kwargs.get("now") or datetime.now(UTC)
        owner = kwargs["owner"]
        config = kwargs["config"]
        svc, session = await self._prepare_session(
            owner=owner,
            config=config,
            broker_account_id=kwargs["broker_account_id"],
            qualification_id=kwargs["qualification_id"],
            evidence_fingerprint=kwargs["evidence_fingerprint"],
            strategy_db_id=kwargs.get("strategy_db_id"),
            external_account_id=kwargs["external_account_id"],
            now=now,
        )
        fake = FakeExecutionAdapter()
        runner = PaperSessionRunner(
            self.db,
            bar_source=kwargs["bar_source"],
            strategy=FixedDecisionStrategy(
                [pilot_enter_limit(config.symbol)],
                strategy_id=config.strategy_id,
                version=config.strategy_version,
            ),
            proposal_service=self._pipeline(fake),
            authorization=svc.authorization,
            paper_execute_enabled=True,
            worker_id="pilot-sim-cx",
        )
        result = await runner.run_once(session.id, now=now)
        broker_id = next(iter(fake.broker_orders))
        cancelled = await fake.request_paper_cancel(broker_id)
        # Account-scoped: only this order id
        return ScenarioResult(
            name="cancellation",
            ok=result.submitted
            and cancelled.get("status") == "canceled"
            and fake.cancel_count == 1,
            detail=f"cancel_status={cancelled.get('status')}",
            fake_post_count=fake.post_count,
            submitted=result.submitted,
            extras={"cancel_count": fake.cancel_count, "broker_order_id": broker_id},
        )

    async def run_duplicate_and_concurrent(self, **kwargs: Any) -> ScenarioResult:
        now = kwargs.get("now") or datetime.now(UTC)
        owner = kwargs["owner"]
        config = kwargs["config"]
        svc, session = await self._prepare_session(
            owner=owner,
            config=config,
            broker_account_id=kwargs["broker_account_id"],
            qualification_id=kwargs["qualification_id"],
            evidence_fingerprint=kwargs["evidence_fingerprint"],
            strategy_db_id=kwargs.get("strategy_db_id"),
            external_account_id=kwargs["external_account_id"],
            now=now,
        )
        fake = FakeExecutionAdapter()
        pipeline = self._pipeline(fake)
        strategy = FixedDecisionStrategy(
            [pilot_enter_limit(config.symbol), pilot_enter_limit(config.symbol)],
            strategy_id=config.strategy_id,
            version=config.strategy_version,
        )
        runner = PaperSessionRunner(
            self.db,
            bar_source=kwargs["bar_source"],
            strategy=strategy,
            proposal_service=pipeline,
            authorization=svc.authorization,
            paper_execute_enabled=True,
            max_outstanding_orders=1,
            worker_id="pilot-sim-dup",
        )
        r1 = await runner.run_once(session.id, now=now)
        second_detail: str | list[str] = []
        r2_submitted = False
        try:
            r2 = await runner.run_once(session.id, now=now)
            r2_submitted = r2.submitted
            second_detail = r2.warnings
        except PaperSessionError as exc:
            # max_orders_per_session == 1 also enforces the one-order pilot limit
            second_detail = [exc.code]
            r2_submitted = False
        ok = r1.submitted and (not r2_submitted) and fake.post_count == 1
        return ScenarioResult(
            name="duplicate_and_one_order_max",
            ok=ok,
            detail=f"r1={r1.submitted} r2={second_detail} posts={fake.post_count}",
            fake_post_count=fake.post_count,
            submitted=r1.submitted,
            extras={"second_warnings": second_detail},
        )

    async def run_revoked_consent(self, **kwargs: Any) -> ScenarioResult:
        now = kwargs.get("now") or datetime.now(UTC)
        owner = kwargs["owner"]
        config = kwargs["config"]
        svc, session = await self._prepare_session(
            owner=owner,
            config=config,
            broker_account_id=kwargs["broker_account_id"],
            qualification_id=kwargs["qualification_id"],
            evidence_fingerprint=kwargs["evidence_fingerprint"],
            strategy_db_id=kwargs.get("strategy_db_id"),
            external_account_id=kwargs["external_account_id"],
            now=now,
        )
        svc.revoke_execution_consent(session.id, owner=owner, reason="pilot_test")
        fake = FakeExecutionAdapter()
        runner = PaperSessionRunner(
            self.db,
            bar_source=kwargs["bar_source"],
            strategy=FixedDecisionStrategy(
                [pilot_enter_limit(config.symbol)],
                strategy_id=config.strategy_id,
                version=config.strategy_version,
            ),
            proposal_service=self._pipeline(fake),
            authorization=svc.authorization,
            paper_execute_enabled=True,
            worker_id="pilot-sim-rev",
        )
        code = None
        try:
            await runner.run_once(session.id, now=now)
        except ConsentError as exc:
            code = exc.code
        return ScenarioResult(
            name="revoked_consent",
            ok=code == "consent_revoked" and fake.post_count == 0,
            detail=f"code={code}",
            fake_post_count=fake.post_count,
        )

    async def run_expired_consent(self, **kwargs: Any) -> ScenarioResult:
        now = kwargs.get("now") or datetime.now(UTC)
        owner = kwargs["owner"]
        config = kwargs["config"]
        past = now - timedelta(hours=1)
        # Temporarily set source
        self.broker_source = StaticBrokerSnapshotSource(
            external_account_id=kwargs["external_account_id"],
            paper_verified=True,
            buying_power="100000",
            paper_base_url="https://paper-api.alpaca.markets",
        )
        svc = PaperSessionService(
            self.db,
            settings=self.settings,
            allow_paper_execute=True,
            broker_source=self.broker_source,
        )
        session = svc.create_session(
            owner=owner,
            engine_strategy_id=kwargs["config"].strategy_id,
            strategy_version=config.strategy_version,
            parameter_hash=configuration_hash(config.parameters),
            parameters=dict(config.parameters),
            qualification_approval_id=kwargs["qualification_id"],
            evidence_fingerprint=kwargs["evidence_fingerprint"],
            broker_account_id=kwargs["broker_account_id"],
            instrument=config.symbol,
            timeframe=config.timeframe,
            risk_limits=config.to_session_risk_limits(),
            strategy_db_id=kwargs.get("strategy_db_id"),
            execution_mode=PaperSessionExecutionMode.PAPER_EXECUTE,
            max_orders_per_session=1,
        )
        auth = svc.grant_execution_consent(
            session.id, owner=owner, expires_in_seconds=1, now=past
        )
        auth.expires_at = past + timedelta(seconds=1)
        self.db.flush()
        await svc.activate(session.id, owner=owner, now=past + timedelta(milliseconds=500))
        # Advance clock past expiry for submission
        fake = FakeExecutionAdapter()
        runner = PaperSessionRunner(
            self.db,
            bar_source=kwargs["bar_source"],
            strategy=FixedDecisionStrategy(
                [pilot_enter_limit(config.symbol)],
                strategy_id=config.strategy_id,
                version=config.strategy_version,
            ),
            proposal_service=self._pipeline(fake),
            authorization=svc.authorization,
            paper_execute_enabled=True,
            worker_id="pilot-sim-exp",
        )
        code = None
        try:
            await runner.run_once(session.id, now=now)
        except ConsentError as exc:
            code = exc.code
        return ScenarioResult(
            name="expired_consent",
            ok=code == "consent_expired" and fake.post_count == 0,
            detail=f"code={code}",
            fake_post_count=fake.post_count,
        )

    async def kill_switch_rehearsal(
        self,
        *,
        owner: AuthenticatedOwner,
        config: PilotConfig,
        broker_account_id: uuid.UUID,
        qualification_id: uuid.UUID,
        evidence_fingerprint: str,
        strategy_db_id: uuid.UUID | None,
        external_account_id: str,
        bar_source: SessionBarSource,
        now: datetime | None = None,
    ) -> KillSwitchRehearsalResult:
        """Simulated kill-switch: submit once, kill, verify no further submits."""
        now = now or datetime.now(UTC)
        notes = [
            "Emergency kill stops future submissions.",
            "Does NOT guarantee cancellation of already accepted orders.",
            "Does NOT liquidate positions.",
        ]
        svc, session = await self._prepare_session(
            owner=owner,
            config=config,
            broker_account_id=broker_account_id,
            qualification_id=qualification_id,
            evidence_fingerprint=evidence_fingerprint,
            strategy_db_id=strategy_db_id,
            external_account_id=external_account_id,
            now=now,
        )
        fake = FakeExecutionAdapter()
        runner = PaperSessionRunner(
            self.db,
            bar_source=bar_source,
            strategy=FixedDecisionStrategy(
                [pilot_enter_limit(config.symbol), pilot_enter_limit(config.symbol)],
                strategy_id=config.strategy_id,
                version=config.strategy_version,
            ),
            proposal_service=self._pipeline(fake),
            authorization=svc.authorization,
            paper_execute_enabled=True,
            worker_id="pilot-kill",
        )
        first = await runner.run_once(session.id, now=now)
        kill = svc.emergency_kill(session.id, owner=owner, reason="pilot_kill_rehearsal")
        # Attempt another cycle — session stopped / consent revoked
        second = await runner.run_once(session.id, now=now)
        additional_blocked = second.processed is False or second.submitted is False
        self.db.refresh(session)
        ok = (
            first.submitted
            and kill["further_submissions_disabled"] is True
            and kill["orders_cancelled"] is False
            and kill["positions_liquidated"] is False
            and session.session_state == PaperSessionState.STOPPED
            and fake.post_count == 1
            and additional_blocked
        )
        return KillSwitchRehearsalResult(
            ok=ok,
            session_state=session.session_state.value,
            further_submissions_disabled=bool(kill["further_submissions_disabled"]),
            consent_revoked=bool(kill.get("execution_consent_revoked")),
            orders_cancelled_claimed=bool(kill["orders_cancelled"]),
            positions_liquidated_claimed=bool(kill["positions_liquidated"]),
            additional_submits_blocked=additional_blocked,
            fake_post_count=fake.post_count,
            notes=notes,
        )


def assert_preparation_environment_safe(settings: Settings | None = None) -> None:
    """Ensure deployment defaults remain safe outside simulated harness Settings."""
    assert_deployment_execute_disabled(settings)
