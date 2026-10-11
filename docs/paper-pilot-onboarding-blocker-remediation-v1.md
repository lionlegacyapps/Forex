# Paper Pilot Onboarding & Blocker Remediation V1

Resolve blockers for the first **supervised** Alpaca paper-trading pilot.  
**No broker orders. No live trading. `PAPER_SESSION_EXECUTE_ENABLED` stays false.**

## Safety invariants

| Control | Requirement |
|---|---|
| Real Alpaca paper orders | **0** |
| Live trading | **NO** |
| `PAPER_SESSION_EXECUTE_ENABLED` | **false** |
| Auto-approve qualification | **forbidden** |
| Owner allowlist empty | **fail closed** |
| API secrets in `broker_accounts` | **never** |

## Modules

| Module | Role |
|---|---|
| `app.onboarding.owner` | Allowlist status + `require_authenticated_owner` |
| `app.onboarding.account` | Verify paper-api identity + idempotent registration |
| `app.onboarding.market_data_check` | IEX/SIP feed access via Market Data Provider |
| `app.onboarding.qualification_evidence` | Walk-forward evidence for `sma_crossover@1.0.0` |
| `app.onboarding.workflow` | Fail-closed steps 1–10 orchestration |

## Owner allowlist (blocker 1)

`PAPER_QUALIFICATION_OWNER_SUBJECTS` must contain the **exact** subject that
`resolve_authenticated_owner(subject=..., credential_verified=True)` will receive
after server-side credential verification.

- Never invent a subject.
- Never hard-code identity in source.
- Never put tokens in the allowlist.
- Empty allowlist → fail closed.

Private `.env` only (see `.env.example`).

## Alpaca paper registration (blocker 2)

`verify_and_register_alpaca_paper_account`:

1. Requires authenticated owner.
2. Asserts host is exactly `paper-api.alpaca.markets`.
3. Reads account via `AlpacaPaperAccountReader` (paper_verified).
4. Registers via `register_alpaca_paper_account` (idempotent; secrets not stored).
5. Defaults `is_enabled=false` (connecting ≠ trading).

## Market data (blocker 4)

Root cause of prior `AUTHENTICATION_FAILED` on recent bars: default **SIP** feed
returns HTTP **403** without a SIP subscription (not a bad API key). Paper trading
API credentials can still authenticate market-data for **IEX**.

Fix:

- Default `ALPACA_DATA_FEED=iex`
- Map subscription/SIP 403 → `SUBSCRIPTION_FORBIDDEN`
- Keep true 401 → `AUTHENTICATION_FAILED`

## Strategy qualification (blocker 3)

`prepare_sma_crossover_qualification`:

- Parameters: aligned with `default_pilot_config()` — `fast_period=3`, `slow_period=5`, `quantity=1`
- Nonzero costs: commission `0.005`/share + `5` bps slippage
- Rolling walk-forward; reproducible dataset + parameter hashes
- Creates draft + submits evidence only — **never calls approve()**

Owner must manually review findings, then call
`PaperQualificationService.approve(...)` when ready.

## Workflow steps

1. Verify allowlist configured  
2. Authenticate owner against allowlist  
3. Verify Alpaca paper account  
4. Register/update `broker_accounts` (PAPER)  
5. Verify market-data access (completed bars)  
6. Generate qualification evidence  
7. Present findings  
8. **Manual** qualification approval (not automated)  
9. Read-only preflight — blocked until approval  
10. One DRY_RUN — blocked until approval + separate invocation  

Every missing prerequisite **fails closed**.

## Operator quick start

```bash
# Private .env — never commit real values
PAPER_SESSION_EXECUTE_ENABLED=false
PAPER_QUALIFICATION_OWNER_SUBJECTS=<exact-authenticated-subject>
ALPACA_DATA_FEED=iex
ALPACA_PAPER_BASE_URL=https://paper-api.alpaca.markets
ALPACA_DATA_BASE_URL=https://data.alpaca.markets
ALPACA_API_KEY=...
ALPACA_API_SECRET=...
```

Then invoke `PaperPilotOnboardingWorkflow.run(...)` from a trusted server context
with `credential_verified=True` and the matching subject.

After evidence is eligible and owner approves:

1. Enable paper `BrokerAccount` explicitly if still disabled  
2. Run `PilotPreflightService` (read-only)  
3. Run `ControlledDryRunPilot` with `PAPER_SESSION_EXECUTE_ENABLED=false`  
4. Only after a separate written owner decision: consider execute activation (out of scope)

## Related docs

- `docs/supervised-paper-pilot-preparation-v1.md`
- `docs/supervised-paper-pilot-operator-runbook.md`
- `docs/paper-strategy-qualification-gate-v1.md`
- `docs/market-data-provider-v1.md`
