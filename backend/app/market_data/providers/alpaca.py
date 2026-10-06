"""Alpaca Market Data provider — READ ONLY via HTTP.

ALPACA MARKET DATA ACCESS DOES NOT ENABLE ALPACA ORDER EXECUTION.

This module uses httpx against Alpaca's Market Data REST API only.
It must never import Alpaca trading SDKs or call order endpoints.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.market_data.errors import (
    AUTHENTICATION_FAILED,
    BARS_UNAVAILABLE,
    INVALID_SYMBOL,
    PROVIDER_UNAVAILABLE,
    QUOTE_UNAVAILABLE,
    RATE_LIMITED,
    TRADE_UNAVAILABLE,
    UNSUPPORTED_ASSET_CLASS,
    MarketDataError,
)
from app.market_data.models import Bar, MarketDataAssetClass, Quote, Trade
from app.market_data.provider import MarketDataProvider

logger = logging.getLogger(__name__)

# Stock market data only for Alpaca V1.
_SUPPORTED = frozenset({MarketDataAssetClass.EQUITY})

# Explicit deny-list of trading path fragments — never call these.
_FORBIDDEN_PATH_FRAGMENTS = (
    "/v2/orders",
    "/v1/orders",
    "/orders",
    "/positions",
    "/account",
)


def _dec(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise MarketDataError(f"Invalid decimal: {value!r}", code=PROVIDER_UNAVAILABLE) from exc


def _parse_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if not value:
        raise MarketDataError("Missing timestamp", code=PROVIDER_UNAVAILABLE)
    text = str(value).replace("Z", "+00:00")
    return datetime.fromisoformat(text)


class AlpacaMarketDataProvider(MarketDataProvider):
    """Read-only Alpaca market-data client (stocks/equity V1)."""

    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        base_url: str = "https://data.alpaca.markets",
        timeout_seconds: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key or not api_secret:
            raise MarketDataError(
                "Alpaca market-data credentials are required",
                code=AUTHENTICATION_FAILED,
            )
        self._api_key = api_key
        self._api_secret = api_secret
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._transport = transport

    @property
    def provider_name(self) -> str:
        return "alpaca"

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self._api_key,
            "APCA-API-SECRET-KEY": self._api_secret,
            "Accept": "application/json",
        }

    def _assert_safe_path(self, path: str) -> None:
        lowered = path.lower()
        for frag in _FORBIDDEN_PATH_FRAGMENTS:
            if frag in lowered:
                raise MarketDataError(
                    "Refusing to call Alpaca trading endpoint from market-data provider",
                    code=PROVIDER_UNAVAILABLE,
                )

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._assert_safe_path(path)
        url = f"{self._base_url}{path}"
        # Never log headers or credential-bearing URLs with secrets.
        logger.info(
            "alpaca_market_data_request",
            extra={"provider": self.provider_name, "path": path, "params_keys": list((params or {}).keys())},
        )
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = await client.get(url, headers=self._headers(), params=params)
        except httpx.TimeoutException as exc:
            raise MarketDataError("Alpaca market-data request timed out", code=PROVIDER_UNAVAILABLE) from exc
        except httpx.HTTPError as exc:
            raise MarketDataError("Alpaca market-data network error", code=PROVIDER_UNAVAILABLE) from exc

        if response.status_code in {401, 403}:
            raise MarketDataError("Alpaca market-data authentication failed", code=AUTHENTICATION_FAILED)
        if response.status_code == 429:
            raise MarketDataError("Alpaca market-data rate limited", code=RATE_LIMITED)
        if response.status_code == 404:
            raise MarketDataError("Symbol or resource not found", code=INVALID_SYMBOL)
        if response.status_code >= 400:
            raise MarketDataError(
                f"Alpaca market-data HTTP {response.status_code}",
                code=PROVIDER_UNAVAILABLE,
            )
        data = response.json()
        if not isinstance(data, dict):
            raise MarketDataError("Unexpected Alpaca response shape", code=PROVIDER_UNAVAILABLE)
        return data

    def _ensure_equity(self, asset_class: MarketDataAssetClass) -> None:
        if asset_class not in _SUPPORTED:
            raise MarketDataError(
                f"AlpacaMarketDataProvider V1 supports equity only; got {asset_class}",
                code=UNSUPPORTED_ASSET_CLASS,
            )

    async def get_quote(
        self,
        symbol: str,
        *,
        asset_class: MarketDataAssetClass = MarketDataAssetClass.EQUITY,
    ) -> Quote:
        self._ensure_equity(asset_class)
        sym = symbol.strip().upper()
        if not sym:
            raise MarketDataError("Invalid symbol", code=INVALID_SYMBOL)
        data = await self._get(f"/v2/stocks/{sym}/quotes/latest")
        quote = data.get("quote") or data
        if not isinstance(quote, dict):
            raise MarketDataError("Quote unavailable", code=QUOTE_UNAVAILABLE)
        bid = _dec(quote.get("bp") if "bp" in quote else quote.get("bid_price"))
        ask = _dec(quote.get("ap") if "ap" in quote else quote.get("ask_price"))
        ts = quote.get("t") or quote.get("timestamp")
        if ts is None:
            raise MarketDataError("Quote missing timestamp", code=QUOTE_UNAVAILABLE)
        return Quote(
            symbol=sym,
            bid_price=bid,
            ask_price=ask,
            bid_size=_dec(quote.get("bs") if "bs" in quote else quote.get("bid_size")),
            ask_size=_dec(quote.get("as") if "as" in quote else quote.get("ask_size")),
            timestamp=_parse_ts(ts),
            provider=self.provider_name,
            asset_class=MarketDataAssetClass.EQUITY,
            raw={"alpaca": True},
        )

    async def get_latest_trade(
        self,
        symbol: str,
        *,
        asset_class: MarketDataAssetClass = MarketDataAssetClass.EQUITY,
    ) -> Trade:
        self._ensure_equity(asset_class)
        sym = symbol.strip().upper()
        if not sym:
            raise MarketDataError("Invalid symbol", code=INVALID_SYMBOL)
        data = await self._get(f"/v2/stocks/{sym}/trades/latest")
        trade = data.get("trade") or data
        if not isinstance(trade, dict):
            raise MarketDataError("Trade unavailable", code=TRADE_UNAVAILABLE)
        price = _dec(trade.get("p") if "p" in trade else trade.get("price"))
        if price is None:
            raise MarketDataError("Trade missing price", code=TRADE_UNAVAILABLE)
        ts = trade.get("t") or trade.get("timestamp")
        if ts is None:
            raise MarketDataError("Trade missing timestamp", code=TRADE_UNAVAILABLE)
        return Trade(
            symbol=sym,
            price=price,
            size=_dec(trade.get("s") if "s" in trade else trade.get("size")),
            timestamp=_parse_ts(ts),
            provider=self.provider_name,
            asset_class=MarketDataAssetClass.EQUITY,
            raw={"alpaca": True},
        )

    async def get_bars(
        self,
        symbol: str,
        *,
        timeframe: str,
        start: datetime | None = None,
        end: datetime | None = None,
        asset_class: MarketDataAssetClass = MarketDataAssetClass.EQUITY,
        limit: int | None = None,
    ) -> list[Bar]:
        self._ensure_equity(asset_class)
        sym = symbol.strip().upper()
        if not sym:
            raise MarketDataError("Invalid symbol", code=INVALID_SYMBOL)
        params: dict[str, Any] = {"timeframe": timeframe}
        if start is not None:
            params["start"] = start.isoformat()
        if end is not None:
            params["end"] = end.isoformat()
        if limit is not None:
            params["limit"] = limit
        data = await self._get(f"/v2/stocks/{sym}/bars", params=params)
        bars_raw = data.get("bars") or []
        if not isinstance(bars_raw, list):
            raise MarketDataError("Bars unavailable", code=BARS_UNAVAILABLE)
        out: list[Bar] = []
        for row in bars_raw:
            if not isinstance(row, dict):
                continue
            out.append(
                Bar(
                    symbol=sym,
                    open=_dec(row.get("o") if "o" in row else row.get("open")) or Decimal("0"),
                    high=_dec(row.get("h") if "h" in row else row.get("high")) or Decimal("0"),
                    low=_dec(row.get("l") if "l" in row else row.get("low")) or Decimal("0"),
                    close=_dec(row.get("c") if "c" in row else row.get("close")) or Decimal("0"),
                    volume=_dec(row.get("v") if "v" in row else row.get("volume")),
                    timestamp=_parse_ts(row.get("t") or row.get("timestamp")),
                    timeframe=timeframe,
                    provider=self.provider_name,
                    asset_class=MarketDataAssetClass.EQUITY,
                    raw={"alpaca": True},
                )
            )
        return out
