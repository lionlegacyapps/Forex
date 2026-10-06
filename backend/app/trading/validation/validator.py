"""Order Validator — structural consistency (not risk policy)."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.broker_account import BrokerAccount
from app.models.enums import OrderType, TimeInForce, TradeProposalStatus, TradeSide, TradingMode
from app.models.trade_proposal import TradeProposal
from app.trading.risk import codes


class ValidationCheck(BaseModel):
    name: str
    passed: bool
    reason_code: str | None = None
    message: str = ""


class ValidationResult(BaseModel):
    valid: bool
    reason_code: str | None = None
    message: str = ""
    checks: list[ValidationCheck] = Field(default_factory=list)

    @classmethod
    def reject(
        cls,
        *,
        reason_code: str,
        message: str,
        checks: list[ValidationCheck] | None = None,
    ) -> ValidationResult:
        return cls(
            valid=False,
            reason_code=reason_code,
            message=message,
            checks=list(checks or []),
        )

    @classmethod
    def ok(
        cls,
        *,
        message: str = "Order structure valid",
        checks: list[ValidationCheck] | None = None,
    ) -> ValidationResult:
        return cls(valid=True, message=message, checks=list(checks or []))


class OrderValidator:
    """Validate that a risk-approved proposal is structurally routable."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def validate(self, proposal: TradeProposal) -> ValidationResult:
        checks: list[ValidationCheck] = []

        # Proposal must be risk-approved and not already past validation.
        if proposal.status != TradeProposalStatus.RISK_APPROVED:
            check = ValidationCheck(
                name="proposal_status",
                passed=False,
                reason_code=codes.PROPOSAL_NOT_RISK_APPROVED,
                message=f"Proposal status must be risk_approved, got {proposal.status.value}",
            )
            checks.append(check)
            return ValidationResult.reject(
                reason_code=codes.PROPOSAL_NOT_RISK_APPROVED,
                message=check.message,
                checks=checks,
            )
        checks.append(
            ValidationCheck(
                name="proposal_status",
                passed=True,
                message="Proposal is risk_approved",
            )
        )

        if proposal.status in {
            TradeProposalStatus.ROUTED,
            TradeProposalStatus.SUBMITTED,
        }:
            check = ValidationCheck(
                name="not_already_routed",
                passed=False,
                reason_code=codes.PROPOSAL_ALREADY_ROUTED,
                message="Proposal has already been routed or submitted",
            )
            checks.append(check)
            return ValidationResult.reject(
                reason_code=codes.PROPOSAL_ALREADY_ROUTED,
                message=check.message,
                checks=checks,
            )

        symbol = (proposal.symbol or "").strip()
        if not symbol:
            check = ValidationCheck(
                name="symbol",
                passed=False,
                reason_code="INVALID_SYMBOL",
                message="Symbol is required",
            )
            checks.append(check)
            return ValidationResult.reject(
                reason_code="INVALID_SYMBOL",
                message=check.message,
                checks=checks,
            )
        checks.append(ValidationCheck(name="symbol", passed=True, message="Symbol present"))

        if proposal.quantity is None or proposal.quantity <= 0:
            check = ValidationCheck(
                name="quantity",
                passed=False,
                reason_code=codes.QUANTITY_INVALID,
                message="Quantity must be > 0",
            )
            checks.append(check)
            return ValidationResult.reject(
                reason_code=codes.QUANTITY_INVALID,
                message=check.message,
                checks=checks,
            )
        checks.append(ValidationCheck(name="quantity", passed=True, message="Quantity positive"))

        if proposal.side not in {TradeSide.BUY, TradeSide.SELL}:
            check = ValidationCheck(
                name="side",
                passed=False,
                reason_code="INVALID_SIDE",
                message="Side must be buy or sell",
            )
            checks.append(check)
            return ValidationResult.reject(
                reason_code="INVALID_SIDE",
                message=check.message,
                checks=checks,
            )
        checks.append(ValidationCheck(name="side", passed=True, message="Side valid"))

        if proposal.order_type not in {
            OrderType.MARKET,
            OrderType.LIMIT,
            OrderType.STOP,
            OrderType.STOP_LIMIT,
        }:
            check = ValidationCheck(
                name="order_type",
                passed=False,
                reason_code="INVALID_ORDER_TYPE",
                message="Order type is not recognized",
            )
            checks.append(check)
            return ValidationResult.reject(
                reason_code="INVALID_ORDER_TYPE",
                message=check.message,
                checks=checks,
            )
        checks.append(
            ValidationCheck(name="order_type", passed=True, message="Order type valid")
        )

        price_check = self._validate_prices(proposal)
        checks.append(price_check)
        if not price_check.passed:
            return ValidationResult.reject(
                reason_code=price_check.reason_code or "INVALID_PRICES",
                message=price_check.message,
                checks=checks,
            )

        if proposal.time_in_force not in {
            TimeInForce.DAY,
            TimeInForce.GTC,
            TimeInForce.IOC,
            TimeInForce.FOK,
        }:
            check = ValidationCheck(
                name="time_in_force",
                passed=False,
                reason_code="INVALID_TIME_IN_FORCE",
                message="time_in_force is invalid",
            )
            checks.append(check)
            return ValidationResult.reject(
                reason_code="INVALID_TIME_IN_FORCE",
                message=check.message,
                checks=checks,
            )
        checks.append(
            ValidationCheck(name="time_in_force", passed=True, message="TIF valid")
        )

        account = self._session.get(BrokerAccount, proposal.broker_account_id)
        if account is None:
            check = ValidationCheck(
                name="broker_account",
                passed=False,
                reason_code=codes.BROKER_ACCOUNT_NOT_FOUND,
                message="Broker account missing",
            )
            checks.append(check)
            return ValidationResult.reject(
                reason_code=codes.BROKER_ACCOUNT_NOT_FOUND,
                message=check.message,
                checks=checks,
            )

        # Paper/live consistency — Safety Pipeline V1 only allows paper.
        if account.trading_mode != TradingMode.PAPER:
            check = ValidationCheck(
                name="paper_live_consistency",
                passed=False,
                reason_code=codes.LIVE_TRADING_NOT_ALLOWED,
                message="Account trading mode is not paper",
            )
            checks.append(check)
            return ValidationResult.reject(
                reason_code=codes.LIVE_TRADING_NOT_ALLOWED,
                message=check.message,
                checks=checks,
            )
        checks.append(
            ValidationCheck(
                name="paper_live_consistency",
                passed=True,
                message="Paper mode consistent",
            )
        )
        checks.append(
            ValidationCheck(
                name="broker_account_match",
                passed=True,
                message="Proposal broker_account_id resolves",
            )
        )

        return ValidationResult.ok(checks=checks)

    @staticmethod
    def _validate_prices(proposal: TradeProposal) -> ValidationCheck:
        if proposal.order_type == OrderType.LIMIT:
            if proposal.limit_price is None or proposal.limit_price < 0:
                return ValidationCheck(
                    name="prices",
                    passed=False,
                    reason_code="LIMIT_PRICE_REQUIRED",
                    message="LIMIT orders require a non-negative limit_price",
                )
        elif proposal.order_type == OrderType.STOP:
            if proposal.stop_price is None or proposal.stop_price < 0:
                return ValidationCheck(
                    name="prices",
                    passed=False,
                    reason_code="STOP_PRICE_REQUIRED",
                    message="STOP orders require a non-negative stop_price",
                )
        elif proposal.order_type == OrderType.STOP_LIMIT:
            if (
                proposal.limit_price is None
                or proposal.stop_price is None
                or proposal.limit_price < 0
                or proposal.stop_price < 0
            ):
                return ValidationCheck(
                    name="prices",
                    passed=False,
                    reason_code="STOP_LIMIT_PRICES_REQUIRED",
                    message="STOP_LIMIT orders require limit_price and stop_price",
                )

        # Guard against nonsensical negatives when present
        for label, value in (
            ("limit_price", proposal.limit_price),
            ("stop_price", proposal.stop_price),
            ("stop_loss_price", proposal.stop_loss_price),
            ("take_profit_price", proposal.take_profit_price),
        ):
            if value is not None and value < Decimal("0"):
                return ValidationCheck(
                    name="prices",
                    passed=False,
                    reason_code="NEGATIVE_PRICE",
                    message=f"{label} must not be negative",
                )

        return ValidationCheck(name="prices", passed=True, message="Price fields consistent")
