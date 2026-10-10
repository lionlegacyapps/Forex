# Paper Strategy Qualification Gate V1

Evidence-based **manual** approval workflow for paper-session eligibility.

**Qualification is not execution.** This gate does not start strategies, create
broker orders, activate sessions, enable accounts, or permit live trading.

## Qualification states

| State | Meaning |
|---|---|
| `draft` | Record created; no evidence yet |
| `evaluation_required` | Walk-forward evidence must be submitted |
| `evaluated` | Evidence reviewed; recommendation recorded |
| `review_required` | Eligible for owner review (no hard blockers) |
| `approved_for_paper` | Owner approved; **PAPER_ONLY** scope |
| `rejected` | Owner rejected (or not eligible) |
| `revoked` | Prior approval manually revoked |
| `expired` | Approval TTL elapsed |

Illegal transitions raise `IllegalTransitionError`. New records default to `draft`
(unapproved). Approval **never** implies live-trading permission.

## Evidence requirements

Configurable via `QualificationCriteria` (`paper_qualification_policy_v1`).

Conservative **example** defaults (not profitability claims):

| Gate | Default | Severity |
|---|---|---|
| Min OOS trades | 10 | Hard blocker |
| Min OOS windows | 1 | Hard blocker |
| Max drawdown (abs) | 50000 | Hard blocker |
| Non-zero costs | required | Hard blocker |
| Reproducibility metadata | required | Hard blocker |
| Negative OOS PnL | warn | Warning |
| Profit factor &lt; 1 | warn | Warning |

Recommendations: `eligible_for_review` | `insufficient_evidence` | `reject_recommended`.

Hard blockers are never silently waived.

## Approval workflow

1. `create_draft` (idempotent on evidence binding)
2. Submit walk-forward evidence → evaluate → `review_required` if eligible
3. Owner calls `approve` with `AuthenticatedOwner` from
   `resolve_authenticated_owner(subject=…, credential_verified=True)`
4. Approval records actor, timestamps, hashes, policy version, PAPER_ONLY scope, expiry
5. Audit event `PAPER_QUALIFICATION_APPROVED` appended

**No public HTTP approval endpoint** is exposed in V1.

### Authorization model

- Owner allowlist: `PAPER_QUALIFICATION_OWNER_SUBJECTS` (comma-separated)
- Empty allowlist → fail closed
- `credential_verified` must be True (server-side auth already succeeded)
- Client-supplied identity alone is never trusted

## Invalidation rules

Eligibility / approval is invalidated when:

- Strategy version changes
- Parameter hash changes
- Evidence fingerprint changes
- Policy version changes incompatibly
- Approval expires
- Owner revokes

Previously approved evidence cannot authorize a different configuration
(unique binding on strategy + version + parameter hash + evidence fingerprint).

Revoked approvals are not silently reactivated; re-approval requires current
evidence and a new explicit owner decision.

## Persistence

Table `strategy_paper_qualifications` (Alembic `c9e3f1b20a4d`):

- Durable current state + optimistic `state_version`
- JSONB report / blockers / warnings
- CHECK: `approval_scope = paper_only`
- Immutable audit history via `audit_events`

## Paper-session eligibility contract

`PaperEligibilityService.check(...)` is read-only for a future session runner.

Validates: approval state, strategy version, parameter hash, evidence fingerprint,
expiration, PAPER_ONLY scope, broker account identity, account paper mode.

Returns `account_enabled_by_check=False`, `orders_authorized_by_check=False`,
`live_trading_authorized=False` always. Does **not** enable accounts or place orders.
Risk Engine + Broker Router checks remain mandatory.

## Security limitations

- V1 has no end-user JWT/session framework; callers must supply a
  server-verified owner context.
- No UI. No public approve API.
- Live trading remains impossible through this gate.

## Future integration

A paper-session runner should:

1. Call `PaperEligibilityService.check`
2. Confirm account enabled separately (operator action)
3. Still pass Risk → Validator → Router for every order
