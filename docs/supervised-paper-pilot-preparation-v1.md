# Supervised Single-Strategy Paper Pilot — Preparation V1

Preparation and simulation only. **No real Alpaca paper orders.**  
`PAPER_SESSION_EXECUTE_ENABLED` remains **false** in deployment.  
No always-on worker. No live trading. No frontend.

## Repository integrity

| Item | Status |
|---|---|
| PR #20 (Authorized Paper Execute) | Includes consent + session runner ancestry |
| Migration head | `e2b5c9d41f6a` (revises `d1a4b8c30e5f` ← `c9e3f1b20a4d`) |
| Baseline suite before changes | 323 passed / 0 failed / 1 skipped |

### Stacked PR targeting notes (do not force-push)

| PR | Head | Current base | Ideal base |
|---|---|---|---|
| #20 | authorized-paper-execute | controlled-paper-session-runner | correct |
| #19 | controlled-paper-session-runner | **trading-schema** | paper-strategy-qualification-gate |
| #18 | paper-strategy-qualification-gate | walk-forward | correct (stacked) |

PR #19 targets an earlier base because the cloud agent default base was
`trading-schema`; its head still contains the full linear history. Retarget
manually when convenient — do not rewrite history.

## Pilot configuration

`app.pilot.config.PilotConfig` / `default_pilot_config()`:

- Strategy: first-party `sma_crossover@1.0.0`
- Symbol: `AAPL`, timeframe `1Day`
- Max quantity `1`, max notional `500`, max daily loss `100`
- **Max orders per session = 1**, max outstanding = 1
- Session duration ≤ 1 hour, consent TTL ≤ 1 hour
- `allow_real_paper_submit=false`, `background_worker_allowed=false`
- No broker credentials in config

## Preflight (read-only)

`PilotPreflightService.run` verifies owner, qualification, paper account,
paper endpoint, risk limits, buying power, positions/orders, fresh bars,
idempotency ledger, migration head, kill-switch readiness.

**Does not** submit, modify, or cancel orders.

## Controlled dry run

`ControlledDryRunPilot` creates a `DRY_RUN` session, activates, runs one
iteration. Captures decision/proposal/risk/validation/memory/audit.  
`NO_ACTION` is recorded honestly — signals are never manufactured.

## Simulated paper execution

`SimulatedPilotHarness` uses **only** `FakeExecutionAdapter` through Broker
Router. Covers success, rejection, partial fill, cancel, timeout reconcile,
unknown outcome, duplicate/one-order max, revoked/expired consent, kill switch.

## Operator runbook

See [supervised-paper-pilot-operator-runbook.md](./supervised-paper-pilot-operator-runbook.md).

## Safety

- Paper-only routing; live endpoints rejected
- Deployment execute flag must stay false during preparation
- No autonomous activation / no background worker
- No broad cancel / no auto-liquidation
- No qualification or risk bypass
- No blind retries after uncertain ACK
