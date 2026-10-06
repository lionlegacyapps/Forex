"""Exposure calculations using MarketDataService or SimulationMarketData."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.market_data.errors import MarketDataError
from app.market_data.service import MarketDataService
from app.models.enums import PositionStatus
from app.models.position import Position
from app.trading.execution.market_data import SimulationMarketData
from app.trading.execution.position_accounting import PositionAccountingService


class _HasGetPrice(Protocol):
    def get_price(self, symbol: str) -> Decimal | None: ...


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
        market_data: SimulationMarketData | None = None,
        market_data_service: MarketDataService | None = None,
    ) -> None:
        self._session = session
        self._board = market_data
        self._mds = market_data_service

    def _lookup_price(self, symbol: str) -> tuple[Decimal | None, str | None]:
        if self._mds is not None:
            try:
                ref = self._mds.sync_reference_price(symbol)
                return ref.price, None
            except MarketDataError as exc:
                return None, exc.code
        if self._board is not None:
            price = self._board.get_price(symbol)
            if price is None:
                return None, "NOT_EVALUATED_PRICE_REQUIRED"
            return price, None
        return None, "NOT_EVALUATED_PRICE_REQUIRED"

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
        reason: str | None = None
        for pos in positions:
            price, err = self._lookup_price(pos.symbol)
            if price is None:
                unknown.append(pos.symbol)
                reason = err or "NOT_EVALUATED_PRICE_REQUIRED"
                continue
            notional = abs(pos.quantity) * price
            if pos.quantity > 0:
                long_n += notional
            else:
                short_n += notional
        if unknown:
            return ExposureBreakdown(
                complete=False,
                reason_code=reason or "NOT_EVALUATED_PRICE_REQUIRED",
                message="One or more open positions lack reliable market prices",
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
        price, _err = self._lookup_price(symbol)
        if price is None:
            return None
        return abs(quantity) * price

    def mark_open_positions(
        self,
        broker_account_id: uuid.UUID,
        *,
        strategy_id: uuid.UUID | None = None,
    ) -> list[tuple[Position, Decimal | None]]:
        """Update current_price / unrealized using reference prices."""
        stmt = select(Position).where(
            Position.broker_account_id == broker_account_id,
            Position.status == PositionStatus.OPEN,
        )
        if strategy_id is not None:
            stmt = stmt.where(Position.strategy_id == strategy_id)
        positions = list(self._session.scalars(stmt).all())
        accounting = PositionAccountingService(self._session)
        results: list[tuple[Position, Decimal | None]] = []
        for pos in positions:
            price, _err = self._lookup_price(pos.symbol)
            upnl = accounting.mark_position(pos, price)
            results.append((pos, upnl))
        self._session.flush()
        return results
