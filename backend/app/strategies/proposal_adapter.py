"""Convert StrategyDecision → CreateTradeProposalInput (safety pipeline entry).

Strategies never create broker orders. All actionable decisions enter the
existing Trade Proposal → Risk → Validator → Router path when executed
in paper/live-capable environments. Backtests simulate the same shape
offline without broker submission.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from app.models.enums import ProposalSource
from app.strategies.decision import DecisionAction, StrategyDecision
from app.strategies.errors import StrategyDecisionError
from app.trading.proposals.schemas import CreateTradeProposalInput


class StrategyProposalAdapter:
    """Maps approved StrategyDecision objects into Trade Proposal inputs."""

    def to_proposal_input(
        self,
        decision: StrategyDecision,
        *,
        broker_account_id: uuid.UUID,
        strategy_db_id: uuid.UUID | None = None,
        quantity: Decimal | None = None,
        signal_reference: str | None = None,
        idempotency_key: str | None = None,
        metadata: dict[str, Any] | None = None,
        strategy_id: str | None = None,
        strategy_version: str | None = None,
    ) -> CreateTradeProposalInput:
        if not decision.is_actionable:
            raise StrategyDecisionError(
                "NO_ACTION cannot become a trade proposal",
                code="no_action",
            )
        assert decision.symbol is not None
        assert decision.asset_class is not None
        assert decision.side is not None

        qty = quantity if quantity is not None else decision.quantity
        if qty is None or qty <= 0:
            raise StrategyDecisionError(
                "Actionable decision requires a positive quantity",
                code="missing_quantity",
            )

        meta: dict[str, Any] = {
            "decision_action": decision.action.value,
            "rationale_code": decision.rationale_code,
            "rationale": decision.rationale,
            "signal_metadata": dict(decision.signal_metadata),
        }
        if strategy_id is not None:
            meta["strategy_engine_id"] = strategy_id
        if strategy_version is not None:
            meta["strategy_engine_version"] = strategy_version
        if metadata:
            meta.update(metadata)

        return CreateTradeProposalInput(
            broker_account_id=broker_account_id,
            strategy_id=strategy_db_id,
            source=ProposalSource.STRATEGY,
            symbol=decision.symbol,
            asset_class=decision.asset_class,
            side=decision.side,
            order_type=decision.order_type,
            quantity=qty,
            limit_price=decision.limit_price,
            stop_price=decision.stop_price,
            stop_loss_price=decision.stop_loss_price,
            take_profit_price=decision.take_profit_price,
            time_in_force=decision.time_in_force,
            signal_reference=signal_reference or decision.rationale_code,
            idempotency_key=idempotency_key,
            metadata=meta,
        )

    @staticmethod
    def implied_side(action: DecisionAction):
        from app.models.enums import TradeSide
        from app.strategies.decision import _default_side

        if action == DecisionAction.NO_ACTION:
            raise StrategyDecisionError("NO_ACTION has no side", code="no_action")
        return _default_side(action)
