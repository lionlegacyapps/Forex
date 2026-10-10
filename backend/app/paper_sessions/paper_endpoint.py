"""Server-side Alpaca paper endpoint verification.

Never trusts client-provided account-mode flags.
Live ``api.alpaca.markets`` is always rejected.
"""

from __future__ import annotations

import hashlib
from urllib.parse import urlparse

from app.core.config import Settings, get_settings
from app.paper_sessions.errors import ActivationRejectedError

PAPER_HOST = "paper-api.alpaca.markets"
LIVE_HOST = "api.alpaca.markets"


def verify_alpaca_paper_endpoint(
    base_url: str | None,
    *,
    settings: Settings | None = None,
) -> str:
    """Return normalized paper base URL or raise.

    Uses server settings when ``base_url`` is None. Rejects live hosts.
    """
    cfg = settings or get_settings()
    candidate = (base_url if base_url is not None else cfg.alpaca_paper_base_url) or ""
    cleaned = candidate.strip().rstrip("/")
    if not cleaned:
        raise ActivationRejectedError(
            "Alpaca paper base URL is required",
            code="paper_endpoint_missing",
        )
    parsed = urlparse(cleaned)
    host = (parsed.hostname or "").lower()
    if host == LIVE_HOST or (LIVE_HOST in host and PAPER_HOST not in host):
        raise ActivationRejectedError(
            "Live Alpaca trading endpoint is forbidden",
            code="live_endpoint_rejected",
        )
    if host != PAPER_HOST:
        raise ActivationRejectedError(
            f"Only Alpaca paper-api host is allowed; got host={host!r}",
            code="paper_endpoint_rejected",
        )
    if parsed.scheme not in {"https", ""}:
        raise ActivationRejectedError(
            "Alpaca paper endpoint must use https",
            code="paper_endpoint_rejected",
        )
    return cleaned


def paper_base_url_fingerprint(base_url: str) -> str:
    return hashlib.sha256(base_url.encode("utf-8")).hexdigest()
