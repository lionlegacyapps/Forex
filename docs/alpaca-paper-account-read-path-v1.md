# Alpaca Paper Account Read-Path V1

**CONNECTING AN ALPACA ACCOUNT DOES NOT AUTHORIZE TRADING.**

## Capability separation

| Capability | Component | Status |
|---|---|---|
| Read market data | `AlpacaMarketDataProvider` | Implemented (Market Data V1) |
| Read paper account state | `AlpacaPaperAccountReader` | Implemented (this milestone) |
| Place/cancel/modify orders | `AlpacaPaperExecutionAdapter` | **NOT IMPLEMENTED** |

```
Consumer
→ BrokerStateService
→ BrokerAccountReader
→ AlpacaPaperAccountReader
→ https://paper-api.alpaca.markets  (GET only)
```

`BrokerAdapter` (SimulationBroker) remains the simulation execution path.
Alpaca paper read-path is **not** an execution adapter.

## Paper-only lock

- Base URL hard-locked to `https://paper-api.alpaca.markets`
- `https://api.alpaca.markets` (live) → `LIVE_BROKER_ACCESS_FORBIDDEN`
- Successful `/v2/account` from paper host → `paper_verified=True`
- If paper cannot be verified → `PAPER_ACCOUNT_NOT_VERIFIED` (fail closed)

## Read operations

| Operation | Endpoint (GET) |
|---|---|
| Account snapshot | `/v2/account` |
| Positions | `/v2/positions` |
| Orders / open orders | `/v2/orders` |
| Order by id | `/v2/orders/{id}` |
| Trade/fill activity | `/v2/account/activities?activity_types=FILL` |

**Write HTTP methods (POST/PUT/PATCH/DELETE): ZERO**

Forbidden application methods: `place_order`, `submit_order`, `cancel_order`,
`cancel_all_orders`, `replace_order`, `modify_order`, `close_position`,
`close_all_positions`, `liquidate`.

Raw Alpaca SDK `TradingClient` is **not** used or exposed.

## Reconciliation V1

`ReconciliationEngine` compares internal DB positions/orders against broker
snapshots and returns a `ReconciliationReport`.

- Observational only
- `mutations` always `0`
- Does **not** create/cancel broker orders
- Does **not** overwrite internal positions

## Account registration

`register_alpaca_paper_account` links `broker_accounts` to a verified paper
account via `broker=alpaca` + `external_account_id`.

- Credentials are **never** stored on the row
- `trading_mode=paper`
- `is_enabled=false` by default

## Credentials

```
ALPACA_API_KEY=
ALPACA_API_SECRET=
ALPACA_PAPER_BASE_URL=https://paper-api.alpaca.markets
```

Never commit or log secrets.

## Risk Engine foundation

`RiskEngine` may accept an optional `VerifiedBrokerState` for future
buying-power / open-order awareness. V1 does **not** replace internal
accounting with broker values and does **not** enable execution.
