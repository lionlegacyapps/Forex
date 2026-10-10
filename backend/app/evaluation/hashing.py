"""Canonical hashes for evaluation reproducibility."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.market_data.models import Bar


def _json_default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"unserializable type: {type(obj)!r}")


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=_json_default)


def sha256_hex(payload: str | bytes) -> str:
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    return hashlib.sha256(raw).hexdigest()


def configuration_hash(parameters: dict[str, Any], *, extras: dict[str, Any] | None = None) -> str:
    body = {"parameters": parameters or {}, "extras": extras or {}}
    return sha256_hex(canonical_json(body))


def dataset_fingerprint(
    bars: list[Bar],
    *,
    symbol: str,
    timeframe: str,
) -> str:
    """Fingerprint OHLCV series without storing the full dataset in memory events."""
    rows = [
        {
            "t": b.timestamp.isoformat(),
            "o": str(b.open),
            "h": str(b.high),
            "l": str(b.low),
            "c": str(b.close),
            "v": None if b.volume is None else str(b.volume),
        }
        for b in bars
    ]
    body = {
        "symbol": symbol.strip().upper(),
        "timeframe": timeframe,
        "n": len(rows),
        "rows": rows,
    }
    return sha256_hex(canonical_json(body))


def evaluation_identity(
    *,
    strategy_id: str,
    strategy_version: str,
    configuration_hash: str,
    dataset_fingerprint: str,
    execution_assumptions: dict[str, Any],
    cost_assumptions: dict[str, Any],
) -> str:
    """Stable identity independent of wall-clock evaluation timestamp."""
    body = {
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "configuration_hash": configuration_hash,
        "dataset_fingerprint": dataset_fingerprint,
        "execution_assumptions": execution_assumptions or {},
        "cost_assumptions": cost_assumptions or {},
    }
    return sha256_hex(canonical_json(body))
