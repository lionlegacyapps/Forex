# Authorized Paper Execute Activation V1

Tightly controlled `PAPER_EXECUTE` for qualified strategies. Submissions go only through:

```
Strategy → StrategyDecision → TradeProposal → Risk Engine → Order Validator → Broker Router → Alpaca Paper Adapter
```

**Default remains disabled.** Live trading is impossible. This milestone does **not** place real Alpaca orders (tests use `FakeExecutionAdapter`).

## Required configuration

| Setting | Default | Role |
|---|---|---|
| `PAPER_SESSION_EXECUTE_ENABLED` | `false` | Server-side feature gate |
| `PAPER_SESSION_EXECUTE_CONSENT_TTL_SECONDS` | `900` | Consent lifetime (1–86400) |
| `PAPER_QUALIFICATION_OWNER_SUBJECTS` | empty | Owner allowlist (fail-closed) |
| `ALPACA_PAPER_BASE_URL` | `https://paper-api.alpaca.markets` | Must be paper-api host |

Enabling the feature flag alone is **not** enough.

## Owner authorization

Uses the same server-side `resolve_authenticated_owner` path as qualification.
Client-supplied account-mode flags are never trusted as proof of paper status.

## Session-scoped consent

`PaperSessionService.grant_execution_consent` creates a durable
`paper_execution_authorizations` row:

- States: `granted` → `revoked` | `expired` | `consumed` (one-time)
- Bound to `session_id` + `broker_account_id`
- Fingerprint over session, account, owner, strategy version, parameter hash,
  evidence fingerprint, and verified paper base URL
- Short TTL; revocable; not reusable after revoke/expire/consume

`PAPER_EXECUTE` activation requires active consent. The runner rechecks consent
**immediately before** Broker Router submission.

## Paper endpoint verification

`verify_alpaca_paper_endpoint` rejects `api.alpaca.markets` (live) and any
non-`paper-api.alpaca.markets` host. Verification is server-side from settings
(and optional broker identity snapshot), never from client mode flags.

## Order lifecycle

1. Manual create (`PAPER_EXECUTE`) with feature enabled
2. Grant consent
3. Activate (qualification + risk limits + recon + buying power + paper endpoint)
4. `PaperSessionRunner.run_once` → decision → proposal → risk → validate
5. Consent recheck → max outstanding order check → `BrokerRouter.route_and_submit`
6. Persist outcome + Market Memory

No second execution path. No direct Alpaca calls from the session package.

## Idempotency

- Session bar ledger (`paper_session_processed_bars`)
- Router persists internal order **before** broker submit; `client_order_id` from order id
- Fake/Alpaca adapters recover existing `client_order_id` without a second POST
- Uncertain ACKs **never** blind-retry

## Uncertain acknowledgment recovery

On `NETWORK_TIMEOUT` / `AMBIGUOUS_IDEMPOTENCY_STATE`:

1. Mark session `submissions_blocked`
2. Reconcile local NEW orders via `client_order_id` fallback lookup
3. Leave block until operator `clear_submission_block` after inspection
4. Do not auto-resubmit

## Risk controls (fail-closed)

Session limits + Risk Engine + Validator +:

- One active strategy session per paper account
- One instrument per session
- Max one outstanding strategy-generated order
- Max orders / notional / position / daily loss / duration
- Fresh completed bars required

## Pause / stop / kill

| Action | Effect |
|---|---|
| Pause | No new decisions/orders |
| Stop | Ends lifecycle; revokes consent |
| Emergency kill | Revokes consent, blocks submissions, stops session; **does not** claim cancel/liquidate |

Operations are idempotent.

## Manual test procedure (future real paper — not this milestone)

1. Set `PAPER_SESSION_EXECUTE_ENABLED=true` in a private env (not commit)
2. Ensure owner allowlist + paper credentials + paper-api URL
3. Approve qualification for the strategy/version/hash
4. Create `PAPER_EXECUTE` session via service layer
5. Grant consent with short TTL
6. Activate; run one iteration under supervision
7. Verify Alpaca paper order; stop/kill; revoke consent
8. Set feature flag back to `false`

## Rollback

1. Keep `PAPER_SESSION_EXECUTE_ENABLED=false` (default)
2. Revoke any granted consents / emergency-kill sessions
3. Alembic downgrade `e2b5c9d41f6a` → `d1a4b8c30e5f` if needed (reversible)

## Out of scope

- Real Alpaca orders in CI/this milestone
- Always-on worker
- Multi-strategy orchestration
- Live trading
- Frontend / public start endpoints
