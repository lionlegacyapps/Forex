# Operator Runbook — Future Separately Authorized Alpaca Paper Pilot

This runbook is for a **future** real Alpaca paper-order pilot.  
**Pilot Preparation V1 does not authorize or perform any real paper submission.**

---

## 0. Approval checkpoint (mandatory)

> **STOP — SEPARATE EXPLICIT OWNER DECISION REQUIRED**
>
> Before any real Alpaca `POST /v2/orders` call:
>
> 1. Pilot Preparation V1 must be `PASS`.
> 2. Preflight report must be `ok=true` on the same day.
> 3. Owner allowlist subject must authenticate server-side.
> 4. Owner must explicitly set `PAPER_SESSION_EXECUTE_ENABLED=true` in a
>    private, non-committed environment (never in git).
> 5. Owner must grant session-scoped consent with a short TTL.
> 6. Owner must confirm in writing (ticket/chat) the exact
>    strategy/version/parameter hash/symbol/quantity/account.
> 7. Maximum **one** order for the session.
>
> Without all of the above, **abort**. Preparation code paths must remain
> the default.

---

## 1. Required environment configuration

```bash
# Deployment / shared .env — KEEP FALSE
PAPER_SESSION_EXECUTE_ENABLED=false
PAPER_SESSION_EXECUTE_CONSENT_TTL_SECONDS=900
PAPER_QUALIFICATION_OWNER_SUBJECTS=owner@example.com
ALPACA_PAPER_BASE_URL=https://paper-api.alpaca.markets
# Keys only in private operator env — never commit, never log
ALPACA_API_KEY=...
ALPACA_API_SECRET=...
ALLOW_ALPACA_PAPER_ORDER_TEST=false
```

Confirm Alembic head is `e2b5c9d41f6a`.

## 2. Owner authentication

Use server-side `resolve_authenticated_owner` with verified credentials and
allowlist membership. Never accept a client-supplied user id alone.

## 3. Strategy qualification

1. Evaluate `sma_crossover@1.0.0` (or chosen first-party strategy) offline.
2. Produce evidence fingerprint + parameter hash.
3. Owner approves `APPROVED_FOR_PAPER` / `PAPER_ONLY` via qualification service.
4. Confirm non-expired approval.

## 4. Broker account verification

- `BrokerAccount.trading_mode == paper`
- `is_enabled == true`
- Broker slug `alpaca`
- External account id matches paper-api identity read
- Endpoint host is exactly `paper-api.alpaca.markets`

## 5. Risk-limit verification

Pilot limits (or stricter):

| Limit | Value |
|---|---|
| Max quantity | 1 |
| Max notional | ≤ 500 |
| Max daily loss | ≤ 100 |
| Max orders / session | 1 |
| Max outstanding | 1 |
| Max concurrent positions | 1 |
| Max session duration | ≤ 3600s |

Missing limits → fail closed.

## 6. Manual session creation

Service layer only (`PaperSessionService.create_session`).  
No public HTTP start endpoint. No auto-start on deploy/restart.

Mode for the **future** real pilot: `paper_execute` (only after §0).  
Preparation uses `dry_run`.

## 7. Preflight checks

```text
PilotPreflightService.run(...) → report.ok must be true
```

Covers: owner, qualification, consent (when required), paper endpoint,
account identity, buying power, positions/orders, fresh bars, idempotency
ledger, migration, kill-switch readiness.

If any required check fails → **stop**.

## 8. Dry-run procedure

```text
ControlledDryRunPilot.run(...)  # DRY_RUN, zero broker POSTs
```

Inspect decision. If `NO_ACTION`, do not invent a signal.

## 9. Explicit paper-execution consent

```text
PaperSessionService.grant_execution_consent(session_id, owner=..., expires_in_seconds=≤900)
```

Revocable. Non-reusable after revoke/expire/consume.

## 10. One-order maximum enforcement

`max_orders_per_session=1` and runner `max_outstanding_orders=1`.  
Second strategy-generated order while one is open must be rejected.

## 11. Order status monitoring

Use existing Order Lifecycle sync (bounded poll) — status, fills, rejects.
Do not build a second pipeline.

## 12. Partial-fill handling

Record fills via fill sync / accounting. Do not open additional orders to
“complete” size in the pilot.

## 13. Account-scoped cancellation

Cancel only the exact paper order id for this session’s order.  
Never cancel-all. Never touch unrelated orders.

## 14. Emergency kill

```text
PaperSessionService.emergency_kill(session_id, owner=...)
```

Effects: revoke consent, block submissions, stop session.  
**Does not** claim orders cancelled or positions liquidated.

## 15. Post-session reconciliation

Read broker positions/orders; observational reconcile; resolve any uncertain
local NEW orders by `client_order_id` before considering retry (pilot: do not
retry — end session).

## 16. Final audit report

Collect:

- Audit events (`PAPER_SESSION_*`, `PAPER_EXECUTE_CONSENT_*`, Alpaca paper events)
- Market Memory `paper_session_event` rows
- Preflight JSON
- Order id / broker order id / fills
- Kill / stop reasons

## 17. Safe rollback and recovery

1. Set `PAPER_SESSION_EXECUTE_ENABLED=false`.
2. Emergency-kill any running pilot session.
3. Revoke consents.
4. Clear worker leases (`recover_stale_lease`) — does not auto-restart.
5. Optionally Alembic downgrade only if rolling back schema (not required for
   operational abort).

---

## Kill-switch semantics (rehearsed in simulation)

| Claim | True? |
|---|---|
| Further strategy submissions disabled | Yes |
| Consent revoked | Yes |
| Already accepted orders cancelled | **No guarantee** |
| Positions liquidated | **No** |
| Unrelated account orders cancelled | **No** |
