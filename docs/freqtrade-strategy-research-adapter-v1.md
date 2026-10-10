# Freqtrade Strategy Research & Adapter V1

## EXTERNAL GITHUB CODE IS NEVER TRUSTED BY DEFAULT.

| Field | Value |
|---|---|
| Official repository | https://github.com/freqtrade/freqtrade |
| Pinned commit | `fccc94d9bb7a85023e946bf75774bd903888fc45` |
| License | **GPL-3.0** |
| Full Freqtrade bot installed | **NO** |
| Freqtrade source adapted/copied | **NO** |
| Compliant approach | **Independent** public-domain indicator formulas + first-party strategy |

## License review (critical)

Freqtrade is licensed under **GNU GPL v3**. Direct source-code adaptation,
translation, or close porting into this proprietary codebase is **unsuitable**
without explicit legal approval and copyleft compliance.

**Finding:** `COPYLEFT_REVIEW_REQUIRED` — **GPL source adaptation REJECTED**.

**Compliant delivery for this milestone:** independently implement standard
mathematical indicators (Wilder RSI/ATR, EMA/SMA, MACD, Bollinger) and an
`RSIMACDTrendStrategy` using those formulas. Strategy ideas (RSI+MACD
confirmation) are common market concepts, not Freqtrade source.

## Component classification

| Capability | Decision |
|---|---|
| RSI / MACD / MA / Bollinger concepts | **INDEPENDENT IMPLEMENTATION** |
| Multi-indicator confirmation | **INDEPENDENT IMPLEMENTATION** |
| Stop-loss / take-profit concepts | **INDEPENDENT IMPLEMENTATION** |
| Parameter configuration concepts | **REFERENCE ONLY** |
| Hyperopt / optimization approach | **REFERENCE ONLY** (documented; not implemented at scale) |
| Freqtrade bot runtime | **REJECT** |
| ccxt exchange adapters | **REJECT** |
| Freqtrade backtesting engine | **REJECT** |
| GPL source adaptation | **REJECT** |

## Indicators implemented (`app.indicators`)

Independent, deterministic, warm-up-aware:

- SMA, EMA
- RSI (Wilder)
- MACD (+ signal + histogram)
- Bollinger Bands
- ATR (Wilder)

No future leakage; missing values as `None` during warm-up.

## First strategy: `rsi_macd_trend@1.0.0`

`RSIMACDTrendStrategy` — first-party `Strategy` (not an ExternalStrategyAdapter
of Freqtrade).

| Parameter | Default |
|---|---|
| rsi_period | 14 |
| rsi_oversold | 30 |
| rsi_overbought | 70 |
| macd_fast / slow / signal | 12 / 26 / 9 |
| quantity | 1 |
| stop_loss_pct | 0.05 |
| require_macd_cross | true |

Rules (demo only — not a profitability claim):

- **Enter long:** RSI recovers above oversold **and** MACD bullish (optionally
  requiring MACD cross up).
- **Exit long:** RSI crosses into overbought **or** MACD crosses down.
- **NO_ACTION** otherwise.
- Optional `stop_loss_price` from `reference_price * (1 - stop_loss_pct)`.

Integration path:

```
Historical bars → Indicators → RSIMACDTrendStrategy
→ StrategyDecision → Trade Proposal → BacktestEngine
```

## Future optimization foundation (not implemented)

Freqtrade Hyperopt inspires a **future** walk-forward optimizer for:

- RSI periods / thresholds
- MACD settings
- Stop-loss / take-profit

Requirements for any future optimizer:

1. Chronological train / validation / test splits
2. No optimization against the final evaluation dataset
3. Walk-forward windows
4. Untouched out-of-sample holdout
5. Never treat in-sample fitness as proof of profitability

## Market Memory compatibility

Backtest trades / decisions retain strategy_id, version, parameters, symbol,
timeframe, indicator metadata (`signal_metadata`), and P&L fields for future
Market Memory hooks. No automatic learning or promotion.

## Security

- No Freqtrade package installed
- No ccxt / Freqtrade exchange imports
- No exchange credentials
- No arbitrary third-party strategy execution
- No auto paper/live trading

## Related

- [github-strategy-intake-adapter-framework-v1.md](./github-strategy-intake-adapter-framework-v1.md)
- [strategy-engine-backtesting-v1.md](./strategy-engine-backtesting-v1.md)
