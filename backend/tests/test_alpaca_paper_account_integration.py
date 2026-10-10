"""Optional live Alpaca PAPER account integration (SKIP without credentials).

CONNECTING AN ALPACA ACCOUNT DOES NOT AUTHORIZE TRADING.

This test performs READ-ONLY calls against paper-api.alpaca.markets.
It must never place, cancel, or modify orders.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest

from app.broker_state.readers.alpaca_paper import AlpacaPaperAccountReader
from app.broker_state.service import BrokerStateService
from app.core.config import get_settings


def _credentials() -> tuple[str, str] | None:
    get_settings.cache_clear()
    settings = get_settings()
    key = (settings.alpaca_api_key or os.getenv("ALPACA_API_KEY") or "").strip()
    secret = (settings.alpaca_api_secret or os.getenv("ALPACA_API_SECRET") or "").strip()
    if not key or not secret:
        return None
    return key, secret


@pytest.mark.asyncio
async def test_alpaca_paper_account_readonly_optional() -> None:
    creds = _credentials()
    if creds is None:
        pytest.skip("ALPACA_API_KEY / ALPACA_API_SECRET not configured")

    key, secret = creds
    reader = AlpacaPaperAccountReader(
        api_key=key,
        api_secret=secret,
        timeout_seconds=15.0,
    )
    # Architectural: no trading methods; no raw client
    assert not hasattr(reader, "place_order")
    assert not hasattr(reader, "cancel_order")
    assert not hasattr(reader, "client")

    svc = BrokerStateService(reader)
    snap = await svc.get_account_snapshot()
    assert snap.paper_verified is True
    assert snap.broker == "alpaca"
    assert snap.external_account_id
    assert isinstance(snap.cash, Decimal)
    assert snap.timestamp is not None

    positions = await svc.get_positions()
    assert isinstance(positions, list)

    orders = await svc.get_open_orders()
    assert isinstance(orders, list)

    # Empty account is valid — do not require positions/orders.
    activity = await svc.get_trade_activity(limit=5)
    assert isinstance(activity, list)
