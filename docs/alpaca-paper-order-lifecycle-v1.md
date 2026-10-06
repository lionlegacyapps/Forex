# Alpaca Paper Order Lifecycle V1

**ALL EXTERNAL EXECUTION REMAINS ALPACA PAPER ONLY.**

## Lifecycle

```
Trade Proposal → Risk → Validation → Router → Alpaca Paper Submission
  → OrderStatusSyncService
  → Partial Fill / Fill → Execution → PositionAccounting
  → Reconciliation
```

Controlled cancellation (exact order only):

```
CancellationRequest
→ ownership + paper checks
→ pre-sync (detect fill race)
→ request_paper_cancel(broker_order_id)
→ post-sync (broker authoritative)
→ reconcile
```

## Status mapping

| Alpaca | Internal `OrderStatus` | Conceptual |
|---|---|---|
| new / pending_new | `submitted` | pending |
| accepted | `submitted` | accepted |
| pending_cancel | `submitted` | cancel_pending |
| partially_filled | `partially_filled` | partially_filled |
| filled | `filled` | filled |
| canceled / cancelled / replaced | `cancelled` | cancelled |
| rejected | `rejected` | rejected |
| expired | `expired` | expired |

Illegal backward transitions from terminal states are refused; last valid state is kept.

## Partial fills

- Durable activity/fill IDs → one `Execution` per id (idempotent)
- Aggregate fallback uses **delta** qty only (`broker_filled − internal_filled`)
- Positions update incrementally via `PositionAccountingService`

## Cancellation rules

- Paper account only (`trading_mode=paper`, `broker=alpaca`)
- Requires matching `internal_order_id` + `broker_order_id` + `broker_account_id`
- No `cancel_all_orders` / liquidation / public cancel HTTP endpoint
- Adapter exposes `request_paper_cancel` (single id) for the lifecycle service only — **not** `cancel_order` / `cancel_all_orders`

## Cancel / fill race

If the broker fills before/during cancel:

1. cancel attempt may fail or return filled
2. sync records fills + accounting
3. order is marked **filled**, not cancelled

## Polling

`OrderStatusSyncService.poll_until_terminal` is bounded (`interval`, `timeout`, `max_iterations`). No infinite loops. Webhook/websocket interface exists as a no-op foundation; polling is sufficient for V1.

## Reconciliation

Detects status, fill-quantity, missing-execution, and position mismatches. Observational only (`mutations=0`).
