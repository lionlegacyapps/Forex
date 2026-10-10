# Strategy Evaluation & Market Memory V1

Offline research-evidence foundation for comparing strategies under different
market conditions. **Does not trade, promote strategies, or optimize parameters.**

## Evaluation architecture

```
Historical bars
  → BacktestEngine (existing)
  → StrategyEvaluationService
       → dataset fingerprint + configuration hash
       → trade→regime attribution
       → regime performance buckets
       → evidence-quality warnings
  → StrategyComparisonReport (same-dataset only when assumptions match)
  → MarketMemoryService → market_memory_events (optional persistence)
```

Evaluation identity (`evaluation_id`) is derived from strategy version,
parameters, dataset fingerprint, and execution/cost assumptions — **not** from
wall-clock run time.

## Market context and regimes

Point-in-time features use `app.indicators` on bars `≤ as_of_index` only.

Multi-label regimes (not mutually exclusive):

| Label | Meaning (V1 rules) |
|---|---|
| `trending_up` | Fast EMA above slow EMA beyond ranging band |
| `trending_down` | Fast EMA below slow EMA beyond ranging band |
| `ranging` | EMA gap inside ranging band |
| `high_volatility` | ATR% ≥ median ATR% × high multiplier |
| `low_volatility` | ATR% ≤ median ATR% × low multiplier |
| `unknown` | Insufficient warm-up / unclassified |

## Performance comparison methodology

`StrategyEvaluationService.compare` requires matching:

- dataset fingerprint
- symbol / timeframe
- execution assumptions
- cost assumptions

Metrics surfaced: net P&L, total return %, win rate, profit factor, expectancy,
max drawdown, trade count, average win/loss, costs. **Win rate alone is never
used as a ranking rule.**

## Market Memory storage model

Reuses existing `market_memory_events` (no migration in V1):

- `event_type`: `strategy_evaluation_summary` | `market_context_snapshot`
- `source`: `strategy_evaluation_v1`
- `market_context.evidence_id`: stable idempotency key
- `market_context.payload_hash`: conflict detection
- `outcome`: compact evaluation summary (no OHLCV, no equity curves, no model binaries)

Writes are idempotent. Conflicting payloads for the same `evidence_id` raise
`EvidenceConflictError`. Updates to stored outcomes raise
`EvidenceImmutabilityError`.

## Provenance and reproducibility

Research adapters attach provenance for:

- Qlib-inspired momentum (`is_trained_ai_policy=False`)
- FinRL-X offline baseline (`is_trained_ai_policy=False` — never claimed trained)
- RSI/MACD and SMA reference strategies

Identical inputs reproduce identical `evaluation_id` and metrics.

## Evidence limitations

Warnings include small samples, zero trades, missing OOS evaluation, incomplete
or zero costs, warm-up gaps, regime concentration, and unreliable regime buckets
(`< 10` trades). No fabricated statistical confidence intervals.

## Walk-forward readiness

`WalkForwardPlan` / `SplitRole` support future TRAIN / VALIDATION /
OUT_OF_SAMPLE windows. V1 does **not** search parameters. FULL_SAMPLE and TRAIN
results must not be labeled as out-of-sample evidence.

## Paper qualification boundary

Evaluation sets `paper_eligible=False` and `promotion_blocked=True` always.
Future promotion requires a separate approval workflow.

## Database migration

**NO** — V1 uses the existing `market_memory_events` table.
