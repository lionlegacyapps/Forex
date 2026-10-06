"""Deterministic Alpaca-safe client_order_id from internal order UUID.

Alpaca limit: typically ≤ 48 characters. UUID hex + prefix fits.
"""

from __future__ import annotations

import re
import uuid

_CLIENT_ORDER_RE = re.compile(r"^o[0-9a-f]{32}$")


def build_client_order_id(internal_order_id: uuid.UUID) -> str:
    """Encode durable internal order UUID as broker client_order_id."""
    return f"o{internal_order_id.hex}"


def parse_client_order_id(client_order_id: str) -> uuid.UUID | None:
    """Reverse mapping when format matches; else None."""
    if not _CLIENT_ORDER_RE.match(client_order_id or ""):
        return None
    return uuid.UUID(hex=client_order_id[1:])
