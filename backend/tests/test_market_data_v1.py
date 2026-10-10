"""Market Data Provider V1 unit tests (offline / deterministic)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.orm import Session

from app.market_data.errors import (
    AUTHENTICATION_FAILED,
    INVALID_SYMBOL,
    PRICE_UNAVAILABLE,
    QUOTE_UNAVAILABLE,
    RATE_LIMITED,
    STALE_MARKET_DATA,
    TRADE_UNAVAILABLE,
    UNSUPPORTED_ASSET_CLASS,
    MarketDataError,
)
from app.market_data.models import MarketDataAssetClass, Quote, Trade
from app.market_data.provider import MarketDataProvider
from app.market_data.providers.alpaca import AlpacaMarketDataProvider
from app.market_data.providers.fake import FakeMarketDataProvider
from app.market_data.providers.simulation import SimulationMarketDataProvider
from app.market_data.reference import resolve_reference_price
from app.market_data.service import MarketDataService
from app.trading.execution.exposure import ExposureService
from app.trading.execution.market_data import SimulationMarketData
from app.trading.risk.engine import RiskEngine
from app.trading.risk import codes
from app.models import (
    AssetClass,
    OrderType,
    Position,
    PositionStatus,
    ProposalSource,
    TradeProposal,
    TradeSide,
)
from tests.pipeline_helpers import make_global_policy, make_simulation_account


def test_reference_price_midpoint_and_trade_fallback() -> None:
    now = datetime.now(UTC)
    quote = Quote(
        symbol="AAPL",
        bid_price=Decimal("100"),
        ask_price=Decimal("102"),
        timestamp=now,
        provider="fake",
    )
    mid = resolve_reference_price(symbol="AAPL", quote=quote, trade=None, provider="fake")
    assert mid.price == Decimal("101")
    assert mid.source == "midpoint"

    trade = Trade(
        symbol="AAPL",
        price=Decimal("99.5"),
        timestamp=now,
        provider="fake",
    )
    last = resolve_reference_price(symbol="AAPL", quote=None, trade=trade, provider="fake")
    assert last.price == Decimal("99.5")
    assert last.source == "last_trade"

    with pytest.raises(MarketDataError) as exc:
        resolve_reference_price(symbol="AAPL", quote=None, trade=None, provider="fake")
    assert exc.value.code == PRICE_UNAVAILABLE


@pytest.mark.asyncio
async def test_fake_quote_trade_bar_decimal_and_errors() -> None:
    fake = FakeMarketDataProvider()
    now = datetime.now(UTC)
    fake.set_quote("aapl", bid=Decimal("10.1"), ask=Decimal("10.3"), timestamp=now)
    fake.set_trade("aapl", price=Decimal("10.2"), timestamp=now, size=Decimal("5"))
    svc = MarketDataService(fake, enforce_freshness=True, quote_max_age_seconds=60)

    q = await svc.get_quote("aapl")
    assert q.symbol == "AAPL"
    assert isinstance(q.bid_price, Decimal)
    t = await svc.get_latest_trade("AAPL")
    assert t.price == Decimal("10.2")
    ref = await svc.get_reference_price("AAPL")
    assert ref.price == Decimal("10.2")

    with pytest.raises(MarketDataError) as exc:
        await svc.get_quote("MSFT")
    assert exc.value.code == QUOTE_UNAVAILABLE

    fake.simulate_rate_limit()
    with pytest.raises(MarketDataError) as exc2:
        await svc.get_quote("AAPL")
    assert exc2.value.code == RATE_LIMITED

    fake.fail_with = None
    fake.simulate_auth_failure()
    with pytest.raises(MarketDataError) as exc3:
        await svc.get_latest_trade("AAPL")
    assert exc3.value.code == AUTHENTICATION_FAILED

    fake.fail_with = None
    with pytest.raises(MarketDataError) as exc4:
        await svc.get_quote("AAPL", asset_class=MarketDataAssetClass.FUTURES)
    assert exc4.value.code == UNSUPPORTED_ASSET_CLASS


@pytest.mark.asyncio
async def test_stale_quote_rejected() -> None:
    fake = FakeMarketDataProvider()
    old = datetime.now(UTC) - timedelta(seconds=120)
    fake.set_quote("AAPL", bid=Decimal("1"), ask=Decimal("2"), timestamp=old)
    svc = MarketDataService(fake, quote_max_age_seconds=30, enforce_freshness=True)
    with pytest.raises(MarketDataError) as exc:
        await svc.get_quote("AAPL")
    assert exc.value.code == STALE_MARKET_DATA


@pytest.mark.asyncio
async def test_simulation_provider_preserves_board() -> None:
    board = SimulationMarketData()
    board.set_price("AAPL", Decimal("55"))
    provider = SimulationMarketDataProvider(board)
    svc = MarketDataService(provider, enforce_freshness=False)
    q = await svc.get_quote("AAPL")
    assert q.bid_price == Decimal("55")
    ref = svc.sync_reference_price("AAPL")
    assert ref.price == Decimal("55")
    with pytest.raises(MarketDataError):
        svc.sync_reference_price("NOPE")


def test_alpaca_provider_has_no_execution_methods() -> None:
    import re

    provider = AlpacaMarketDataProvider(api_key="k", api_secret="s")
    assert not hasattr(provider, "place_order")
    assert not hasattr(provider, "cancel_order")
    assert not hasattr(provider, "modify_order")
    assert not hasattr(provider, "close_position")
    assert not hasattr(provider, "liquidate")
    # Interface is MarketDataProvider only
    assert isinstance(provider, MarketDataProvider)
    src = open("app/market_data/providers/alpaca.py", encoding="utf-8").read()
    src_lower = src.lower()
    assert "place_order" not in src_lower
    assert "tradingclient" not in src_lower
    # Real import statements only — not docstring mentions of "Alpaca"
    assert re.search(r"(?m)^\s*from\s+alpaca(\.|\s)", src) is None
    assert re.search(r"(?m)^\s*import\s+alpaca(\.|\s|$)", src) is None


def test_market_data_service_has_no_execution_methods() -> None:
    svc = MarketDataService(FakeMarketDataProvider())
    assert not hasattr(svc, "place_order")
    assert not hasattr(svc, "cancel_order")
    assert not hasattr(svc, "modify_order")


def test_risk_engine_valid_stale_unavailable_price(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="MD-Risk")
    make_global_policy(db_session, require_stop_loss=False, max_order_value=Decimal("500"))

    fake = FakeMarketDataProvider()
    now = datetime.now(UTC)
    fake.set_quote("AAPL", bid=Decimal("10"), ask=Decimal("10"), timestamp=now)
    fake.set_trade("AAPL", price=Decimal("10"), timestamp=now)
    mds = MarketDataService(fake, quote_max_age_seconds=60, enforce_freshness=True)
    engine = RiskEngine(db_session, market_data_service=mds)

    proposal = TradeProposal(
        broker_account_id=account.id,
        source=ProposalSource.MANUAL,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        side=TradeSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("10"),  # 100 <= 500
    )
    db_session.add(proposal)
    db_session.flush()
    ok = engine.evaluate(proposal)
    assert ok.approved is True

    # Stale
    fake.set_quote("AAPL", bid=Decimal("10"), ask=Decimal("10"), timestamp=now - timedelta(hours=1))
    fake.trades.clear()
    mds_stale = MarketDataService(fake, quote_max_age_seconds=30, enforce_freshness=True)
    engine2 = RiskEngine(db_session, market_data_service=mds_stale)
    proposal2 = TradeProposal(
        broker_account_id=account.id,
        source=ProposalSource.MANUAL,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        side=TradeSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("10"),
    )
    db_session.add(proposal2)
    db_session.flush()
    bad = engine2.evaluate(proposal2)
    assert bad.approved is False
    assert bad.reason_code == STALE_MARKET_DATA

    # Unavailable
    fake.quotes.clear()
    fake.trades.clear()
    engine3 = RiskEngine(db_session, market_data_service=mds_stale)
    proposal3 = TradeProposal(
        broker_account_id=account.id,
        source=ProposalSource.MANUAL,
        symbol="MSFT",
        asset_class=AssetClass.EQUITY,
        side=TradeSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("1"),
    )
    db_session.add(proposal3)
    db_session.flush()
    missing = engine3.evaluate(proposal3)
    assert missing.approved is False


def test_exposure_marking_with_market_data_service(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="MD-Exp")
    db_session.add(
        Position(
            broker_account_id=account.id,
            symbol="AAPL",
            asset_class=AssetClass.EQUITY,
            quantity=Decimal("10"),
            average_entry_price=Decimal("100"),
            status=PositionStatus.OPEN,
        )
    )
    db_session.flush()
    fake = FakeMarketDataProvider()
    now = datetime.now(UTC)
    fake.set_quote("AAPL", bid=Decimal("110"), ask=Decimal("110"), timestamp=now)
    fake.set_trade("AAPL", price=Decimal("110"), timestamp=now)
    mds = MarketDataService(fake, enforce_freshness=False)
    exp = ExposureService(db_session, market_data_service=mds)
    breakdown = exp.account_exposure(account.id)
    assert breakdown.complete is True
    assert breakdown.gross_notional == Decimal("1100")
    marked = exp.mark_open_positions(account.id)
    assert marked[0][1] == Decimal("100")


@pytest.mark.asyncio
async def test_alpaca_provider_maps_http_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = AlpacaMarketDataProvider(api_key="k", api_secret="s")

    class _Resp:
        def __init__(self, status: int, payload: dict | None = None) -> None:
            self.status_code = status
            self._payload = payload or {}

        def json(self) -> dict:
            return self._payload

    class _Client:
        def __init__(self, *a, **k) -> None:
            pass

        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *a) -> None:
            return None

        async def get(self, url: str, headers: dict | None = None, params: dict | None = None):
            assert "orders" not in url
            assert headers and "APCA-API-KEY-ID" in headers
            return self._resp

    async def _run(status: int, code: str) -> None:
        _Client._resp = _Resp(status)
        monkeypatch.setattr("app.market_data.providers.alpaca.httpx.AsyncClient", _Client)
        with pytest.raises(MarketDataError) as exc:
            await provider.get_quote("AAPL")
        assert exc.value.code == code

    await _run(401, AUTHENTICATION_FAILED)
    await _run(429, RATE_LIMITED)
    await _run(404, INVALID_SYMBOL)

    _Client._resp = _Resp(
        200,
        {
            "quote": {
                "bp": "100.5",
                "ap": "100.7",
                "bs": "1",
                "as": "2",
                "t": datetime.now(UTC).isoformat(),
            }
        },
    )
    monkeypatch.setattr("app.market_data.providers.alpaca.httpx.AsyncClient", _Client)
    q = await provider.get_quote("AAPL")
    assert q.bid_price == Decimal("100.5")
    assert isinstance(q.ask_price, Decimal)
