"""Deterministic multi-scope risk policy resolution.

Resolution algorithm
--------------------
1. Collect every **enabled** RiskPolicy whose scope matches the proposal:
   - GLOBAL (scope_id IS NULL)
   - BROKER_ACCOUNT (scope_id = broker_account_id)
   - STRATEGY (scope_id = strategy_id) when strategy_id is present
   - STRATEGY_ACCOUNT (scope_id = assignment.id) when an assignment exists

2. Also fold in numeric limits from the strategy↔account assignment row
   (``max_position_size``, ``daily_loss_limit``, ``max_concurrent_positions``).
   These act as additional tightening sources — never as silent weakeners.

3. Merge rules (strictest wins / fail-closed):
   - ``require_stop_loss``: TRUE if **any** applicable enabled policy has it
     TRUE. If no policies exist, default TRUE.
   - Numeric maximums (``max_order_value``, ``max_open_positions``,
     ``max_daily_loss``, ``max_position_size``, ``max_position_value``,
     ``max_total_exposure``, ``max_concurrent_positions``): effective value is
     the **minimum** among all non-null applicable values.
   - A more specific policy may **tighten** a global limit; it must not
     raise an effective maximum above a stricter higher-scope limit because
     the merge always takes the minimum.

4. Disabled policies (``is_enabled = false``) are ignored entirely.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import RiskScopeType
from app.models.risk_policy import RiskPolicy
from app.models.strategy_account_assignment import StrategyAccountAssignment


class EffectiveRiskLimits(BaseModel):
    require_stop_loss: bool = True
    max_order_value: Decimal | None = None
    max_open_positions: int | None = None
    max_daily_loss: Decimal | None = None
    max_position_size: Decimal | None = None
    max_position_value: Decimal | None = None
    max_total_exposure: Decimal | None = None
    max_concurrent_positions: int | None = None
    policy_ids: list[uuid.UUID] = Field(default_factory=list)
    assignment_id: uuid.UUID | None = None


def _min_decimal(current: Decimal | None, candidate: Decimal | None) -> Decimal | None:
    if candidate is None:
        return current
    if current is None:
        return candidate
    return min(current, candidate)


def _min_int(current: int | None, candidate: int | None) -> int | None:
    if candidate is None:
        return current
    if current is None:
        return candidate
    return min(current, candidate)


class RiskPolicyResolver:
    """Resolve effective risk limits for a proposal context."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def resolve(
        self,
        *,
        broker_account_id: uuid.UUID,
        strategy_id: uuid.UUID | None = None,
        assignment: StrategyAccountAssignment | None = None,
    ) -> EffectiveRiskLimits:
        policies = self._load_applicable_policies(
            broker_account_id=broker_account_id,
            strategy_id=strategy_id,
            assignment_id=assignment.id if assignment is not None else None,
        )

        effective = EffectiveRiskLimits(require_stop_loss=True)
        if not policies:
            # Fail-closed default when no policy rows exist.
            effective.require_stop_loss = True
        else:
            effective.require_stop_loss = any(p.require_stop_loss for p in policies)

        for policy in policies:
            effective.policy_ids.append(policy.id)
            effective.max_order_value = _min_decimal(
                effective.max_order_value, policy.max_order_value
            )
            effective.max_open_positions = _min_int(
                effective.max_open_positions, policy.max_open_positions
            )
            effective.max_daily_loss = _min_decimal(
                effective.max_daily_loss, policy.max_daily_loss
            )
            effective.max_position_value = _min_decimal(
                effective.max_position_value, policy.max_position_value
            )
            effective.max_total_exposure = _min_decimal(
                effective.max_total_exposure, policy.max_total_exposure
            )

        if assignment is not None:
            effective.assignment_id = assignment.id
            effective.max_position_size = _min_decimal(
                effective.max_position_size, assignment.max_position_size
            )
            effective.max_daily_loss = _min_decimal(
                effective.max_daily_loss, assignment.daily_loss_limit
            )
            effective.max_concurrent_positions = _min_int(
                effective.max_concurrent_positions, assignment.max_concurrent_positions
            )
            # Treat assignment concurrent-position cap as an open-position limit too.
            effective.max_open_positions = _min_int(
                effective.max_open_positions, assignment.max_concurrent_positions
            )

        return effective

    def _load_applicable_policies(
        self,
        *,
        broker_account_id: uuid.UUID,
        strategy_id: uuid.UUID | None,
        assignment_id: uuid.UUID | None,
    ) -> list[RiskPolicy]:
        stmt = select(RiskPolicy).where(RiskPolicy.is_enabled.is_(True))
        policies = list(self._session.scalars(stmt).all())
        applicable: list[RiskPolicy] = []
        for policy in policies:
            if policy.scope_type == RiskScopeType.GLOBAL and policy.scope_id is None:
                applicable.append(policy)
            elif (
                policy.scope_type == RiskScopeType.BROKER_ACCOUNT
                and policy.scope_id == broker_account_id
            ):
                applicable.append(policy)
            elif (
                strategy_id is not None
                and policy.scope_type == RiskScopeType.STRATEGY
                and policy.scope_id == strategy_id
            ):
                applicable.append(policy)
            elif (
                assignment_id is not None
                and policy.scope_type == RiskScopeType.STRATEGY_ACCOUNT
                and policy.scope_id == assignment_id
            ):
                applicable.append(policy)
        return applicable
