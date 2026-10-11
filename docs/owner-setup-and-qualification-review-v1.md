# Owner Setup & Strategy Qualification Review V1

Operator guide for non-programmers.  
**No strategy auto-approval. No account enablement. No broker orders.**  
Keep `PAPER_SESSION_EXECUTE_ENABLED=false`.

## What is already true

| Item | Status |
|---|---|
| Branch ancestry includes onboarding + pilot preparation | Yes |
| Alembic head | `e2b5c9d41f6a` |
| Qualification `b46aa6ab-dcb4-41d7-b3e0-d4d5667d0573` | Present (`review_required`) |
| Alpaca paper identity (masked) | Verified separately (`7f21…6b5f`) |
| IEX market data | Working |
| Owner allowlist | Empty until you complete setup |
| Broker account row | Not registered until owner auth succeeds |

## Missing piece (why setup was blocked)

The platform authorize path (`resolve_authenticated_owner`) requires a
**server-verified** owner subject. There was no login integration that produced
that subject safely.

**Smallest safe fix added:** Supabase Auth verification
(`app.onboarding.supabase_owner`) + guided CLI
(`python -m app.onboarding.owner_setup_cli`).

## Phase A — Owner setup (you must do this)

1. Confirm the private file `.env` exists at the **repository root**  
   (copy from `.env.example` if needed). Never commit `.env`.
2. Confirm these lines are already filled (values stay private):
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
   - `ALPACA_API_KEY` / `ALPACA_API_SECRET`
   - `PAPER_SESSION_EXECUTE_ENABLED=false`
3. Open a terminal in the repository and run:

```bash
cd backend
.venv/bin/python -m app.onboarding.owner_setup_cli
```

4. Choose **1** (email + password).
5. Enter your **real Supabase login** email and password for this project.  
   Do not invent an email that was never signed up.
6. On success the tool writes only:

```bash
PAPER_QUALIFICATION_OWNER_SUBJECTS=<your-verified-email>
```

7. If an API server is running, restart it.

Owner setup is **PASS** only after the CLI prints verification success.

## Phase B — Read the qualification report

Open:

- `docs/reports/sma-crossover-qualification-report.md`
- `/opt/cursor/artifacts/sma-crossover-qualification-report.md` (agent artifact copy)

This report is **historical evidence only**. It is not a promise of future profit.  
The strategy is **not approved** until you explicitly approve it.

## Phase C — Broker registration (after owner setup PASS)

Only after owner setup succeeds, from `backend/`:

```bash
.venv/bin/python -m app.onboarding.register_paper_account_cli
```

This registers the verified Alpaca **paper** account with `is_enabled=false`.  
Connecting is not trading. Do not enable the account yet.

## Phase D — Manual approval checkpoint (stop before running unless you decide)

Approval binds to:

| Field | Value |
|---|---|
| qualification_id | `b46aa6ab-dcb4-41d7-b3e0-d4d5667d0573` |
| strategy | `sma_crossover@1.0.0` |
| parameter_hash | `0dffa427614c01c848fdf24980b562da3ce3b88293ff8fc8fad2030ed7c4ec47` |
| evidence_fingerprint | `cfcfdfe72d9fa2b94797f155e3bfa8e0f8a074f730f1f3c803adf307a9c97154` |

Service call (not executed by this milestone):

`PaperQualificationService.approve(qualification_id, owner=<AuthenticatedOwner>)`

Hard blockers: **none** → approval is allowed by policy **only after your decision**.  
No unsafe override path is offered.

See the approval snippet in the report appendix / FINAL REPORT from the agent run.

## Phase E — DRY_RUN readiness

After owner setup + registration + your approval + separate account enablement:

1. Confirm IEX data still works.
2. Confirm completed bars are fresh enough for a session day.
3. Run read-only `PilotPreflightService`.
4. Run one `ControlledDryRunPilot` with execute still **false**.

This milestone **stops before** approval, enablement, and DRY_RUN start.

## Safety reminders

- Never put passwords or tokens into git.
- Never set `PAPER_SESSION_EXECUTE_ENABLED=true` here.
- Never approve from a public HTTP endpoint (none is exposed).
- Live Alpaca trading remains forbidden by code.
