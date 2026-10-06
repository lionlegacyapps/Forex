# Architecture notes

## Order pipeline (planned)

```
Trade Proposal → Risk Engine → Order Validator → Broker Router → Broker Adapter
```

- Strategies / signals / AI emit **proposals only**.
- Risk evaluates strategy, account, and global limits.
- Validation checks order shape and trading mode.
- Routing selects the broker adapter + account.
- Adapters talk to broker APIs; nothing else should.

## Persistence

Application state belongs in **Supabase PostgreSQL**, not container
filesystems. The VPS is replaceable compute.

## Current scope

Foundation plus **Version 1 database schema** (tables/models/migration only).
See [schema-v1.md](./schema-v1.md) for table details and ER diagram.

Not implemented yet: broker adapters, risk engine, execution, strategies,
market-data, AI, backtesting, or frontend.
