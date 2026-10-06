"""Alpaca PAPER execution adapter — submit_order only.

ALPACA PAPER EXECUTION DOES NOT ENABLE LIVE TRADING.

Uses httpx against paper-api.alpaca.markets only.
Never exposes a raw TradingClient.
Never implements cancel/replace/close for application use.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.broker_state.readers.alpaca_paper import (
    ALPACA_PAPER_BASE_URL,
    assert_paper_base_url,
)
from app.brokers.execution.adapter import BrokerExecutionAdapter
from app.brokers.execution.errors import (
    ACCOUNT_BLOCKED,
    AMBIGUOUS_IDEMPOTENCY_STATE,
    AUTHENTICATION_FAILED,
    BROKER_ACCOUNT_DISABLED,
    BROKER_UNAVAILABLE,
    INSUFFICIENT_BROKER_BUYING_POWER,
    LIVE_BROKER_ACCESS_FORBIDDEN,
    MALFORMED_RESPONSE,
    NETWORK_TIMEOUT,
    ORDER_REJECTED_BY_BROKER,
    PAPER_ACCOUNT_NOT_VERIFIED,
    PIPELINE_PRECONDITION_FAILED,
    PRICE_UNAVAILABLE,
    RATE_LIMITED,
    STALE_MARKET_DATA,
    TRADING_BLOCKED,
    UNSUPPORTED_ASSET_CLASS,
    UNSUPPORTED_ORDER_TYPE,
    ExecutionAdapterError,
)
from app.brokers.execution.types import ExecutionResult, ExecutionSubmission
from app.market_data.errors import MarketDataError
from app.market_data.service import MarketDataService

logger = logging.getLogger(__name__)

_SUPPORTED_ORDER_TYPES = frozenset({"market", "limit", "stop", "stop_limit"})
_SUPPORTED_ASSET_CLASSES = frozenset({"equity"})
_SUPPORTED_TIF = frozenset({"day", "gtc", "ioc", "fok"})


def _dec(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ExecutionAdapterError(f"Invalid decimal: {value!r}", code=MALFORMED_RESPONSE) from exc


def _parse_ts(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


class AlpacaPaperExecutionAdapter(BrokerExecutionAdapter):
    """Controlled paper order submission (POST /v2/orders only)."""

    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        base_url: str = ALPACA_PAPER_BASE_URL,
        timeout_seconds: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
        market_data_service: MarketDataService | None = None,
        skip_buying_power_check: bool = False,
    ) -> None:
        if not api_key or not api_secret:
            raise ExecutionAdapterError(
                "Alpaca paper credentials required",
                code=AUTHENTICATION_FAILED,
            )
        self._api_key = api_key
        self._api_secret = api_secret
        try:
            self._base_url = assert_paper_base_url(base_url)
        except Exception as exc:  # BrokerStateError or similar
            code = getattr(exc, "code", LIVE_BROKER_ACCESS_FORBIDDEN)
            raise ExecutionAdapterError(str(exc), code=code) from exc
        self._timeout = timeout_seconds
        self._transport = transport
        self._mds = market_data_service
        self._skip_bp = skip_buying_power_check
        self._submit_post_count = 0  # test observability

    @property
    def provider_name(self) -> str:
        return "alpaca"

    @property
    def submit_post_count(self) -> int:
        return self._submit_post_count

# Intentionally NO: cancel_order, cancel_all_orders, replace_order, modify_order, close_position
# Intentionally NO: public .client
# Lifecycle cancel is ``request_paper_cancel`` (single order id) for ControlledCancellationService only.

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self._api_key,
            "APCA-API-SECRET-KEY": self._api_secret,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _enforce_pipeline(self, submission: ExecutionSubmission) -> None:
        if not (
            submission.risk_approved
            and submission.validated
            and submission.routed
            and submission.proposal_status == "routed"
        ):
            raise ExecutionAdapterError(
                "Submission lacks risk/validation/routing proof",
                code=PIPELINE_PRECONDITION_FAILED,
            )
        if submission.broker.lower().strip() != "alpaca":
            raise ExecutionAdapterError(
                f"Adapter only accepts alpaca broker; got {submission.broker!r}",
                code=PIPELINE_PRECONDITION_FAILED,
            )
        if submission.trading_mode.lower().strip() != "paper":
            raise ExecutionAdapterError(
                "Live trading mode forbidden",
                code=LIVE_BROKER_ACCESS_FORBIDDEN,
            )
        if not submission.account_enabled:
            raise ExecutionAdapterError(
                "Broker account is disabled",
                code=BROKER_ACCOUNT_DISABLED,
            )
        if submission.asset_class.lower().strip() not in _SUPPORTED_ASSET_CLASSES:
            raise ExecutionAdapterError(
                f"Unsupported asset class: {submission.asset_class}",
                code=UNSUPPORTED_ASSET_CLASS,
            )
        ot = submission.order_type.lower().strip()
        if ot not in _SUPPORTED_ORDER_TYPES:
            raise ExecutionAdapterError(
                f"Unsupported order type: {submission.order_type}",
                code=UNSUPPORTED_ORDER_TYPE,
            )
        if not submission.client_order_id:
            raise ExecutionAdapterError(
                "client_order_id required for idempotency",
                code=PIPELINE_PRECONDITION_FAILED,
            )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        assert_paper_base_url(self._base_url)
        # Live host must never be used.
        if "api.alpaca.markets" in self._base_url and "paper-api" not in self._base_url:
            raise ExecutionAdapterError(
                "Live Alpaca endpoint forbidden",
                code=LIVE_BROKER_ACCESS_FORBIDDEN,
            )
        url = f"{self._base_url}{path}"
        logger.info(
            "alpaca_paper_execution_request",
            extra={
                "provider": self.provider_name,
                "method": method,
                "path": path,
                "params_keys": list((params or {}).keys()),
            },
        )
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                if method == "GET":
                    response = await client.get(url, headers=self._headers(), params=params)
                elif method == "POST":
                    if path != "/v2/orders":
                        raise ExecutionAdapterError(
                            f"POST only allowed for /v2/orders; got {path}",
                            code=SUBMIT_FORBIDDEN,
                        )
                    self._submit_post_count += 1
                    response = await client.post(url, headers=self._headers(), json=json_body)
                elif method == "DELETE":
                    # Exact single-order cancel only — never /v2/orders (cancel-all).
                    if path == "/v2/orders" or path.rstrip("/") == "/v2/orders":
                        raise ExecutionAdapterError(
                            "cancel_all_orders is forbidden",
                            code=SUBMIT_FORBIDDEN,
                        )
                    if not path.startswith("/v2/orders/"):
                        raise ExecutionAdapterError(
                            f"DELETE only allowed for /v2/orders/{{id}}; got {path}",
                            code=SUBMIT_FORBIDDEN,
                        )
                    rest = path[len("/v2/orders/") :]
                    if not rest or "/" in rest or rest.lower() in {"", "all"}:
                        raise ExecutionAdapterError(
                            "Invalid cancel path",
                            code=SUBMIT_FORBIDDEN,
                        )
                    response = await client.delete(url, headers=self._headers())
                else:
                    raise ExecutionAdapterError(
                        f"HTTP method {method} not allowed on execution adapter",
                        code=BROKER_UNAVAILABLE,
                    )
        except httpx.TimeoutException as exc:
            raise ExecutionAdapterError("Alpaca paper request timed out", code=NETWORK_TIMEOUT) from exc
        except httpx.HTTPError as exc:
            raise ExecutionAdapterError("Alpaca paper network error", code=BROKER_UNAVAILABLE) from exc

        if response.status_code in {401, 403}:
            raise ExecutionAdapterError("Alpaca authentication failed", code=AUTHENTICATION_FAILED)
        if response.status_code == 429:
            raise ExecutionAdapterError("Alpaca rate limited", code=RATE_LIMITED)
        if not response.content:
            data = None
        else:
            ctype = (response.headers.get("content-type") or "").lower()
            try:
                data = response.json()
            except ValueError as exc:
                # Alpaca returns plain-text "Not Found" on some 404s (client_order_id lookup).
                if response.status_code == 404:
                    data = {"message": response.text[:200]}
                elif response.status_code >= 400:
                    data = {"message": response.text[:200]}
                elif "json" not in ctype:
                    raise ExecutionAdapterError(
                        "Non-JSON Alpaca response",
                        code=MALFORMED_RESPONSE,
                    ) from exc
                else:
                    raise ExecutionAdapterError(
                        "Non-JSON Alpaca response",
                        code=MALFORMED_RESPONSE,
                    ) from exc
        return response.status_code, data

    async def _verify_paper_account(self) -> dict[str, Any]:
        status, data = await self._request("GET", "/v2/account")
        if status >= 400 or not isinstance(data, dict):
            raise ExecutionAdapterError(
                "Paper account verification failed",
                code=PAPER_ACCOUNT_NOT_VERIFIED,
            )
        if not data.get("id"):
            raise ExecutionAdapterError(
                "Paper account id missing",
                code=PAPER_ACCOUNT_NOT_VERIFIED,
            )
        if bool(data.get("account_blocked")):
            raise ExecutionAdapterError("Alpaca account is blocked", code=ACCOUNT_BLOCKED)
        if bool(data.get("trading_blocked")):
            raise ExecutionAdapterError("Alpaca trading is blocked", code=TRADING_BLOCKED)
        return data

    async def _lookup_by_client_order_id(self, client_order_id: str) -> dict[str, Any] | None:
        # Preferred endpoint (may 404 with plain text on some Alpaca paper deployments).
        status, data = await self._request(
            "GET",
            f"/v2/orders:by_client_order_id/{client_order_id}",
        )
        if status == 200 and isinstance(data, dict) and data.get("id"):
            return data
        if status not in {200, 404}:
            raise ExecutionAdapterError(
                "Unable to confirm existing client_order_id before submit",
                code=AMBIGUOUS_IDEMPOTENCY_STATE,
            )

        # Fallback: scan recent orders for matching client_order_id.
        status2, rows = await self._request(
            "GET",
            "/v2/orders",
            params={"status": "all", "limit": 100, "direction": "desc"},
        )
        if status2 >= 400 or not isinstance(rows, list):
            if status == 404:
                return None
            raise ExecutionAdapterError(
                "Unable to confirm existing client_order_id before submit",
                code=AMBIGUOUS_IDEMPOTENCY_STATE,
            )
        for row in rows:
            if isinstance(row, dict) and str(row.get("client_order_id") or "") == client_order_id:
                return row
        return None

    async def _buying_power_precheck(self, submission: ExecutionSubmission, account: dict[str, Any]) -> None:
        if self._skip_bp:
            return
        side = submission.side.lower()
        if side != "buy":
            return  # sell/cover: do not invent margin assumptions
        bp = _dec(account.get("buying_power"))
        if bp is None:
            raise ExecutionAdapterError(
                "Buying power unavailable from broker",
                code=INSUFFICIENT_BROKER_BUYING_POWER,
            )
        required: Decimal | None = None
        ot = submission.order_type.lower()
        if ot in {"limit", "stop_limit"} and submission.limit_price is not None:
            required = submission.quantity * submission.limit_price
        elif ot == "market":
            if self._mds is None:
                # Cannot reliably value market order without MDS — fail closed
                raise ExecutionAdapterError(
                    "Market order requires market data for buying-power estimate",
                    code=PRICE_UNAVAILABLE,
                )
            try:
                ref = await self._mds.get_reference_price(submission.symbol)
                required = submission.quantity * ref.price
            except MarketDataError as exc:
                code = STALE_MARKET_DATA if exc.code == "STALE_MARKET_DATA" else PRICE_UNAVAILABLE
                raise ExecutionAdapterError(exc.message, code=code) from exc
        elif ot == "stop" and submission.stop_price is not None:
            # Conservative estimate using stop trigger
            required = submission.quantity * submission.stop_price
        if required is not None and required > bp:
            raise ExecutionAdapterError(
                f"Insufficient buying power: need {required}, have {bp}",
                code=INSUFFICIENT_BROKER_BUYING_POWER,
            )

    async def _freshness_for_market(self, submission: ExecutionSubmission) -> None:
        if submission.order_type.lower() != "market":
            return
        if self._mds is None:
            raise ExecutionAdapterError(
                "Market order requires fresh market data service",
                code=PRICE_UNAVAILABLE,
            )
        try:
            await self._mds.get_reference_price(submission.symbol, enforce_freshness=True)
        except MarketDataError as exc:
            code = STALE_MARKET_DATA if exc.code == "STALE_MARKET_DATA" else PRICE_UNAVAILABLE
            raise ExecutionAdapterError(exc.message, code=code) from exc

    def _build_alpaca_body(self, submission: ExecutionSubmission) -> dict[str, Any]:
        tif = submission.time_in_force.lower().strip()
        if tif not in _SUPPORTED_TIF:
            tif = "day"
        ot = submission.order_type.lower()
        body: dict[str, Any] = {
            "symbol": submission.symbol.upper().strip(),
            "qty": str(submission.quantity),
            "side": submission.side.lower(),
            "type": ot if ot != "stop_limit" else "stop_limit",
            "time_in_force": tif,
            "client_order_id": submission.client_order_id,
        }
        if ot in {"limit", "stop_limit"}:
            if submission.limit_price is None:
                raise ExecutionAdapterError("limit_price required", code=PIPELINE_PRECONDITION_FAILED)
            body["limit_price"] = str(submission.limit_price)
        if ot in {"stop", "stop_limit"}:
            if submission.stop_price is None:
                raise ExecutionAdapterError("stop_price required", code=PIPELINE_PRECONDITION_FAILED)
            body["stop_price"] = str(submission.stop_price)
        return body

    def _to_result(self, data: dict[str, Any], *, recovered: bool, posts: int) -> ExecutionResult:
        oid = str(data.get("id") or "").strip()
        if not oid:
            raise ExecutionAdapterError("Broker order id missing", code=MALFORMED_RESPONSE)
        status = str(data.get("status") or "new").lower()
        return ExecutionResult(
            broker_order_id=oid,
            client_order_id=str(data.get("client_order_id") or ""),
            status=status,
            submitted_at=_parse_ts(data.get("submitted_at") or data.get("created_at")),
            filled_quantity=_dec(data.get("filled_qty")) or Decimal("0"),
            filled_avg_price=_dec(data.get("filled_avg_price")),
            recovered_existing=recovered,
            submit_http_calls=posts,
            raw_status=status,
            details={"alpaca": True, "paper": True},
        )

    async def submit_order(self, submission: ExecutionSubmission) -> ExecutionResult:
        self._enforce_pipeline(submission)
        assert_paper_base_url(self._base_url)

        posts_before = self._submit_post_count
        account = await self._verify_paper_account()
        await self._freshness_for_market(submission)
        await self._buying_power_precheck(submission, account)

        # Idempotency: existing client_order_id → return without POST
        existing = await self._lookup_by_client_order_id(submission.client_order_id)
        if existing is not None:
            return self._to_result(existing, recovered=True, posts=0)

        body = self._build_alpaca_body(submission)
        try:
            status, data = await self._request("POST", "/v2/orders", json_body=body)
        except ExecutionAdapterError as exc:
            if exc.code == NETWORK_TIMEOUT:
                # Response may have been lost after broker accept — recover
                recovered = await self._lookup_by_client_order_id(submission.client_order_id)
                if recovered is not None:
                    return self._to_result(
                        recovered,
                        recovered=True,
                        posts=self._submit_post_count - posts_before,
                    )
                raise ExecutionAdapterError(
                    "Timeout and client_order_id not found — ambiguous; not retrying",
                    code=AMBIGUOUS_IDEMPOTENCY_STATE,
                ) from exc
            raise

        posts = self._submit_post_count - posts_before
        if status in {200, 201} and isinstance(data, dict):
            return self._to_result(data, recovered=False, posts=posts)

        # Duplicate client_order_id race → fetch existing
        msg = ""
        if isinstance(data, dict):
            msg = str(data.get("message") or data.get("error") or "")
        if status == 422 or "client_order_id" in msg.lower():
            existing = await self._lookup_by_client_order_id(submission.client_order_id)
            if existing is not None:
                return self._to_result(existing, recovered=True, posts=posts)
        raise ExecutionAdapterError(
            f"Alpaca rejected order (HTTP {status}): {msg or 'unknown'}",
            code=ORDER_REJECTED_BY_BROKER,
        )

    async def get_order_by_id(self, broker_order_id: str) -> dict[str, Any]:
        """Read-only status sync helper (GET)."""
        status, data = await self._request("GET", f"/v2/orders/{broker_order_id}")
        if status >= 400 or not isinstance(data, dict):
            raise ExecutionAdapterError("Order status sync failed", code=BROKER_UNAVAILABLE)
        return data

    async def get_order_by_client_order_id(self, client_order_id: str) -> dict[str, Any] | None:
        return await self._lookup_by_client_order_id(client_order_id)

    async def get_fills_for_order(self, broker_order_id: str) -> list[dict[str, Any]]:
        """Fetch FILL activities for one order (durable activity ids when present)."""
        oid = (broker_order_id or "").strip()
        if not oid:
            return []
        status, data = await self._request(
            "GET",
            "/v2/account/activities",
            params={"activity_types": "FILL", "page_size": 100},
        )
        if status >= 400 or not isinstance(data, list):
            return []
        out: list[dict[str, Any]] = []
        for row in data:
            if not isinstance(row, dict):
                continue
            if str(row.get("order_id") or "") != oid:
                continue
            # Normalize durable id
            aid = str(row.get("id") or "").strip()
            if not aid:
                continue
            out.append(row)
        return out

    async def request_paper_cancel(self, broker_order_id: str) -> dict[str, Any]:
        """Lifecycle-only cancel of ONE paper order by broker id.

        Not a general ``cancel_order`` / ``cancel_all_orders`` API.
        Callers must be ControlledCancellationService (ownership already checked).
        """
        oid = (broker_order_id or "").strip()
        if not oid or "/" in oid:
            raise ExecutionAdapterError("Invalid broker_order_id", code=SUBMIT_FORBIDDEN)
        assert_paper_base_url(self._base_url)
        status, data = await self._request("DELETE", f"/v2/orders/{oid}")
        if status in {200, 204}:
            if isinstance(data, dict):
                return data
            # 204 empty — fetch current state
            return await self.get_order_by_id(oid)
        msg = ""
        if isinstance(data, dict):
            msg = str(data.get("message") or data.get("error") or "")
        raise ExecutionAdapterError(
            f"Paper cancel failed HTTP {status}: {msg or 'unknown'}",
            code=ORDER_REJECTED_BY_BROKER,
        )
