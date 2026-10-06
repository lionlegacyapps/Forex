"""Deterministic Risk Engine V1 — no AI, fail-closed.

Consumes paper execution accounting (daily PnL, positions, simulation prices).
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.market_data.errors import MarketDataError
from app.market_data.service import MarketDataService
from app.models.broker_account import BrokerAccount
from app.models.enums import PositionStatus, StrategyStatus, TradingMode
from app.models.position import Position
from app.models.strategy import Strategy
from app.models.strategy_account_assignment import StrategyAccountAssignment
from app.models.trade_proposal import TradeProposal
from app.trading.execution.daily_pnl import DailyPnlService
from app.trading.execution.exposure import ExposureService
from app.trading.execution.market_data import SimulationMarketData, default_simulation_market_data
from app.trading.risk import codes
from app.trading.risk.resolver import EffectiveRiskLimits, RiskPolicyResolver
from app.trading.risk.results import CheckStatus, RiskCheckResult, RiskDecision


class RiskEngine:
    """Evaluate whether a trade proposal is allowed under current risk rules."""

    def __init__(
        self,
        session: Session,
        *,
        policy_resolver: RiskPolicyResolver | None = None,
        market_data: SimulationMarketData | None = None,
        market_data_service: MarketDataService | None = None,
        daily_pnl: DailyPnlService | None = None,
        exposure: ExposureService | None = None,
    ) -> None:
        self._session = session
        self._resolver = policy_resolver or RiskPolicyResolver(session)
        self._market = market_data or default_simulation_market_data
        self._mds = market_data_service
        tz = get_settings().trading_day_timezone
        self._daily_pnl = daily_pnl or DailyPnlService(session, trading_timezone=tz)
        self._exposure = exposure or ExposureService(
            session,
            market_data=self._market,
            market_data_service=self._mds,
        )

    def evaluate(self, proposal: TradeProposal) -> RiskDecision:
        checks: list[RiskCheckResult] = []

        account = self._session.get(BrokerAccount, proposal.broker_account_id)
        if account is None:
            check = RiskCheckResult(
                name="broker_account_enabled",
                status=CheckStatus.FAILED,
                reason_code=codes.BROKER_ACCOUNT_NOT_FOUND,
                message="Broker account does not exist",
            )
            checks.append(check)
            return RiskDecision.reject(
                reason_code=codes.BROKER_ACCOUNT_NOT_FOUND,
                message=check.message,
                checks=checks,
            )

        if not account.is_enabled:
            check = RiskCheckResult(
                name="broker_account_enabled",
                status=CheckStatus.FAILED,
                reason_code=codes.BROKER_ACCOUNT_DISABLED,
                message="Broker account is disabled",
            )
            checks.append(check)
            return RiskDecision.reject(
                reason_code=codes.BROKER_ACCOUNT_DISABLED,
                message=check.message,
                checks=checks,
            )
        checks.append(
            RiskCheckResult(
                name="broker_account_enabled",
                status=CheckStatus.PASSED,
                message="Broker account is enabled",
            )
        )

        if account.trading_mode != TradingMode.PAPER:
            check = RiskCheckResult(
                name="paper_mode",
                status=CheckStatus.FAILED,
                reason_code=codes.LIVE_TRADING_NOT_ALLOWED,
                message="Only PAPER trading mode is permitted",
            )
            checks.append(check)
            return RiskDecision.reject(
                reason_code=codes.LIVE_TRADING_NOT_ALLOWED,
                message=check.message,
                checks=checks,
            )
        checks.append(
            RiskCheckResult(
                name="paper_mode",
                status=CheckStatus.PASSED,
                message="Account trading mode is paper",
            )
        )

        assignment: StrategyAccountAssignment | None = None

        if proposal.strategy_id is not None:
            strategy = self._session.get(Strategy, proposal.strategy_id)
            if strategy is None:
                check = RiskCheckResult(
                    name="strategy_assignment",
                    status=CheckStatus.FAILED,
                    reason_code=codes.STRATEGY_NOT_FOUND,
                    message="Strategy does not exist",
                )
                checks.append(check)
                return RiskDecision.reject(
                    reason_code=codes.STRATEGY_NOT_FOUND,
                    message=check.message,
                    checks=checks,
                )
            if strategy.status == StrategyStatus.PAUSED:
                check = RiskCheckResult(
                    name="strategy_assignment",
                    status=CheckStatus.FAILED,
                    reason_code=codes.STRATEGY_PAUSED,
                    message="Strategy is paused",
                )
                checks.append(check)
                return RiskDecision.reject(
                    reason_code=codes.STRATEGY_PAUSED,
                    message=check.message,
                    checks=checks,
                )
            if strategy.status == StrategyStatus.RETIRED:
                check = RiskCheckResult(
                    name="strategy_assignment",
                    status=CheckStatus.FAILED,
                    reason_code=codes.STRATEGY_RETIRED,
                    message="Strategy is retired",
                )
                checks.append(check)
                return RiskDecision.reject(
                    reason_code=codes.STRATEGY_RETIRED,
                    message=check.message,
                    checks=checks,
                )

            assignment = self._session.scalars(
                select(StrategyAccountAssignment).where(
                    StrategyAccountAssignment.strategy_id == proposal.strategy_id,
                    StrategyAccountAssignment.broker_account_id == proposal.broker_account_id,
                )
            ).first()
            if assignment is None:
                check = RiskCheckResult(
                    name="strategy_assignment",
                    status=CheckStatus.FAILED,
                    reason_code=codes.STRATEGY_NOT_ASSIGNED,
                    message="Strategy is not assigned to the selected broker account",
                )
                checks.append(check)
                return RiskDecision.reject(
                    reason_code=codes.STRATEGY_NOT_ASSIGNED,
                    message=check.message,
                    checks=checks,
                )
            if not assignment.is_enabled:
                check = RiskCheckResult(
                    name="strategy_assignment",
                    status=CheckStatus.FAILED,
                    reason_code=codes.STRATEGY_ASSIGNMENT_DISABLED,
                    message="Strategy account assignment is disabled",
                )
                checks.append(check)
                return RiskDecision.reject(
                    reason_code=codes.STRATEGY_ASSIGNMENT_DISABLED,
                    message=check.message,
                    checks=checks,
                )
            if assignment.trading_mode != TradingMode.PAPER:
                check = RiskCheckResult(
                    name="strategy_assignment",
                    status=CheckStatus.FAILED,
                    reason_code=codes.STRATEGY_ASSIGNMENT_LIVE_NOT_ALLOWED,
                    message="Strategy assignment trading mode must be paper",
                )
                checks.append(check)
                return RiskDecision.reject(
                    reason_code=codes.STRATEGY_ASSIGNMENT_LIVE_NOT_ALLOWED,
                    message=check.message,
                    checks=checks,
                )
            checks.append(
                RiskCheckResult(
                    name="strategy_assignment",
                    status=CheckStatus.PASSED,
                    message="Strategy assignment is enabled and paper",
                )
            )
        else:
            checks.append(
                RiskCheckResult(
                    name="strategy_assignment",
                    status=CheckStatus.PASSED,
                    message="No strategy on proposal; assignment check skipped",
                )
            )

        limits = self._resolver.resolve(
            broker_account_id=proposal.broker_account_id,
            strategy_id=proposal.strategy_id,
            assignment=assignment,
        )

        if limits.require_stop_loss and proposal.stop_loss_price is None:
            check = RiskCheckResult(
                name="stop_loss_required",
                status=CheckStatus.FAILED,
                reason_code=codes.STOP_LOSS_REQUIRED,
                message="Applicable risk policy requires stop_loss_price",
            )
            checks.append(check)
            return RiskDecision.reject(
                reason_code=codes.STOP_LOSS_REQUIRED,
                message=check.message,
                checks=checks,
            )
        checks.append(
            RiskCheckResult(
                name="stop_loss_required",
                status=CheckStatus.PASSED,
                message=(
                    "stop_loss_price present"
                    if limits.require_stop_loss
                    else "stop_loss not required by effective policy"
                ),
            )
        )

        if proposal.quantity is None or proposal.quantity <= 0:
            check = RiskCheckResult(
                name="quantity",
                status=CheckStatus.FAILED,
                reason_code=codes.QUANTITY_INVALID,
                message="Quantity must be greater than zero",
            )
            checks.append(check)
            return RiskDecision.reject(
                reason_code=codes.QUANTITY_INVALID,
                message=check.message,
                checks=checks,
            )
        checks.append(
            RiskCheckResult(
                name="quantity",
                status=CheckStatus.PASSED,
                message="Quantity is positive",
            )
        )

        size_check = self._check_max_position_size(proposal, limits)
        checks.append(size_check)
        if size_check.status == CheckStatus.FAILED:
            return RiskDecision.reject(
                reason_code=size_check.reason_code or codes.MAX_POSITION_SIZE_EXCEEDED,
                message=size_check.message,
                checks=checks,
            )

        order_value_check = self._check_max_order_value(proposal, limits)
        checks.append(order_value_check)
        if order_value_check.status == CheckStatus.FAILED:
            return RiskDecision.reject(
                reason_code=order_value_check.reason_code or codes.MAX_ORDER_VALUE_EXCEEDED,
                message=order_value_check.message,
                checks=checks,
            )

        daily_check = self._check_daily_loss(proposal, limits)
        checks.append(daily_check)
        if daily_check.status == CheckStatus.FAILED:
            return RiskDecision.reject(
                reason_code=daily_check.reason_code or codes.DAILY_LOSS_LIMIT_REACHED,
                message=daily_check.message,
                checks=checks,
            )

        open_check = self._check_open_positions(proposal, limits)
        checks.append(open_check)
        if open_check.status == CheckStatus.FAILED:
            return RiskDecision.reject(
                reason_code=open_check.reason_code or codes.MAX_OPEN_POSITIONS_EXCEEDED,
                message=open_check.message,
                checks=checks,
            )

        exposure_check = self._check_max_total_exposure(proposal, limits)
        checks.append(exposure_check)
        if exposure_check.status == CheckStatus.FAILED:
            return RiskDecision.reject(
                reason_code=exposure_check.reason_code or codes.MAX_TOTAL_EXPOSURE_EXCEEDED,
                message=exposure_check.message,
                checks=checks,
            )

        dup_check = self._check_duplicate(proposal)
        checks.append(dup_check)
        if dup_check.status == CheckStatus.FAILED:
            return RiskDecision.reject(
                reason_code=dup_check.reason_code or codes.DUPLICATE_PROPOSAL,
                message=dup_check.message,
                checks=checks,
            )

        return RiskDecision.approve(checks=checks)

    def _check_max_position_size(
        self,
        proposal: TradeProposal,
        limits: EffectiveRiskLimits,
    ) -> RiskCheckResult:
        if limits.max_position_size is None:
            return RiskCheckResult(
                name="max_position_size",
                status=CheckStatus.PASSED,
                message="No max_position_size configured",
            )
        if proposal.quantity > limits.max_position_size:
            return RiskCheckResult(
                name="max_position_size",
                status=CheckStatus.FAILED,
                reason_code=codes.MAX_POSITION_SIZE_EXCEEDED,
                message=(
                    f"Quantity {proposal.quantity} exceeds max_position_size "
                    f"{limits.max_position_size}"
                ),
            )
        return RiskCheckResult(
            name="max_position_size",
            status=CheckStatus.PASSED,
            message="Quantity within max_position_size",
        )

    def _deterministic_order_price(
        self, proposal: TradeProposal
    ) -> tuple[Decimal | None, str | None]:
        """Return (price, error_code). Prefer limit, then MarketDataService, then sim board."""
        if proposal.limit_price is not None:
            return proposal.limit_price, None
        if self._mds is not None:
            try:
                ref = self._mds.sync_reference_price(proposal.symbol)
                return ref.price, None
            except MarketDataError as exc:
                return None, exc.code
        price = self._market.get_price(proposal.symbol)
        if price is None:
            return None, codes.NOT_EVALUATED_MARKET_PRICE_REQUIRED
        return price, None

    def _check_max_order_value(
        self,
        proposal: TradeProposal,
        limits: EffectiveRiskLimits,
    ) -> RiskCheckResult:
        if limits.max_order_value is None:
            return RiskCheckResult(
                name="max_order_value",
                status=CheckStatus.PASSED,
                message="No max_order_value configured",
            )

        price, err = self._deterministic_order_price(proposal)
        if price is None:
            # Required financial limit cannot be evaluated → fail closed.
            code = err or codes.NOT_EVALUATED_MARKET_PRICE_REQUIRED
            return RiskCheckResult(
                name="max_order_value",
                status=CheckStatus.FAILED,
                reason_code=code,
                message=(
                    "max_order_value configured but no reliable price available; "
                    "fail-closed (not treated as PASS)"
                ),
            )

        order_value = proposal.quantity * price
        if order_value > limits.max_order_value:
            return RiskCheckResult(
                name="max_order_value",
                status=CheckStatus.FAILED,
                reason_code=codes.MAX_ORDER_VALUE_EXCEEDED,
                message=(
                    f"Order value {order_value} exceeds max_order_value "
                    f"{limits.max_order_value}"
                ),
            )
        return RiskCheckResult(
            name="max_order_value",
            status=CheckStatus.PASSED,
            message=f"Order value {order_value} within limit",
        )

    def _check_daily_loss(
        self,
        proposal: TradeProposal,
        limits: EffectiveRiskLimits,
    ) -> RiskCheckResult:
        if limits.max_daily_loss is None:
            return RiskCheckResult(
                name="daily_loss_limit",
                status=CheckStatus.PASSED,
                message="No daily loss limit configured",
            )

        pnl = self._daily_pnl.realized_pnl(
            broker_account_id=proposal.broker_account_id,
            strategy_id=proposal.strategy_id,
        )
        # Loss reached when realized PnL is <= -max_daily_loss.
        if pnl.realized_pnl <= -limits.max_daily_loss:
            return RiskCheckResult(
                name="daily_loss_limit",
                status=CheckStatus.FAILED,
                reason_code=codes.DAILY_LOSS_LIMIT_REACHED,
                message=(
                    f"Daily realized PnL {pnl.realized_pnl} reached/exceeded loss limit "
                    f"{limits.max_daily_loss} ({pnl.timezone} day {pnl.trading_day})"
                ),
            )
        return RiskCheckResult(
            name="daily_loss_limit",
            status=CheckStatus.PASSED,
            message=(
                f"Daily realized PnL {pnl.realized_pnl} within loss limit "
                f"{limits.max_daily_loss}"
            ),
        )

    def _find_open_for_proposal(self, proposal: TradeProposal) -> Position | None:
        stmt = select(Position).where(
            Position.broker_account_id == proposal.broker_account_id,
            Position.symbol == proposal.symbol,
            Position.asset_class == proposal.asset_class,
            Position.status == PositionStatus.OPEN,
        )
        if proposal.strategy_id is None:
            stmt = stmt.where(Position.strategy_id.is_(None))
        else:
            stmt = stmt.where(Position.strategy_id == proposal.strategy_id)
        return self._session.scalars(stmt).first()

    def _check_open_positions(
        self,
        proposal: TradeProposal,
        limits: EffectiveRiskLimits,
    ) -> RiskCheckResult:
        if limits.max_open_positions is None:
            return RiskCheckResult(
                name="open_position_limit",
                status=CheckStatus.PASSED,
                message="No max_open_positions configured",
            )

        stmt = select(func.count()).select_from(Position).where(
            Position.broker_account_id == proposal.broker_account_id,
            Position.status == PositionStatus.OPEN,
        )
        if proposal.strategy_id is not None:
            stmt = stmt.where(Position.strategy_id == proposal.strategy_id)

        open_count = int(self._session.scalar(stmt) or 0)
        existing = self._find_open_for_proposal(proposal)
        # Adding to an existing open position does not consume a new slot.
        if existing is not None:
            return RiskCheckResult(
                name="open_position_limit",
                status=CheckStatus.PASSED,
                message=(
                    f"Proposal adds to existing open position; count {open_count} unchanged"
                ),
            )

        if open_count >= limits.max_open_positions:
            return RiskCheckResult(
                name="open_position_limit",
                status=CheckStatus.FAILED,
                reason_code=codes.MAX_OPEN_POSITIONS_EXCEEDED,
                message=(
                    f"Open positions {open_count} already at/exceed "
                    f"max_open_positions {limits.max_open_positions}"
                ),
            )
        return RiskCheckResult(
            name="open_position_limit",
            status=CheckStatus.PASSED,
            message=f"Open positions {open_count} within limit for new position",
        )

    def _check_max_total_exposure(
        self,
        proposal: TradeProposal,
        limits: EffectiveRiskLimits,
    ) -> RiskCheckResult:
        if limits.max_total_exposure is None:
            return RiskCheckResult(
                name="max_total_exposure",
                status=CheckStatus.PASSED,
                message="No max_total_exposure configured",
            )

        current = self._exposure.account_exposure(
            proposal.broker_account_id,
            strategy_id=proposal.strategy_id,
        )
        incremental = self._exposure.proposed_incremental_notional(
            symbol=proposal.symbol,
            quantity=proposal.quantity,
        )
        if not current.complete or incremental is None:
            return RiskCheckResult(
                name="max_total_exposure",
                status=CheckStatus.FAILED,
                reason_code=current.reason_code or codes.NOT_EVALUATED_PRICE_REQUIRED,
                message=(
                    "max_total_exposure cannot be evaluated without reliable prices; "
                    "fail-closed"
                ),
            )

        projected = current.gross_notional + incremental
        if projected > limits.max_total_exposure:
            return RiskCheckResult(
                name="max_total_exposure",
                status=CheckStatus.FAILED,
                reason_code=codes.MAX_TOTAL_EXPOSURE_EXCEEDED,
                message=(
                    f"Projected exposure {projected} exceeds max_total_exposure "
                    f"{limits.max_total_exposure}"
                ),
            )
        return RiskCheckResult(
            name="max_total_exposure",
            status=CheckStatus.PASSED,
            message=f"Projected exposure {projected} within limit",
        )

    def _check_duplicate(self, proposal: TradeProposal) -> RiskCheckResult:
        metadata = proposal.metadata_ or {}
        key = metadata.get("idempotency_key")
        if not key:
            return RiskCheckResult(
                name="duplicate_proposal",
                status=CheckStatus.PASSED,
                message="No idempotency_key supplied",
            )

        candidates = self._session.scalars(
            select(TradeProposal).where(
                TradeProposal.broker_account_id == proposal.broker_account_id,
                TradeProposal.id != proposal.id,
            )
        ).all()
        active_statuses = {
            "pending",
            "risk_approved",
            "validated",
            "routed",
            "submitted",
        }
        for other in candidates:
            other_meta = other.metadata_ or {}
            if other_meta.get("idempotency_key") != key:
                continue
            if other.status.value in active_statuses:
                return RiskCheckResult(
                    name="duplicate_proposal",
                    status=CheckStatus.FAILED,
                    reason_code=codes.DUPLICATE_PROPOSAL,
                    message=f"Active proposal {other.id} already uses idempotency_key",
                )
        return RiskCheckResult(
            name="duplicate_proposal",
            status=CheckStatus.PASSED,
            message="No active duplicate idempotency_key",
        )
