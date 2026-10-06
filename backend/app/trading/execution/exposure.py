"""Exposure calculations using deterministic simulation prices only."""

from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import PositionStatus
from app.models.position import Position
from app.trading.execution.market_data import SimulationMarketData


class ExposureBreakdown(BaseModel):
    complete: bool
    reason_code: str | None = None
    message: str = ""
    long_notional: Decimal = Decimal("0")
    short_notional: Decimal = Decimal("0")
    gross_notional: Decimal = Decimal("0")
    unknown_symbols: list[str] = Field(default_factory=list)


class ExposureService:
    def __init__(
        self,
        session: Session,
        *,
        market_data: SimulationMarketData,
    ) -> None:
        self._session = session
        self._market = market_data

    def account_exposure(
        self,
        broker_account_id: uuid.UUID,
        *,
        strategy_id: uuid.UUID | None = None,
    ) -> ExposureBreakdown:
        stmt = select(Position).where(
            Position.broker_account_id == broker_account_id,
            Position.status == PositionStatus.OPEN,
        )
        if strategy_id is not None:
            stmt = stmt.where(Position.strategy_id == strategy_id)
        positions = list(self._session.scalars(stmt).all())
        return self._from_positions(positions)

    def _from_positions(self, positions: list[Position]) -> ExposureBreakdown:
        long_n = Decimal("0")
        short_n = Decimal("0")
        unknown: list[str] = []
        for pos in positions:
            price = self._market.get_price(pos.symbol)
            if price is None:
                unknown.append(pos.symbol)
                continue
            notional = abs(pos.quantity) * price
            if pos.quantity > 0:
                long_n += notional
            else:
                short_n += notional
        if unknown:
            return ExposureBreakdown(
                complete=False,
                reason_code="NOT_EVALUATED_PRICE_REQUIRED",
                message="One or more open positions lack simulation prices",
                long_notional=long_n,
                short_notional=short_n,
                gross_notional=long_n + short_n,
                unknown_symbols=sorted(set(unknown)),
            )
        return ExposureBreakdown(
            complete=True,
            message="Exposure complete",
            long_notional=long_n,
            short_notional=short_n,
            gross_notional=long_n + short_n,
        )

    def proposed_incremental_notional(
        self,
        *,
        symbol: str,
        quantity: Decimal,
    ) -> Decimal | None:
        price = self._market.get_price(symbol)
        if price is None:
            return None
        return abs(quantity) * price
