# Strategy Engine + Backtesting Foundation V1

**BACKTEST PERFORMANCE DOES NOT GUARANTEE FUTURE PERFORMANCE.**

## Architecture

```
Historical Market Data
  → Strategy.evaluate(StrategyContext)
  → StrategyDecision
  → StrategyProposalAdapter
  → CreateTradeProposalInput (normalized Trade Proposal shape)
```

In paper/live-capable environments (not this milestone’s backtester):

```
Trade Proposal → Risk Engine → Order Validator → Broker Router → Broker
```

The Strategy Engine **never** knows how to submit broker orders.
Strategies must **not** receive `BrokerExecutionAdapter`, Alpaca trading
clients, `BrokerRouter` write access, or raw credentials.

Backtests operate **entirely offline/in-process**. They do **not** route to
Alpaca.

## Strategy interface

`app.strategies.protocol.Strategy`

| Concept | Property / method |
|---|---|
| Identifier | `strategy_id` |
| Display name | `name` |
| Version | `version` |
| Asset classes | `supported_asset_classes` |
| Timeframes | `required_timeframes` |
| Parameters | `default_parameters()` / `validate_parameters()` |
| Decision | `evaluate(context) -> StrategyDecision` |

## StrategyContext

Normalized, broker-free inputs:

- `symbol`, `asset_class`, `timestamp`, `timeframe`
- `bars` — **lookahead-safe** historical OHLCV only
- optional `latest_quote` / `latest_trade` / `reference_price`
- `position` (strategy-scoped), optional `portfolio`
- `parameters`

## StrategyDecision

Actions: `NO_ACTION`, `ENTER_LONG`, `ENTER_SHORT`, `EXIT_LONG`, `EXIT_SHORT`.

May include side, quantity, order type, limit/stop/stop-loss/take-profit,
time in force, rationale, and signal metadata.

Strategies **do not** create broker orders.

## Strategy Registry

`StrategyRegistry` registers in-process implementations, looks up by
`strategy_id` / version, validates metadata, and rejects duplicates.

No plugin marketplace. No dynamic execution of untrusted code.

## Trade Proposal adapter

`StrategyProposalAdapter.to_proposal_input(...)` converts an actionable
decision into `CreateTradeProposalInput` with `source=STRATEGY`.

All strategy-generated trades enter the **same** safety pipeline shape.
There is no separate strategy execution path.

## Historical data abstraction

`HistoricalMarketDataProvider.get_bars(symbol, timeframe, start, end)`

Normalized OHLCV (`Bar`). Provider-independent. Future sources may include
Alpaca, Polygon, Databento, Parquet/CSV — **not** all implemented in V1.

`InMemoryHistoricalMarketDataProvider` loads deterministic sequences for tests.

## Backtest Engine

Responsibilities:

1. Load historical bars
2. Iterate chronologically
3. Build lookahead-safe `StrategyContext`
4. Invoke strategy
5. Simulate proposal creation via adapter
6. Simulate fills with deterministic rules
7. Track portfolio / trades / equity curve / metrics

### Execution Model V1 assumptions

| Rule | Behavior |
|---|---|
| Signal timing | Bar **close** |
| Market orders | Fill at **next** bar **open** (+ optional slippage) |
| Limit orders | Fill only if a **subsequent** bar range crosses limit |
| Stop orders | Trigger only if a subsequent bar range crosses stop |
| Same-bar fill | **Forbidden** (no intra-bar lookahead) |
| External broker | **Never** |

### Cost model

`BacktestCostModel`: `commission_per_share`, `commission_flat`, `slippage_bps`.

Defaults may be **zero for baseline tests** — this does **not** represent real
trading costs.

### Position sizing boundary

`BacktestSizingModel` separates direction logic from capital sizing
(`fixed_quantity`, `decision_quantity`, `percent_equity`, optional `max_quantity`).

Paper/live execution still uses the existing Risk Engine.

### Portfolio

Tracks starting capital, cash, positions, average entry, realized/unrealized
P&L, equity, and closed trades (`Decimal`).

### Performance metrics V1

Starting capital, ending equity, net P&L, total return %, trade counts,
win/loss, win rate, average win/loss, profit factor, max drawdown,
expectancy; Sharpe/Sortino when statistically valid (else `None` + warning).

See `app/backtesting/metrics.py` for formulas.

### Trade log & equity curve

Normalized `BacktestTradeRecord` and `EquityPoint` series for future UI charts
(charts **not** built in this milestone).

### BacktestResult

Serializable (`model_dump` / `to_serializable_dict`) including strategy
metadata, parameters, range, symbols, timeframe, capital, metrics, trades,
equity curve, warnings, execution/cost assumptions.

## Lookahead protection

At evaluation time `i`, strategies receive bars `[0..i]` only.
Orders generated at bar `i` cannot fill on bar `i`.
`LookaheadSafeBarView` and explicit tests enforce this.

## Strategy lifecycle (DB statuses)

Aligned with existing `StrategyStatus`:

`development` → `backtesting` → `paper` → `live_eligible` / `paused` / `retired`

A successful backtest is **evidence only**. It does **not** automatically
change database status or approve paper/live trading.

## Acceptance foundation

`BacktestAcceptanceGate` + `AcceptanceRule` support future qualification
rules (min trades, win rate, profit factor, max drawdown, positive expectancy).

**No profitability thresholds chosen in V1. No automatic promotion.**

## Multi-strategy / multi-symbol

Results and trades carry `strategy_id`, `strategy_version`, and `parameters`.
Positions are tracked per symbol within a backtest run; multiple strategies
must not share position state accidentally.

V1 may primarily exercise single-symbol strategies; the engine timeline merges
timestamps across symbols for future multi-symbol use.

## Market Memory hook

Optional `BacktestMemoryHook` receives decision/fill events for future Market
Memory. **No AI/learning system in V1.**

## GitHub strategy integration

See [github-strategy-intake-adapter-framework-v1.md](./github-strategy-intake-adapter-framework-v1.md).

**EXTERNAL GITHUB CODE IS NEVER TRUSTED BY DEFAULT.**

Do not `git clone` arbitrary repositories into the trading runtime.
Never execute untrusted external code directly inside the trading runtime.

## Reference strategy

`SMACrossoverStrategy` (`sma_crossover@1.0.0`) — internal deterministic
reference for framework tests only. **Not claimed to be profitable.**

## Security

- Strategy modules contain no broker credentials
- Strategies must not import Alpaca trading clients / execution adapters
- Backtester performs zero external broker writes
- Live trading remains impossible
- External execution remains Alpaca **PAPER** only outside backtests

## Related docs

- [architecture.md](./architecture.md)
- [trading-safety-pipeline-v1.md](./trading-safety-pipeline-v1.md)
- [market-data-provider-v1.md](./market-data-provider-v1.md)
