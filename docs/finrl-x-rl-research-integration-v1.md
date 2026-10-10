# FinRL-X — AI Reinforcement Learning Integration V1

## EXTERNAL GITHUB CODE IS NEVER TRUSTED BY DEFAULT.

| Field | Value |
|---|---|
| Official repository | https://github.com/AI4Finance-Foundation/FinRL-Trading |
| Identity | FinRL-X (AI4Finance Foundation; arXiv:2603.21330) |
| Pinned commit | `4409abe925c904e570be78ebfb5e77ac3491dff8` |
| License | Apache-2.0 |
| Full FinRL-X installed in trading runtime | **NO** |
| External FinRL-X code executed | **NO** |
| DRL training workers | **NOT deployed** |
| Auto-trading from research | **NO** |

## Intake summary

Verified official FinRL-X implementation as **AI4Finance-Foundation/FinRL-Trading**
(not assumed). Apache-2.0 is permissive for adaptation of concepts.

Static review of tip sources finds **broker order submission**
(`AlpacaManager.place_order`), **credential env templates** (`APCA_*`),
`deploy.sh`, `alpaca-py`, and a heavy optional DRL stack (`torch`, gymnasium,
stable-baselines3).

**Decision for trading/execution service:** do **not** install or execute
full FinRL-X.

**Decision for research value:** **ADAPT** offline RL environment concepts
(observations, discrete actions, rewards, transaction costs, position limits,
episode evaluation) into `app.research.rl`.

### Component matrix

| Component | Decision |
|---|---|
| RL environment design | **ADAPT** |
| Historical market observations | **ADAPT** |
| Action spaces | **ADAPT** |
| Reward calculations | **ADAPT** |
| Transaction-cost modeling | **ADAPT** |
| Position / portfolio constraints | **ADAPT** |
| Offline policy evaluation | **ADAPT** |
| DRL training (torch / SB3) | **REFERENCE ONLY** (deferred) |
| FinRL-X backtest engine | **REJECT** |
| Alpaca broker execution | **REJECT** |
| Deploy / live scripts | **REJECT** |

## Architecture (implemented)

```
Historical Market Data (our bars)
  → OfflineTradingEnv (reset/step, costs, limits)
  → DeterministicMomentumBaselinePolicy (NOT trained RL)
  → evaluate_policy → ResearchOutput
  → FinRLXBaselineSignalAdapter
  → StrategyDecision → Trade Proposal → BacktestEngine
```

Does **not** replace BacktestEngine, Strategy Registry, Risk Engine, Broker
Router, or accounting.

## Baseline policy

`DeterministicMomentumBaselinePolicy` — rule-based BUY/SELL/HOLD from
point-in-time momentum. **Not** a trained or profitable RL model.

## Deferred

- Actual DRL training (PPO/A2C/DDPG/etc.)
- Training workers / GPU infrastructure
- Installing FinRL-X, alpaca-py, torch, or stable-baselines3 in production

## Dependencies introduced

**None** in trading runtime `pyproject.toml`.

## Security

- Broker credentials never exposed to research code
- No FinRL-X order paths reused
- Alpaca paper-only platform safeguards unchanged
- Research outputs do not auto paper-trade

## Related

- [github-strategy-intake-adapter-framework-v1.md](./github-strategy-intake-adapter-framework-v1.md)
- [microsoft-qlib-research-integration-v1.md](./microsoft-qlib-research-integration-v1.md)
- [notices/FINRL_X_APACHE_2_0_NOTICE.md](./notices/FINRL_X_APACHE_2_0_NOTICE.md)
