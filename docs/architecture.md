# Architecture notes

## Order pipeline (mandatory — Safety Pipeline V1)

```
Trade Proposal → Risk Engine → Order Validator → Broker Router
  → Simulation Broker | Alpaca Paper Adapter (authorized PAPER_EXECUTE only)
```

**LIVE BROKER EXECUTION IS IMPOSSIBLE.** Paper submit requires feature flag +
session-scoped consent; credentials alone never unlock writes.

No trade execution component may bypass this path.

- Strategies emit **StrategyDecision → TradeProposal** only (never broker orders).
- Risk evaluates strategy, account, and global limits (deterministic; no AI).
- Validation checks order shape and trading mode.
- Routing selects the broker adapter + account.
- Paper path: Alpaca **PAPER** execution adapter only (live trading impossible).
- Simulation broker remains available for offline pipeline tests.
- Adapters never independently decide whether a trade is safe.
- Backtests are offline/in-process and **never** route to Alpaca.

See [trading-safety-pipeline-v1.md](./trading-safety-pipeline-v1.md) for
reason codes, state transitions, and policy resolution.

See [strategy-engine-backtesting-v1.md](./strategy-engine-backtesting-v1.md) for
the Strategy Engine + Backtesting Foundation V1.

## Fail-closed defaults

| Entity | Default mode | Default enabled |
|---|---|---|
| Broker account | `paper` | `false` |
| Strategy ↔ account assignment | `paper` | `false` |
| Risk policy `require_stop_loss` | — | `true` |

Operators must explicitly enable accounts and assignments before any trading path
can use them. Database constraints reinforce these defaults; they do **not**
replace the Risk Engine.

## Persistence

Application state belongs in **Supabase PostgreSQL**, not container
filesystems. The VPS is replaceable compute.

## Current scope

- Foundation + Version 1 database schema (hardened)
- Trading Safety Pipeline V1
- Paper Execution & Portfolio Accounting V1
- Market Data Provider V1 (read-only; Alpaca data API optional)
- Alpaca Paper Account Read-Path V1 (read-only paper account/positions/orders;
  observational reconciliation; **no** order execution)
- Alpaca Paper Execution Adapter V1 (controlled paper `submit_order` only via
  Risk → Validator → Router; **no** live trading)
- Alpaca Paper Order Lifecycle V1 (status sync, partial fills, controlled
  cancel, fill→accounting, reconciliation)
- Strategy Engine + Backtesting Foundation V1 (strategy interface/registry,
  decision→proposal adapter, historical data abstraction, offline backtester,
  lookahead protection, metrics; reference SMA only)
- GitHub Strategy Intake & Adapter Framework V1 (intake models, license/security
  review, classification, manifests with commit pins, ExternalStrategyAdapter
  gate — **no** external repo clone/execute)
- Microsoft Qlib Research Integration V1 (intake + pinned commit; factor concepts
  adapted into isolated `app.research`; full `pyqlib` **not** installed/executed)
- FinRL-X RL Research Integration V1 (official FinRL-Trading intake; offline
  env + baseline policy adapted; full FinRL-X / alpaca-py / torch **not** installed)
- Freqtrade Strategy Research & Adapter V1 (GPL-3.0 reference-only intake;
  independent indicators + `rsi_macd_trend` strategy; Freqtrade bot **not** installed)
- Strategy Evaluation & Market Memory V1 (normalized evaluation records, regime
  classification, trade attribution, same-dataset comparison, persistence into
  existing `market_memory_events`; **no** auto-promotion / live trading)
- Walk-Forward Evaluation Harness V1 (chronological TRAIN/VALIDATION/OOS splits,
  rolling/expanding windows, leakage guards, fixed-parameter evaluation;
  **no** optimization / promotion / live trading)
- Paper Strategy Qualification Gate V1 (evidence review + manual owner approval
  for paper-session eligibility; durable approvals; **no** session start / orders /
  live trading)
- Controlled Paper Session Runner V1 (manual DRY_RUN sessions; qualification +
  risk + validator path; **PAPER_EXECUTE disabled by default**; no auto-start /
  no live trading)
- Authorized Paper Execute Activation V1 (session-scoped consent + feature flag;
  Risk → Validator → Broker Router → Alpaca paper adapter; mocked in tests;
  **no** real Alpaca orders / no live trading / no always-on worker)
- Supervised Single-Strategy Paper Pilot Preparation V1 (preflight, DRY_RUN,
  FakeExecutionAdapter rehearsal, operator runbook; **no** real paper orders;
  deployment execute remains disabled)

See [market-data-provider-v1.md](./market-data-provider-v1.md),
[alpaca-paper-account-read-path-v1.md](./alpaca-paper-account-read-path-v1.md),
[alpaca-paper-execution-adapter-v1.md](./alpaca-paper-execution-adapter-v1.md),
[alpaca-paper-order-lifecycle-v1.md](./alpaca-paper-order-lifecycle-v1.md),
[strategy-engine-backtesting-v1.md](./strategy-engine-backtesting-v1.md),
[github-strategy-intake-adapter-framework-v1.md](./github-strategy-intake-adapter-framework-v1.md),
[microsoft-qlib-research-integration-v1.md](./microsoft-qlib-research-integration-v1.md),
[finrl-x-rl-research-integration-v1.md](./finrl-x-rl-research-integration-v1.md),
[freqtrade-strategy-research-adapter-v1.md](./freqtrade-strategy-research-adapter-v1.md),
[strategy-evaluation-market-memory-v1.md](./strategy-evaluation-market-memory-v1.md),
[walk-forward-evaluation-harness-v1.md](./walk-forward-evaluation-harness-v1.md),
[paper-strategy-qualification-gate-v1.md](./paper-strategy-qualification-gate-v1.md),
and [controlled-paper-session-runner-v1.md](./controlled-paper-session-runner-v1.md).

**EXTERNAL GITHUB CODE IS NEVER TRUSTED BY DEFAULT.**

Not implemented: live trading, Tradovate, installing/running Freqtrade or
full Qlib/FinRL-X in the trading runtime, DRL training workers, hyperopt,
AI auto-trading, frontend charts.
