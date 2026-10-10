"""Associate completed backtest trades with entry-time market context."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from app.backtesting.result import BacktestResult, BacktestTradeRecord
from app.evaluation.evidence import MIN_RELIABLE_REGIME_TRADES, regime_reliability_warning
from app.evaluation.models import RegimePerformanceBucket, TradeOutcomeAttribution
from app.evaluation.regimes import (
    MarketContextSnapshot,
    MarketRegime,
    RegimeClassifierConfig,
    classify_market_context,
    index_at_or_before,
)
from app.market_data.models import Bar


def attribute_trade(
    trade: BacktestTradeRecord,
    bars: list[Bar],
    *,
    timeframe: str,
    config: RegimeClassifierConfig | None = None,
    research_source: str | None = None,
) -> TradeOutcomeAttribution:
    idx = index_at_or_before(bars, trade.entry_time)
    ctx: MarketContextSnapshot | None = None
    regimes: list[MarketRegime] = [MarketRegime.UNKNOWN]
    if idx is not None:
        ctx = classify_market_context(
            bars,
            as_of_index=idx,
            timeframe=timeframe,
            config=config,
        )
        regimes = list(ctx.regimes)
    holding = (trade.exit_time - trade.entry_time).total_seconds()
    return TradeOutcomeAttribution(
        strategy_id=trade.strategy_id,
        strategy_version=trade.strategy_version,
        symbol=trade.symbol,
        timeframe=timeframe,
        entry_time=trade.entry_time,
        exit_time=trade.exit_time,
        side=trade.side,
        gross_pnl=trade.gross_pnl,
        costs=trade.costs,
        net_pnl=trade.net_pnl,
        holding_duration_seconds=holding,
        exit_reason=trade.exit_reason,
        entry_regimes=regimes,
        entry_context=ctx,
        research_source=research_source,
    )


def attribute_trades(
    result: BacktestResult,
    bars: list[Bar],
    *,
    config: RegimeClassifierConfig | None = None,
    research_source: str | None = None,
) -> list[TradeOutcomeAttribution]:
    return [
        attribute_trade(
            t,
            bars,
            timeframe=result.timeframe,
            config=config,
            research_source=research_source,
        )
        for t in result.trades
    ]


def regime_performance(
    attributions: list[TradeOutcomeAttribution],
) -> list[RegimePerformanceBucket]:
    """Group by each regime label on a trade (multi-label aware)."""
    buckets: dict[MarketRegime, list[TradeOutcomeAttribution]] = defaultdict(list)
    for attr in attributions:
        labels = attr.entry_regimes or [MarketRegime.UNKNOWN]
        for regime in labels:
            buckets[regime].append(attr)

    out: list[RegimePerformanceBucket] = []
    for regime in MarketRegime:
        trades = buckets.get(regime, [])
        n = len(trades)
        if n == 0:
            continue
        net = sum((t.net_pnl for t in trades), Decimal("0"))
        wins = sum(1 for t in trades if t.net_pnl > 0)
        win_rate = (Decimal(wins) / Decimal(n)) * Decimal("100")
        avg = net / Decimal(n)
        reliable = n >= MIN_RELIABLE_REGIME_TRADES
        out.append(
            RegimePerformanceBucket(
                regime=regime,
                trade_count=n,
                net_pnl=net,
                win_rate=win_rate,
                average_net_pnl=avg,
                sample_reliable=reliable,
                warnings=regime_reliability_warning(n),
            )
        )
    return out
