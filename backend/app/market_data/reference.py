"""Deterministic reference-price policy.

Precedence
----------
1. If both bid and ask are present and > 0: midpoint = (bid + ask) / 2
2. Else latest trade price
3. Else PRICE_UNAVAILABLE

Does not invent prices. Stale data is rejected by MarketDataService before
this policy runs (or flagged when skip_freshness is used in tests).
"""

from __future__ import annotations

from decimal import Decimal

from app.market_data.errors import PRICE_UNAVAILABLE, MarketDataError
from app.market_data.models import Quote, ReferencePrice, Trade


def resolve_reference_price(
    *,
    symbol: str,
    quote: Quote | None,
    trade: Trade | None,
    provider: str,
) -> ReferencePrice:
    if quote is not None and quote.bid_price is not None and quote.ask_price is not None:
        if quote.bid_price > 0 and quote.ask_price > 0:
            mid = (quote.bid_price + quote.ask_price) / Decimal("2")
            return ReferencePrice(
                symbol=symbol,
                price=mid,
                timestamp=quote.timestamp,
                provider=provider,
                source="midpoint",
            )

    if trade is not None and trade.price > 0:
        return ReferencePrice(
            symbol=symbol,
            price=trade.price,
            timestamp=trade.timestamp,
            provider=provider,
            source="last_trade",
        )

    raise MarketDataError(
        f"No reference price available for {symbol}",
        code=PRICE_UNAVAILABLE,
    )
