# Strategy Qualification Report (NOT APPROVED)

> Historical evaluation evidence only. This is **not** a prediction of future
> performance and **does not** authorize paper or live trading.

## Identity

- **Strategy:** `sma_crossover@1.0.0`
- **Qualification ID:** `b46aa6ab-dcb4-41d7-b3e0-d4d5667d0573`
- **State:** `review_required`
- **Recommendation:** `eligible_for_review`
- **Approval scope:** `paper_only`
- **Evaluation date (UTC):** 2026-10-11T16:39:10.259682Z
- **Record created (UTC):** 2026-10-11T16:39:10.242790+00:00

## Parameters

- **Configuration:** `{"allow_short": false, "fast_period": 3, "quantity": "1", "slow_period": 5}`
- **Parameter hash:** `0dffa427614c01c848fdf24980b562da3ce3b88293ff8fc8fad2030ed7c4ec47`
- **Dataset fingerprint:** `ec54bdff55da41727dac68595531a714005d15a85b7cb00e37fca99796db1552`
- **Evidence fingerprint:** `cfcfdfe72d9fa2b94797f155e3bfa8e0f8a074f730f1f3c803adf307a9c97154`
- **Evaluation / harness ID:** `ac9b2fd469b6e6e831338c3122f1d9044f19b9e2ad90429022f4e55e40d23443`

## Historical testing period

- **Symbol / timeframe:** AAPL / 1Day
- **Bars:** 618 completed daily bars
- **Range:** 2024-04-24 → 2026-10-09

## Train / validation / OOS split

- **Mode:** rolling
- **Train bars:** 80
- **Validation bars:** 40
- **OOS bars:** 40
- **Step bars:** 40
- **Warmup bars:** 20

## Out-of-sample summary

- **OOS windows:** 12
- **OOS trades:** 39 (wins 20 / losses 19)
- **Net PnL (sum of OOS windows):** 60.9621275
- **Net return (stored OOS aggregate %):** 0.060956686198952530790264900
- **Compounded return % (recomputed):** 0.060956686198952530790264900
- **Trade-weighted win rate %:** 51.28205128205128205128205128
- **Average win (trade-weighted):** 5.14966074999999983
- **Average loss (trade-weighted):** -6.175020000000000015789473684
- **Maximum drawdown (worst OOS window):** 37.2605900
- **Transaction costs total (OOS):** 0.390
- **Profit factor (stored aggregate):** 0E+7
- **Profit factor note:** Stored aggregate profit_factor serializes poorly when some windows have zero losses (0E+7). Use window-level profit factors.

## Transaction cost assumptions

- `{"commission_flat": "0", "commission_per_share": "0.005", "slippage_bps": "5"}`

## Regime performance notes

- unreliable_regime:high_volatility
- unreliable_regime:ranging
- unreliable_regime:trending_down
- unreliable_regime:trending_up

## Robustness findings

- unreliable_regime_buckets_present

## Window-by-window OOS consistency

| Window | Trades | Net PnL | Win rate % | Profit factor | Max DD | Avg win | Avg loss | Costs |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 2 | 7.1641525 | 0 | 0E+7 | 15.6958475 | None | -7.30394375 | 0.020 |
| 1 | 2 | -11.8893125 | 0 | 0E+6 | 17.0498275 | None | -3.511555 | 0.020 |
| 2 | 3 | -6.7037450 | 66.66666666666666666666666667 | 0.4347482029553742701153059719 | 18.5533300 | 2.5780025 | -11.85975 | 0.030 |
| 3 | 3 | 3.0923850 | 33.33333333333333333333333333 | 1.384859193319116856033106789 | 14.4398375 | 6.70034 | -2.41914125 | 0.030 |
| 4 | 5 | 5.7625575 | 80.0 | 2.268965756433674767046636916 | 5.9719575 | 2.575925625 | -4.541145 | 0.050 |
| 5 | 3 | 30.8317825 | 100 | None | 7.621105 | 10.419736666666665 | None | 0.030 |
| 6 | 5 | 17.8607225 | 40.0 | 2.710503283184817373493692255 | 11.4663225 | 9.786116250000001 | -2.4069616666666667 | 0.050 |
| 7 | 4 | -8.8212350 | 25.00 | 0.1366834200362209448274073447 | 8.8212350 | 1.39661 | -3.4059483333333334 | 0.040 |
| 8 | 3 | -6.785965 | 33.33333333333333333333333333 | 0.5568394246458239932918230052 | 19.436000 | 8.52669 | -7.6563275 | 0.030 |
| 9 | 3 | 33.6128250 | 100 | None | 6.900000 | 3.4707508333333332 | None | 0.030 |
| 10 | 2 | 29.9958375 | 50.0 | 0.4599450252670396815688298515 | 7.1000000 | 2.0585725 | -4.4756925 | 0.020 |
| 11 | 4 | -33.1578775 | 50.0 | 0.2043508634701006651489522270 | 37.2605900 | 3.8038 | -18.61406375 | 0.040 |

## Hard blockers

- none

## Warnings

- Codes: low_profit_factor, robustness_warning, unreliable_regime_bucket
- Profit factor 0E+7 below warning threshold
- Unreliable regime sample for high_volatility
- Unreliable regime sample for ranging
- Unreliable regime sample for trending_down
- Unreliable regime sample for trending_up
- unreliable_regime_buckets_present

## Qualification recommendation

- **eligible_for_review**
- Auto-approval was **not** performed.
- Owner must explicitly approve after reviewing this report.

## Recompute integrity

- Parameter hash match: True
- Dataset fingerprint match: True
- Evaluation id match: True
- Note: Window metrics from a recompute that matched stored hashes.

## Disclaimer

These metrics describe historical simulated performance on past market data
with stated transaction costs. They are **not** a guarantee of future results,
profitability, or suitability for unsupervised trading.
