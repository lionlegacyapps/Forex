# Alpaca Paper Execution Adapter V1

**ALPACA PAPER EXECUTION DOES NOT ENABLE LIVE TRADING.**

## Order flow (mandatory)

```
Trade Proposal
→ Risk Engine
→ Order Validator
→ Broker Router
→ AlpacaPaperExecutionAdapter.submit_order
→ (read) status sync / fill accounting / reconciliation
```

There is no public HTTP execution endpoint and no direct strategy/AI path to Alpaca.

## Capability boundaries

| Capability | Component |
|---|---|
| Market data | `AlpacaMarketDataProvider` |
| Account/position/order **reads** | `AlpacaPaperAccountReader` |
| Paper order **submit** | `AlpacaPaperExecutionAdapter` (`submit_order` only) |
| Cancel / replace / live | **NOT IMPLEMENTED** |

## Paper-only enforcement

- Base URL hard-locked to `https://paper-api.alpaca.markets`
- Live host → `LIVE_BROKER_ACCESS_FORBIDDEN`
- Internal account must be `broker=alpaca`, `trading_mode=paper`, `is_enabled=true`
- Paper account verified via GET `/v2/account` before POST
- Account/trading blocked → reject

## Pipeline proof

`ExecutionSubmission` requires:

- `risk_approved`, `validated`, `routed` = true
- `proposal_status` = `routed`

Direct adapter misuse without proof fails closed (`PIPELINE_PRECONDITION_FAILED`).

## Idempotency / client_order_id

1. Persist internal `Order` (UUID) **before** broker POST
2. `client_order_id = o{order_uuid.hex}` (≤ 48 chars)
3. Lookup `GET /v2/orders:by_client_order_id/{id}` before POST
4. On timeout after POST: lookup again; return existing — **do not** double-submit

## Status sync & fills

After accept, router syncs broker order status and records fills into
`Execution` + `PositionAccountingService`. Broker fills are authoritative.
Reconciliation is observational (`mutations=0`).

## Buying power & freshness

- Pre-submit buying-power check for calculable buy notional
- Market orders require fresh `MarketDataService` reference price

## Mutating integration test

Requires **both**:

```
ALPACA_API_KEY / ALPACA_API_SECRET
ALLOW_ALPACA_PAPER_ORDER_TEST=true
```

Credentials alone are **not** permission to submit. Without the flag: SKIP.

The router does **not** auto-register `AlpacaPaperExecutionAdapter` from
credentials — execution adapters must be injected explicitly so market-data
keys cannot silently unlock order submission.
