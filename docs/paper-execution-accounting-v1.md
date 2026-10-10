# Paper Execution & Portfolio Accounting V1

**SIMULATION RESULTS DO NOT REPRESENT REAL MARKET EXECUTION.**

## Loop

```
Trade Proposal → Risk Engine → Order Validator → Broker Router
→ Simulation Broker → Order → Execution/Fill → Position Accounting
→ P&L / Exposure → Risk Engine
```

## Simulation market data

`SimulationMarketData` holds explicitly configured Decimal prices only.

- `set_price("AAPL", Decimal("200"))`
- Missing price → `PRICE_UNAVAILABLE` (no fill, no fabricated quote)
- No network, no randomness

## Order trigger logic (full fills only)

| Type | BUY fills when | SELL fills when |
|---|---|---|
| MARKET | price available | price available |
| LIMIT | market ≤ limit | market ≥ limit |
| STOP | market ≥ stop | market ≤ stop |
| STOP_LIMIT | stop triggered **and** limit marketable | same |

No book depth, slippage, latency, or partial liquidity in V1.

## Order lifecycle (schema vocabulary)

`new → submitted → filled` (and `cancelled` / `rejected` / `expired`).

Conceptual “accepted” maps to **`submitted`** (no separate DB status).
Illegal transitions raise `INVALID_STATE_TRANSITION`.

## Position accounting

`PositionAccountingService` (not inside SimulationBroker):

- Identity: `broker_account_id` + `strategy_id` + `symbol` + `asset_class`
- Quantity sign: **long > 0**, **short < 0**
- Weighted average on same-direction adds
- Realized PnL on reduce/close; reversals close then open opposite
- Execution idempotency via `executions.accounting_applied`

## P&L

- Realized: attributed per fill on `executions.realized_pnl`
- Unrealized: only when a mark price exists; otherwise **unknown**
  (`current_price = NULL` — do not treat stored `0` as evaluated)

## Exposure

Gross notional = Σ \|qty\| × sim price for open positions.
Incomplete if any required price missing (`NOT_EVALUATED_PRICE_REQUIRED`).

## Daily realized P&L

Sum of `execution.realized_pnl` for the trading day in configurable
`TRADING_DAY_TIMEZONE` (default `America/New_York`).

## Buying power (simplified)

In-process cash ledger; default starting cash `100000`.
V1: buying power == cash. **Not** a real margin model.

## Transactions / fail-closed

Fill + execution insert + position update run in the caller’s DB transaction
(test sessions roll back; app sessions must commit as a unit). Failures must
not leave orphan fills without accounting (or the reverse).

## Limitations vs real brokers

No real venues, no latency, no partials from liquidity, no fees beyond
optional commission field (default 0), no margin, no live data.

REAL BROKER EXECUTION IS NOT IMPLEMENTED.
