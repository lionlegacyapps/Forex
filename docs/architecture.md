# Architecture notes

## Order pipeline (planned — mandatory)

```
Trade Proposal → Risk Engine → Order Validator → Broker Router → Broker Adapter
```

No trade execution component may bypass this path.

- Strategies / signals / AI emit **proposals only**.
- Risk evaluates strategy, account, and global limits.
- Validation checks order shape and trading mode.
- Routing selects the broker adapter + account.
- Adapters talk to broker APIs; nothing else should.

## Fail-closed defaults

| Entity | Default mode | Default enabled |
|---|---|---|
| Broker account | `paper` | `false` |
| Strategy ↔ account assignment | `paper` | `false` |
| Risk policy `require_stop_loss` | — | `true` |

Operators must explicitly enable accounts and assignments before any trading path
can use them. Database constraints reinforce these defaults; they do **not**
replace the future Risk Engine.

## Persistence

Application state belongs in **Supabase PostgreSQL**, not container
filesystems. The VPS is replaceable compute.

## Current scope

Foundation plus **Version 1 database schema** (tables / models / migrations /
hardening). See [schema-v1.md](./schema-v1.md).

Not implemented yet: broker adapters, risk engine, execution, strategies,
market-data, AI, backtesting, or frontend.
