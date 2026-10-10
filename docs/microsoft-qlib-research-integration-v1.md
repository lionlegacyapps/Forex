# Microsoft Qlib — First GitHub Strategy Integration V1

## EXTERNAL GITHUB CODE IS NEVER TRUSTED BY DEFAULT.

| Field | Value |
|---|---|
| Repository | https://github.com/microsoft/qlib |
| Pinned commit | `54355232463878d2eebb91fe0ee5fa7fa1f5976c` (2026-10-08) |
| License | MIT |
| Full `pyqlib` installed in trading runtime | **NO** |
| External Qlib code executed | **NO** |
| Auto-trading from research | **NO** |

## Intake summary

Full-repository static intake detects high-risk patterns in Qlib’s own
workflow/utils (e.g. `subprocess`/`shell=True`, `pickle.Unpickler`, HTTP
requests) and a large dependency surface (lightgbm, mlflow, redis, optional
torch/RL, Cython extensions, data download scripts).

**Decision for trading/execution service:** do **not** install or execute
full Qlib.

**Decision for research value:** **ADAPT** factor-engineering concepts into
our isolated `app.research` package; wire predictions through
`ExternalStrategyAdapter` → `StrategyDecision` → Trade Proposal → our
BacktestEngine.

### Component matrix

| Component | Decision |
|---|---|
| Quantitative factor engineering | **ADAPT** |
| Technical indicator / factor expressions | **ADAPT** |
| Feature preprocessing | **ADAPT** |
| Dataset preparation | **WRAP** onto our HistoricalMarketDataProvider |
| Predictive ML models (lightgbm/torch) | **REFERENCE ONLY** (deferred) |
| Model evaluation tooling | **REFERENCE ONLY** |
| Experiment tracking (mlflow/redis) | **REFERENCE ONLY** |
| Qlib backtest engine | **REJECT** |
| Qlib strategy / order execution | **REJECT** |
| Data download scripts | **REJECT** |
| RL modules | **REJECT** |

## Architecture (implemented)

```
Historical Market Data (our bars)
  → ResearchBarFrame (normalized OHLCV)
  → Factor preparation (point-in-time)
  → Fit on training period only
  → Predict on evaluation period only
  → ResearchOutput (serializable)
  → QlibFactorSignalAdapter
  → StrategyDecision
  → Trade Proposal shape
  → BacktestEngine (ours)
```

Qlib must never call Broker Router or Alpaca. Research outputs do not
automatically trigger paper/live trading or strategy promotion.

## Dependencies introduced

**None** in production `pyproject.toml` / trading runtime.

Optional future research environment (not activated): would pin `pyqlib` at
the commit above in an isolated sandbox with no broker credentials — deferred.

## Data requirements

- Symbol, timezone-aware timestamp, OHLCV, timeframe
- Strict chronological order
- Price convention recorded as `as_provided` (no silent adjust assumptions)
- Deterministic fixtures for tests — no automatic external downloads

## First research model (demo)

`qlib_inspired_momentum_v1` — deterministic momentum-vs-trailing-mean factor
with train bias subtraction.

- No GPU
- No paid data
- Not claimed to be profitable
- **Not** the complete Qlib framework

## Reproducibility

Same bars + lookback + train/eval split → identical `ResearchOutput` and
identical backtest results when using `QlibFactorSignalAdapter`.

## Security limitations

- Static scanning ≠ proof of safety
- Full Qlib runtime remains untrusted for execution service
- No unrestricted subprocess, pickle model load, or artifact download in our adapter
- Broker credentials never exposed to research code
- Alpaca paper-only safeguards unchanged

## Implemented vs planned

| Implemented now | Planned / deferred |
|---|---|
| Intake report + pinned manifest | Full pyqlib sandbox service |
| Research frame + factors | LightGBM/torch models |
| Train/eval split + ResearchOutput | Experiment tracking UI |
| QlibFactorSignalAdapter + backtest | Paper auto-execution from research |
| MIT notice | Broader factor expression language |

## Related

- [github-strategy-intake-adapter-framework-v1.md](./github-strategy-intake-adapter-framework-v1.md)
- [strategy-engine-backtesting-v1.md](./strategy-engine-backtesting-v1.md)
- [notices/MICROSOFT_QLIB_MIT_NOTICE.md](./notices/MICROSOFT_QLIB_MIT_NOTICE.md)
