"""Daily realized P&L from execution.realized_pnl (timezone-aware)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.execution import Execution
from app.models.order import Order
from app.models.trade_proposal import TradeProposal


class DailyPnlResult(BaseModel):
    trading_day: date
    timezone: str
    realized_pnl: Decimal
    complete: bool = True
    message: str = ""


class DailyPnlService:
    """Sum fill-attributed realized PnL for a trading day window."""

    def __init__(self, session: Session, *, trading_timezone: str = "America/New_York") -> None:
        self._session = session
        self._tz_name = trading_timezone
        self._tz = ZoneInfo(trading_timezone)

    def trading_day_bounds(
        self, *, as_of: datetime | None = None
    ) -> tuple[date, datetime, datetime]:
        now = as_of or datetime.now(tz=self._tz)
        if now.tzinfo is None:
            now = now.replace(tzinfo=self._tz)
        local = now.astimezone(self._tz)
        day = local.date()
        start = datetime.combine(day, time.min, tzinfo=self._tz)
        end = start + timedelta(days=1)
        return day, start, end

    def realized_pnl(
        self,
        *,
        broker_account_id: uuid.UUID | None = None,
        strategy_id: uuid.UUID | None = None,
        as_of: datetime | None = None,
    ) -> DailyPnlResult:
        day, start, end = self.trading_day_bounds(as_of=as_of)
        stmt: Select = (
            select(func.coalesce(func.sum(Execution.realized_pnl), 0))
            .select_from(Execution)
            .join(Order, Order.id == Execution.order_id)
            .where(
                Execution.accounting_applied.is_(True),
                Execution.executed_at >= start,
                Execution.executed_at < end,
            )
        )
        if broker_account_id is not None:
            stmt = stmt.where(Order.broker_account_id == broker_account_id)
        if strategy_id is not None:
            stmt = stmt.join(
                TradeProposal, TradeProposal.id == Order.trade_proposal_id
            ).where(TradeProposal.strategy_id == strategy_id)

        total = self._session.scalar(stmt)
        return DailyPnlResult(
            trading_day=day,
            timezone=self._tz_name,
            realized_pnl=Decimal(str(total or 0)),
            complete=True,
            message="Sum of execution.realized_pnl for trading day",
        )
