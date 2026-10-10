# Market Data Provider V1

**ALPACA MARKET DATA ACCESS DOES NOT ENABLE ALPACA ORDER EXECUTION.**

## Architecture

```
Market Data Consumer
→ MarketDataService
→ MarketDataProvider
→ SimulationMarketDataProvider | FakeMarketDataProvider | AlpacaMarketDataProvider
```

`BrokerAdapter` remains separate. Market-data modules must never implement
`place_order` / `cancel_order` / `modify_order`.

## Providers

| Provider | Network | Purpose |
|---|---|---|
| `SimulationMarketDataProvider` | No | Wraps deterministic `SimulationMarketData` board |
| `FakeMarketDataProvider` | No | Unit-test injection |
| `AlpacaMarketDataProvider` | Yes (data API only) | Equity quotes/trades/bars via httpx |

Alpaca V1 supports **equity** market data only. Futures/options/crypto routing
is reserved; unsupported classes raise `UNSUPPORTED_ASSET_CLASS`.

## Reference price

1. If bid and ask both present and > 0 → midpoint `(bid+ask)/2`
2. Else latest trade price
3. Else `PRICE_UNAVAILABLE`

## Freshness

Configurable:

- `MARKET_DATA_QUOTE_MAX_AGE_SECONDS` (default 30)
- `MARKET_DATA_TRADE_MAX_AGE_SECONDS` (default 60)

Exceeded → `STALE_MARKET_DATA` (not treated as valid).

## Risk / Exposure integration

Risk Engine and ExposureService may consume `MarketDataService` (sync path for
in-memory providers). When a **configured** financial limit requires a price and
reliable data cannot be obtained → **fail-closed reject** (never PASS).

Paper/simulation regression continues to use `SimulationMarketData`.

## Credentials

```
ALPACA_API_KEY=
ALPACA_API_SECRET=
ALPACA_DATA_BASE_URL=https://data.alpaca.markets
```

Never commit or log secrets. Optional integration test skips without credentials.

## Persistence

Quotes/trades are **not** written to PostgreSQL in this milestone.
