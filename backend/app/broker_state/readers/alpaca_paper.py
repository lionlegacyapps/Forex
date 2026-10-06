"""Alpaca PAPER account reader — READ ONLY.

CONNECTING AN ALPACA ACCOUNT DOES NOT AUTHORIZE TRADING.

This module uses httpx against Alpaca's PAPER Trading REST API only.
It must never:
  - target live Alpaca trading (api.alpaca.markets)
  - expose place_order / cancel_order / modify_order / close_position
  - expose a raw Alpaca SDK TradingClient
  - issue POST/PATCH/PUT/DELETE to the trading API
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

import httpx

from app.broker_state.errors import (
    ACCOUNT_UNAVAILABLE,
    AUTHENTICATION_FAILED,
    BROKER_UNAVAILABLE,
    LIVE_BROKER_ACCESS_FORBIDDEN,
    MALFORMED_RESPONSE,
    NETWORK_TIMEOUT,
    ORDER_NOT_FOUND,
    PAPER_ACCOUNT_NOT_VERIFIED,
    RATE_LIMITED,
    BrokerStateError,
)
from app.broker_state.models import (
    AccountSnapshot,
    BrokerAssetClass,
    BrokerFillSnapshot,
    BrokerOrderSnapshot,
    BrokerPositionSnapshot,
)
from app.broker_state.reader import BrokerAccountReader

logger = logging.getLogger(__name__)

# Hard-locked paper host. Live trading host is never selectable.
ALPACA_PAPER_BASE_URL = "https://paper-api.alpaca.markets"
_LIVE_HOST_MARKERS = (
    "api.alpaca.markets",  # live trading API (exact host check below)
)
_FORBIDDEN_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# GET-only allowlist (path prefixes).
_ALLOWED_GET_PREFIXES = (
    "/v2/account",
    "/v2/positions",
    "/v2/orders",
)


def _dec(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise BrokerStateError(f"Invalid decimal: {value!r}", code=MALFORMED_RESPONSE) from exc


def _dec_required(value: Any, *, field: str) -> Decimal:
    parsed = _dec(value)
    if parsed is None:
        raise BrokerStateError(f"Missing required decimal field: {field}", code=MALFORMED_RESPONSE)
    return parsed


def _parse_ts(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value).replace("Z", "+00:00")
    return datetime.fromisoformat(text)


def _now() -> datetime:
    return datetime.now(UTC)


def assert_paper_base_url(base_url: str) -> str:
    """Fail closed if URL would target Alpaca live trading."""
    cleaned = (base_url or "").strip().rstrip("/")
    if not cleaned:
        raise BrokerStateError(
            "Alpaca paper base URL is required",
            code=LIVE_BROKER_ACCESS_FORBIDDEN,
        )
    parsed = urlparse(cleaned)
    host = (parsed.hostname or "").lower()
    # Exact paper host only.
    if host != "paper-api.alpaca.markets":
        # Explicit live rejection.
        if host == "api.alpaca.markets" or "api.alpaca.markets" in host:
            raise BrokerStateError(
                "Live Alpaca trading endpoint is forbidden",
                code=LIVE_BROKER_ACCESS_FORBIDDEN,
            )
        raise BrokerStateError(
            f"Only Alpaca paper-api host is allowed; got host={host!r}",
            code=LIVE_BROKER_ACCESS_FORBIDDEN,
        )
    if parsed.scheme not in {"https", ""}:
        raise BrokerStateError(
            "Alpaca paper endpoint must use https",
            code=LIVE_BROKER_ACCESS_FORBIDDEN,
        )
    return cleaned or ALPACA_PAPER_BASE_URL


class AlpacaPaperAccountReader(BrokerAccountReader):
    """Read-only Alpaca PAPER account client.

    Credentials are held privately. The HTTP client is never exposed.
    """

    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        base_url: str = ALPACA_PAPER_BASE_URL,
        timeout_seconds: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
        require_paper_verification: bool = True,
    ) -> None:
        if not api_key or not api_secret:
            raise BrokerStateError(
                "Alpaca paper credentials are required",
                code=AUTHENTICATION_FAILED,
            )
        self._api_key = api_key
        self._api_secret = api_secret
        self._base_url = assert_paper_base_url(base_url)
        self._timeout = timeout_seconds
        self._transport = transport
        self._require_paper_verification = require_paper_verification
        self._paper_verified = False
        self._verified_external_id: str | None = None

    @property
    def provider_name(self) -> str:
        return "alpaca"

    @property
    def paper_verified(self) -> bool:
        return self._paper_verified

    # --- Encapsulation: no public client / write surface ---
    # Intentionally NO: place_order, cancel_order, modify_order, close_position
    # Intentionally NO: .client property

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self._api_key,
            "APCA-API-SECRET-KEY": self._api_secret,
            "Accept": "application/json",
        }

    def _assert_safe_get(self, path: str) -> None:
        if not path.startswith("/"):
            raise BrokerStateError("Invalid path", code=BROKER_UNAVAILABLE)
        if any(path.upper().startswith(m) for m in _FORBIDDEN_METHODS):
            raise BrokerStateError("Mutating HTTP methods are forbidden", code=BROKER_UNAVAILABLE)
        allowed = any(path == p or path.startswith(p + "/") or path.startswith(p + "?") for p in _ALLOWED_GET_PREFIXES)
        # /v2/account/activities is under /v2/account
        if not allowed:
            raise BrokerStateError(
                f"Path not allowed for paper account reader: {path}",
                code=BROKER_UNAVAILABLE,
            )

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        self._assert_safe_get(path)
        # Re-validate host on every call (defense in depth).
        assert_paper_base_url(self._base_url)
        url = f"{self._base_url}{path}"
        logger.info(
            "alpaca_paper_account_request",
            extra={
                "provider": self.provider_name,
                "path": path,
                "method": "GET",
                "params_keys": list((params or {}).keys()),
            },
        )
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                # GET only — never POST/PATCH/DELETE.
                response = await client.get(url, headers=self._headers(), params=params)
        except httpx.TimeoutException as exc:
            raise BrokerStateError("Alpaca paper account request timed out", code=NETWORK_TIMEOUT) from exc
        except httpx.HTTPError as exc:
            raise BrokerStateError("Alpaca paper account network error", code=BROKER_UNAVAILABLE) from exc

        if response.status_code in {401, 403}:
            raise BrokerStateError("Alpaca paper authentication failed", code=AUTHENTICATION_FAILED)
        if response.status_code == 429:
            raise BrokerStateError("Alpaca paper rate limited", code=RATE_LIMITED)
        if response.status_code == 404:
            raise BrokerStateError("Alpaca resource not found", code=ORDER_NOT_FOUND)
        if response.status_code >= 400:
            raise BrokerStateError(
                f"Alpaca paper HTTP {response.status_code}",
                code=BROKER_UNAVAILABLE,
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise BrokerStateError("Alpaca returned non-JSON body", code=MALFORMED_RESPONSE) from exc
        return data

    def _mark_paper_verified(self, account_id: str) -> None:
        # Host is paper-api; successful account read from paper host = paper verified.
        if not account_id:
            raise BrokerStateError(
                "Paper account id missing; cannot verify paper environment",
                code=PAPER_ACCOUNT_NOT_VERIFIED,
            )
        self._paper_verified = True
        self._verified_external_id = account_id

    def _ensure_paper_verified(self) -> None:
        if self._require_paper_verification and not self._paper_verified:
            raise BrokerStateError(
                "Paper account not verified; call get_account() first",
                code=PAPER_ACCOUNT_NOT_VERIFIED,
            )

    def _normalize_account(self, data: dict[str, Any]) -> AccountSnapshot:
        if not isinstance(data, dict):
            raise BrokerStateError("Account payload malformed", code=MALFORMED_RESPONSE)
        external_id = str(data.get("id") or "").strip()
        if not external_id:
            raise BrokerStateError("Account id missing", code=PAPER_ACCOUNT_NOT_VERIFIED)
        # Paper host already validated; mark verified.
        self._mark_paper_verified(external_id)
        status = str(data.get("status") or "unknown")
        return AccountSnapshot(
            broker=self.provider_name,
            external_account_id=external_id,
            account_status=status,
            currency=str(data.get("currency") or "USD"),
            cash=_dec_required(data.get("cash"), field="cash"),
            equity=_dec(data.get("equity")),
            buying_power=_dec(data.get("buying_power")),
            portfolio_value=_dec(data.get("portfolio_value")),
            timestamp=_now(),
            trading_blocked=bool(data.get("trading_blocked", False)),
            account_blocked=bool(data.get("account_blocked", False)),
            paper_verified=True,
            account_number=str(data["account_number"]) if data.get("account_number") else None,
        )

    def _normalize_position(self, row: dict[str, Any]) -> BrokerPositionSnapshot:
        qty = _dec_required(row.get("qty") if row.get("qty") is not None else row.get("quantity"), field="qty")
        side_raw = str(row.get("side") or "").lower()
        if not side_raw:
            side_raw = "long" if qty >= 0 else "short"
        asset = str(row.get("asset_class") or "us_equity").lower()
        asset_class = BrokerAssetClass.EQUITY
        if "crypto" in asset:
            asset_class = BrokerAssetClass.CRYPTO
        elif "option" in asset:
            asset_class = BrokerAssetClass.OPTION
        return BrokerPositionSnapshot(
            symbol=str(row.get("symbol") or "").upper(),
            asset_class=asset_class,
            quantity=abs(qty),
            side=side_raw,
            average_entry_price=_dec(row.get("avg_entry_price")),
            current_price=_dec(row.get("current_price")),
            market_value=_dec(row.get("market_value")),
            unrealized_pnl=_dec(row.get("unrealized_pl")),
            unrealized_pnl_percent=_dec(row.get("unrealized_plpc")),
            timestamp=_now(),
            broker=self.provider_name,
        )

    def _normalize_order(self, row: dict[str, Any]) -> BrokerOrderSnapshot:
        oid = str(row.get("id") or "").strip()
        if not oid:
            raise BrokerStateError("Order missing id", code=MALFORMED_RESPONSE)
        status = str(row.get("status") or "unknown").lower()
        # Normalize Alpaca canceled → cancelled
        if status == "canceled":
            status = "cancelled"
        return BrokerOrderSnapshot(
            broker_order_id=oid,
            symbol=str(row.get("symbol") or "").upper(),
            asset_class=BrokerAssetClass.EQUITY,
            side=str(row.get("side") or "").lower(),
            order_type=str(row.get("type") or row.get("order_type") or "").lower(),
            quantity=_dec_required(row.get("qty"), field="qty"),
            filled_quantity=_dec(row.get("filled_qty")) or Decimal("0"),
            limit_price=_dec(row.get("limit_price")),
            stop_price=_dec(row.get("stop_price")),
            time_in_force=str(row.get("time_in_force")).lower() if row.get("time_in_force") else None,
            status=status,
            submitted_at=_parse_ts(row.get("submitted_at") or row.get("created_at")),
            filled_at=_parse_ts(row.get("filled_at")),
            cancelled_at=_parse_ts(row.get("canceled_at") or row.get("cancelled_at")),
            broker=self.provider_name,
        )

    def _normalize_fill(self, row: dict[str, Any]) -> BrokerFillSnapshot | None:
        if not isinstance(row, dict):
            return None
        activity_type = str(row.get("activity_type") or row.get("type") or "").upper()
        if activity_type and activity_type not in {"FILL", "PARTIAL_FILL"}:
            # Allow rows without type when already filtered by API.
            if "activity_type" in row:
                return None
        aid = str(row.get("id") or "").strip()
        if not aid:
            return None
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            return None
        qty = _dec(row.get("qty") or row.get("quantity"))
        price = _dec(row.get("price"))
        ts = _parse_ts(row.get("transaction_time") or row.get("timestamp") or row.get("date"))
        if qty is None or price is None or ts is None:
            return None
        return BrokerFillSnapshot(
            activity_id=aid,
            broker_order_id=str(row["order_id"]) if row.get("order_id") else None,
            symbol=symbol,
            side=str(row["side"]).lower() if row.get("side") else None,
            quantity=qty,
            price=price,
            timestamp=ts,
            broker=self.provider_name,
        )

    async def verify_paper_account(self) -> AccountSnapshot:
        """Explicit paper verification — fail closed if not paper."""
        assert_paper_base_url(self._base_url)
        data = await self._get("/v2/account")
        if not isinstance(data, dict):
            raise BrokerStateError("Account response malformed", code=MALFORMED_RESPONSE)
        snap = self._normalize_account(data)
        if not snap.paper_verified:
            raise BrokerStateError(
                "Paper account verification failed",
                code=PAPER_ACCOUNT_NOT_VERIFIED,
            )
        return snap

    async def get_account(self) -> AccountSnapshot:
        return await self.verify_paper_account()

    async def get_positions(self) -> list[BrokerPositionSnapshot]:
        if not self._paper_verified:
            await self.verify_paper_account()
        data = await self._get("/v2/positions")
        if data is None:
            return []
        if not isinstance(data, list):
            raise BrokerStateError("Positions response malformed", code=MALFORMED_RESPONSE)
        return [self._normalize_position(row) for row in data if isinstance(row, dict)]

    async def get_orders(
        self,
        *,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[BrokerOrderSnapshot]:
        if not self._paper_verified:
            await self.verify_paper_account()
        params: dict[str, Any] = {}
        if status:
            # Alpaca uses status=open|closed|all
            params["status"] = status
        else:
            params["status"] = "all"
        if limit is not None:
            params["limit"] = limit
        params["direction"] = "desc"
        data = await self._get("/v2/orders", params=params)
        if data is None:
            return []
        if not isinstance(data, list):
            raise BrokerStateError("Orders response malformed", code=MALFORMED_RESPONSE)
        return [self._normalize_order(row) for row in data if isinstance(row, dict)]

    async def get_order(self, broker_order_id: str) -> BrokerOrderSnapshot:
        if not self._paper_verified:
            await self.verify_paper_account()
        oid = (broker_order_id or "").strip()
        if not oid:
            raise BrokerStateError("broker_order_id required", code=ORDER_NOT_FOUND)
        data = await self._get(f"/v2/orders/{oid}")
        if not isinstance(data, dict):
            raise BrokerStateError("Order response malformed", code=MALFORMED_RESPONSE)
        return self._normalize_order(data)

    async def get_trade_activity(
        self,
        *,
        limit: int | None = None,
    ) -> list[BrokerFillSnapshot]:
        if not self._paper_verified:
            await self.verify_paper_account()
        params: dict[str, Any] = {"activity_types": "FILL"}
        if limit is not None:
            params["page_size"] = limit
        data = await self._get("/v2/account/activities", params=params)
        if data is None:
            return []
        if not isinstance(data, list):
            raise BrokerStateError("Activity response malformed", code=MALFORMED_RESPONSE)
        out: list[BrokerFillSnapshot] = []
        for row in data:
            fill = self._normalize_fill(row)
            if fill is not None:
                out.append(fill)
        return out
