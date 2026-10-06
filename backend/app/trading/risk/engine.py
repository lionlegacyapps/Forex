"""Deterministic Risk Engine V1 — no AI, fail-closed."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.broker_account import BrokerAccount
from app.models.enums import PositionStatus, StrategyStatus, TradingMode
from app.models.position import Position
from app.models.strategy import Strategy
from app.models.strategy_account_assignment import StrategyAccountAssignment
from app.models.trade_proposal import TradeProposal
from app.trading.risk import codes
from app.trading.risk.resolver import EffectiveRiskLimits, RiskPolicyResolver
from app.trading.risk.results import CheckStatus, RiskCheckResult, RiskDecision


class RiskEngine:
    """Evaluate whether a trade proposal is allowed under current risk rules.

    Unexpected exceptions are converted to a rejected decision by callers;
    this class itself never returns ``approved=True`` after an internal failure.
    """

    def __init__(self, session: Session, *, policy_resolver: RiskPolicyResolver | None = None) -> None:
        self._session = session
        self._resolver = policy_resolver or RiskPolicyResolver(session)

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

        # 1. Broker account enabled
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

        # 2. Paper mode only for this milestone
        if account.trading_mode != TradingMode.PAPER:
            check = RiskCheckResult(
                name="paper_mode",
                status=CheckStatus.FAILED,
                reason_code=codes.LIVE_TRADING_NOT_ALLOWED,
                message="Only PAPER trading mode is permitted in Safety Pipeline V1",
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
        strategy: Strategy | None = None

        # 3. Strategy assignment (when strategy_id present)
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

        # 4. Stop loss requirement
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

        # 5. Quantity
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

        # 6. Max position size (quantity-based)
        size_check = self._check_max_position_size(proposal, limits)
        checks.append(size_check)
        if size_check.status == CheckStatus.FAILED:
            return RiskDecision.reject(
                reason_code=size_check.reason_code or codes.MAX_POSITION_SIZE_EXCEEDED,
                message=size_check.message,
                checks=checks,
            )

        # 7. Max order value (only when deterministic price available)
        order_value_check = self._check_max_order_value(proposal, limits)
        checks.append(order_value_check)
        if order_value_check.status == CheckStatus.FAILED:
            return RiskDecision.reject(
                reason_code=order_value_check.reason_code or codes.MAX_ORDER_VALUE_EXCEEDED,
                message=order_value_check.message,
                checks=checks,
            )

        # 8. Daily loss limit — architecture present; unevaluated without reliable PnL window
        daily_check = self._check_daily_loss(proposal, limits)
        checks.append(daily_check)
        if daily_check.status == CheckStatus.FAILED:
            return RiskDecision.reject(
                reason_code=daily_check.reason_code or codes.MAX_DAILY_LOSS_EXCEEDED,
                message=daily_check.message,
                checks=checks,
            )

        # 9. Open position limit
        open_check = self._check_open_positions(proposal, limits)
        checks.append(open_check)
        if open_check.status == CheckStatus.FAILED:
            return RiskDecision.reject(
                reason_code=open_check.reason_code or codes.MAX_OPEN_POSITIONS_EXCEEDED,
                message=open_check.message,
                checks=checks,
            )

        # 10. Duplicate / idempotency (application-level)
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

        price = self._deterministic_order_price(proposal)
        if price is None:
            # Do not fabricate market price; record unevaluated explicitly.
            # PAPER V1: do not auto-approve a live-capable path on missing data,
            # but also do not invent a rejection that blocks all market orders
            # when only a limit is configured — record NOT_EVALUATED and continue.
            # Fail-closed for LIVE is enforced separately (LIVE rejected).
            return RiskCheckResult(
                name="max_order_value",
                status=CheckStatus.NOT_EVALUATED_MARKET_PRICE_REQUIRED,
                reason_code=codes.NOT_EVALUATED_MARKET_PRICE_REQUIRED,
                message=(
                    "max_order_value configured but no deterministic proposal price "
                    "available; market price not fabricated"
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

    @staticmethod
    def _deterministic_order_price(proposal: TradeProposal) -> Decimal | None:
        """Price usable without market data (limit or stop-limit limit)."""
        if proposal.limit_price is not None:
            return proposal.limit_price
        return None

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

        # Reliable intraday realized PnL aggregation is not yet available as a
        # dedicated ledger. Summing position.realized_pnl without a trading-day
        # window would pretend accuracy. Record NOT_EVALUATED explicitly.
        _ = proposal  # reserved for future account-scoped day window
        _ = datetime.now(timezone.utc)
        return RiskCheckResult(
            name="daily_loss_limit",
            status=CheckStatus.NOT_EVALUATED,
            reason_code=codes.NOT_EVALUATED_PNL_DATA_UNAVAILABLE,
            message=(
                "Daily loss limit configured but reliable same-day realized PnL "
                "data is unavailable; check not evaluated"
            ),
        )

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
        # Reject if adding this proposal's position interest would exceed the cap.
        # Conservative: count current open; if already at/over limit, reject.
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
            message=f"Open positions {open_count} within limit",
        )

    def _check_duplicate(self, proposal: TradeProposal) -> RiskCheckResult:
        """Application-level idempotency via metadata.idempotency_key.

        Schema note: durable uniqueness would require a dedicated
        ``idempotency_key`` column + unique constraint on
        ``(broker_account_id, idempotency_key)``. Until then, this check
        queries JSON metadata for an exact key match among non-terminal
        proposals and never uses weak time-based heuristics.
        """
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
                    message=(
                        f"Active proposal {other.id} already uses idempotency_key"
                    ),
                )
        return RiskCheckResult(
            name="duplicate_proposal",
            status=CheckStatus.PASSED,
            message="No active duplicate idempotency_key",
        )
