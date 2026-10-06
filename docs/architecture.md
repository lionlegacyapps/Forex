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

See [market-data-provider-v1.md](./market-data-provider-v1.md).

Not implemented: real broker order execution, live trading, Tradovate,
automated strategies, AI, frontend.
