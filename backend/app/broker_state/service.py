"""Provider-independent broker state facade.

Consumers should use BrokerStateService rather than calling Alpaca directly.

CONNECTING AN ALPACA ACCOUNT DOES NOT AUTHORIZE TRADING.
"""

from __future__ import annotations

import logging
from typing import Any

from app.broker_state.errors import BROKER_UNAVAILABLE, BrokerStateError
from app.broker_state.models import (
    AccountSnapshot,
    BrokerFillSnapshot,
    BrokerOrderSnapshot,
    BrokerPositionSnapshot,
)
from app.broker_state.reader import BrokerAccountReader

logger = logging.getLogger(__name__)


class BrokerStateService:
    """Normalize and expose read-only broker account state."""

    def __init__(self, reader: BrokerAccountReader) -> None:
        if reader is None:
            raise BrokerStateError("reader is required", code=BROKER_UNAVAILABLE)
        self._reader = reader

    @property
    def provider_name(self) -> str:
        return self._reader.provider_name

    @property
    def reader(self) -> BrokerAccountReader:
        """Injected reader (never a raw Alpaca SDK client)."""
        return self._reader

    async def get_account_snapshot(self) -> AccountSnapshot:
        snap = await self._reader.get_account()
        logger.info(
            "broker_account_snapshot",
            extra={
                "provider": snap.broker,
                "external_account_id": snap.external_account_id,
                "paper_verified": snap.paper_verified,
                "currency": snap.currency,
            },
        )
        return snap

    async def get_positions(self) -> list[BrokerPositionSnapshot]:
        return await self._reader.get_positions()

    async def get_orders(
        self,
        *,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[BrokerOrderSnapshot]:
        return await self._reader.get_orders(status=status, limit=limit)

    async def get_open_orders(self, *, limit: int | None = None) -> list[BrokerOrderSnapshot]:
        return await self._reader.get_open_orders(limit=limit)

    async def get_order(self, broker_order_id: str) -> BrokerOrderSnapshot:
        return await self._reader.get_order(broker_order_id)

    async def get_trade_activity(
        self,
        *,
        limit: int | None = None,
    ) -> list[BrokerFillSnapshot]:
        return await self._reader.get_trade_activity(limit=limit)

    async def get_cash(self):
        return await self._reader.get_cash()

    async def get_buying_power(self):
        return await self._reader.get_buying_power()

    def select_reader(self) -> BrokerAccountReader:
        """Return the configured reader (provider selection already done at construction)."""
        return self._reader


def build_alpaca_paper_state_service(
    *,
    api_key: str,
    api_secret: str,
    timeout_seconds: float = 10.0,
    transport: Any = None,
) -> BrokerStateService:
    """Factory for Alpaca paper read-path (no live endpoint option)."""
    from app.broker_state.readers.alpaca_paper import AlpacaPaperAccountReader

    reader = AlpacaPaperAccountReader(
        api_key=api_key,
        api_secret=api_secret,
        timeout_seconds=timeout_seconds,
        transport=transport,
    )
    return BrokerStateService(reader)
