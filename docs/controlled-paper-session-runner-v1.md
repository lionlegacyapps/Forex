# Controlled Paper Session Runner V1

Manually activated, durable paper-session runner. **DRY_RUN by default.**
Does not auto-start on deploy/restart. Does not expose public start endpoints.
Live trading is impossible. **PAPER_EXECUTE activation is disabled in V1.**

## Session lifecycle

```
CREATED → READY → RUNNING ⇄ PAUSED
                 ↓
              STOPPING → STOPPED
                 ↘ FAILED
```

New sessions default to `CREATED` (inactive).

## Manual activation

Service-layer only (`PaperSessionService.activate`):

1. Authenticated owner (`resolve_authenticated_owner`)
2. Paper-only qualification eligibility (non-expired, matching hashes)
3. Enabled paper broker account
4. Session risk limits present
5. Pre-activation broker reconciliation (read-only snapshots)
6. No conflicting active session on the account

## DRY_RUN vs PAPER_EXECUTE

| Mode | Behavior |
|---|---|
| `dry_run` (default) | Evaluate strategy → proposal → risk → validate → **never submit** |
| `paper_execute` | Structured path exists but **activation is disabled** in V1 |

`PAPER_SESSION_EXECUTE_ENABLED=false` by default.

## Qualification requirements

Uses `PaperEligibilityService.check` with exact strategy version, parameter hash,
evidence fingerprint, PAPER_ONLY scope, and expiration.

## Risk checks

Session risk limits (fail-closed if missing):

- max position size / notional
- max daily loss
- max orders per session
- max concurrent positions
- allowed instrument
- market-data freshness
- max session duration
- stop-loss preference (Risk Engine still authoritative)

Plus existing Risk Engine + Order Validator for every proposal.

## Idempotency

Key = hash(session_id, strategy_id/version, account, instrument, bar_ts, decision_identity).

Ledger: `paper_session_processed_bars`. Duplicate bars/decisions are skipped.
Never blindly resubmits.

## Broker reconciliation

Before activation: identity, paper verification, conflicting positions/orders,
observational reconciliation findings. Rejects unsafe activation.

During execution: DRY_RUN does not call Broker Router submit. Future PAPER_EXECUTE
must reconcile uncertain acknowledgments before retry (not enabled in V1).

## Pause / stop / kill

- **Pause**: no new decisions/orders
- **Stop**: ends lifecycle; does not claim orders/positions cleared
- **Emergency kill**: disables further submissions for **this session only**;
  explicitly does **not** claim cancellation/liquidation of existing orders/positions

## Worker crash recovery

Expiring worker leases (`worker_lease_owner` / `worker_lease_expires_at`).
`recover_stale_lease` clears expired leases. **Does not auto-restart sessions.**

## Market Memory

Events: `paper_session_event` with session identity, decisions, pipeline results,
and state transitions. No strategy retraining.

## Persistence

Migration `d1a4b8c30e5f` (reversible):

- `paper_trading_sessions`
- `paper_session_processed_bars`

One active (non-terminal) session per paper account (partial unique index).

## Future multi-strategy

V1 rejects conflicting active assignments on the same account. Multi-strategy
orchestration is out of scope.
