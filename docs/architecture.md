# Architecture notes

## Order pipeline (mandatory — Safety Pipeline V1)

```
Trade Proposal → Risk Engine → Order Validator → Broker Router → Simulation Broker
```

**REAL BROKER EXECUTION IS NOT IMPLEMENTED.**

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

See [market-data-provider-v1.md](./market-data-provider-v1.md),
[alpaca-paper-account-read-path-v1.md](./alpaca-paper-account-read-path-v1.md),
[alpaca-paper-execution-adapter-v1.md](./alpaca-paper-execution-adapter-v1.md),
[alpaca-paper-order-lifecycle-v1.md](./alpaca-paper-order-lifecycle-v1.md),
[strategy-engine-backtesting-v1.md](./strategy-engine-backtesting-v1.md),
[github-strategy-intake-adapter-framework-v1.md](./github-strategy-intake-adapter-framework-v1.md),
[microsoft-qlib-research-integration-v1.md](./microsoft-qlib-research-integration-v1.md),
and [finrl-x-rl-research-integration-v1.md](./finrl-x-rl-research-integration-v1.md).

**EXTERNAL GITHUB CODE IS NEVER TRUSTED BY DEFAULT.**

Not implemented: live trading, Tradovate, Freqtrade, executing full Qlib/FinRL-X
in the trading runtime, DRL training workers, AI auto-trading, frontend charts.
