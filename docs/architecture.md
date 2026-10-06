# Architecture notes

## Order pipeline (mandatory — Safety Pipeline V1)

```
Trade Proposal → Risk Engine → Order Validator → Broker Router → Simulation Broker
```

**REAL BROKER EXECUTION IS NOT IMPLEMENTED.**

No trade execution component may bypass this path.

- Strategies / signals / AI emit **proposals only** (future).
- Risk evaluates strategy, account, and global limits (deterministic; no AI).
- Validation checks order shape and trading mode.
- Routing selects the broker adapter + account.
- V1 adapter: **SimulationBroker only** (zero network calls).
- Adapters never independently decide whether a trade is safe.

See [trading-safety-pipeline-v1.md](./trading-safety-pipeline-v1.md) for
reason codes, state transitions, and policy resolution.

## Fail-closed defaults

| Entity | Default mode | Default enabled |
|---|---|---|
| Broker account | `paper` | `false` |
| Strategy ↔ account assignment | `paper` | `false` |
| Risk policy `require_stop_loss` | — | `true` |

Operators must explicitly enable accounts and assignments before any trading path
can use them. Database constraints reinforce these defaults; they do **not**
replace the Risk Engine.

## Persistence

Application state belongs in **Supabase PostgreSQL**, not container
filesystems. The VPS is replaceable compute.

## Current scope

- Foundation + Version 1 database schema (hardened)
- Trading Safety Pipeline V1
- Paper Execution & Portfolio Accounting V1
- Market Data Provider V1 (read-only; Alpaca data API optional)
- Alpaca Paper Account Read-Path V1 (read-only paper account/positions/orders;
  observational reconciliation; **no** order execution)
- Alpaca Paper Execution Adapter V1 (controlled paper `submit_order` only via
  Risk → Validator → Router; **no** live trading)
- Alpaca Paper Order Lifecycle V1 (status sync, partial fills, controlled
  cancel, fill→accounting, reconciliation)

See [market-data-provider-v1.md](./market-data-provider-v1.md),
[alpaca-paper-account-read-path-v1.md](./alpaca-paper-account-read-path-v1.md),
[alpaca-paper-execution-adapter-v1.md](./alpaca-paper-execution-adapter-v1.md),
and [alpaca-paper-order-lifecycle-v1.md](./alpaca-paper-order-lifecycle-v1.md).

Not implemented: live trading, Tradovate, cancel-all, strategies, AI, frontend.
