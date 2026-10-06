# Abandoned Live Schema Safety Reference (revision `0001`)

This document captures useful **trading-safety** characteristics discovered in the
abandoned/untracked Supabase development schema (Alembic revision `0001`) before
the controlled development reset that made the GitHub repository canonical.

It is an engineering reference only. It contains **no credentials**, connection
strings, hostnames, account IDs, or user/trading data.

At the time of capture, all application trading tables contained **0 rows**.

## Safety principles worth preserving

### Explicit enablement (fail closed)

- New **broker accounts** defaulted to `is_enabled = false` and `trading_mode = paper`.
- New **strategy ↔ account assignments** likewise defaulted disabled + paper.
- Implication: nothing is tradable until an operator explicitly enables it.

### Broker account classification

- `account_type` was **NOT NULL**, constrained to a small set
  (`cash`, `margin`, `futures`, `other`).
- Prefer requiring an explicit account type before any live path can use the account.

### Proposal stop semantics (do not conflate)

Two different concepts existed on trade proposals:

| Field | Meaning |
|---|---|
| `stop_price` | Trigger price when the **entry order itself** is stop / stop-limit |
| `stop_loss_price` | Protective **exit** level for the resulting position / trade plan |

These are not duplicates. The Risk Engine (future) may require a stop-loss without
forcing it at insert time for every proposal type.

### Order-level time in force

- Orders carried their own `time_in_force` (day / gtc / ioc / fok).
- Routed/broker orders must retain TIF independently of the originating proposal.

### Order ↔ proposal ↔ account consistency

- Live DB enforced a **composite foreign key**:
  `orders(trade_proposal_id, broker_account_id) → trade_proposals(id, broker_account_id)`.
- This prevents an order from referencing proposal A while pointing at a different
  broker account than that proposal.

### Risk policy defaults

- `require_stop_loss` defaulted to **true** (safer fail-closed posture).
- Scope uniqueness existed for global vs scoped policies.

### Useful CHECK invariants (examples)

- Positive quantities; non-negative prices / commissions where applicable.
- Enumerated sides, order types, trading modes, asset classes, statuses.
- Limit/stop price required when order type demands them.
- Position open/closed consistency (`open` ⇒ `closed_at` null and qty ≠ 0; etc.).
- Proposal `source=strategy` ⇒ `strategy_id` present.
- Risk scope_id null iff scope is global.

### Useful uniqueness (examples)

- `(broker, external_account_id)` on broker accounts.
- `(name, version)` on strategies.
- Assignment pair uniqueness (strategy + broker account).
- Broker order id uniqueness per broker account.
- Broker execution id uniqueness per order.
- Careful open-position identity that still allows multi-strategy same-symbol trading.

### Historical FK protection

- Trading history FKs used **ON DELETE RESTRICT** (strategies/accounts could not
  silently wipe proposals, orders, executions, positions, or market memory).
- Prefer RESTRICT (or future soft-delete) for historical entities; CASCADE only for
  pure configuration/junction rows when history is not erased.

## Pipeline reminder

Database constraints are **defense-in-depth**. They do not replace:

```
Trade Proposal → Risk Engine → Order Validator → Broker Router → Broker Adapter
```

No strategy, AI, signal, or integration may bypass that pipeline to place broker orders.

## Status after reset

The abandoned `0001` lineage was removed from the empty development database and
replaced by the GitHub canonical migration chain starting at `111d98cf92b8`, plus a
follow-up hardening migration that re-introduces the safety properties above into
the repository source of truth.
