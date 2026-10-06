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

Foundation only: FastAPI health, config, DB session wiring, Alembic
bootstrap, abstract broker contract, empty module packages.
