"""BacktestEngine — offline chronological strategy simulation.

Never routes to Alpaca or any external broker.
Never places real orders.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from app.backtesting.costs import BacktestCostModel
from app.backtesting.errors import BacktestError, HistoricalDataError, LookaheadError
from app.backtesting.execution_model import BacktestExecutionModel, PendingOrder
from app.backtesting.historical import HistoricalMarketDataProvider
from app.backtesting.memory_hook import (
    BacktestMemoryHook,
    decision_event,
)
from app.backtesting.metrics import calculate_metrics
from app.backtesting.portfolio import BacktestPortfolio
from app.backtesting.result import BacktestResult, BacktestTradeRecord, EquityPoint
from app.backtesting.sizing import BacktestSizingModel
from app.market_data.models import Bar, MarketDataAssetClass
from app.models.enums import AssetClass
from app.strategies.context import PortfolioContextView, StrategyContext
from app.strategies.decision import DecisionAction, StrategyDecision
from app.strategies.proposal_adapter import StrategyProposalAdapter
from app.strategies.protocol import Strategy


# Map trading AssetClass → market-data asset class for historical loads
_ASSET_MAP = {
    AssetClass.EQUITY: MarketDataAssetClass.EQUITY,
    AssetClass.CRYPTO: MarketDataAssetClass.CRYPTO,
    AssetClass.FUTURES: MarketDataAssetClass.FUTURES,
    AssetClass.OPTION: MarketDataAssetClass.OPTION,
    AssetClass.FOREX: MarketDataAssetClass.OTHER,
    AssetClass.OTHER: MarketDataAssetClass.OTHER,
}


class LookaheadSafeBarView:
    """Read-only bar list that rejects access beyond the allowed index."""

    def __init__(self, bars: list[Bar], *, max_inclusive_index: int) -> None:
        if max_inclusive_index < -1 or max_inclusive_index >= len(bars):
            raise LookaheadError(
                "Invalid lookahead window",
                code="invalid_window",
            )
        self._bars = bars
        self._max = max_inclusive_index

    def as_list(self) -> list[Bar]:
        if self._max < 0:
            return []
        return list(self._bars[: self._max + 1])

    def __len__(self) -> int:
        return max(0, self._max + 1)


class BacktestEngine:
    """Run a strategy over historical bars with deterministic fills."""

    EXECUTION_ASSUMPTIONS = {
        "model": "Backtest Execution Model V1",
        "signal_at": "bar_close",
        "market_fill_at": "next_bar_open",
        "limit_fill": "subsequent_bar_range_crosses_limit",
        "stop_fill": "subsequent_bar_range_crosses_stop",
        "same_bar_fill": False,
        "external_broker": False,
        "disclaimer": (
            "BACKTEST PERFORMANCE DOES NOT GUARANTEE FUTURE PERFORMANCE. "
            "Zero-cost defaults do not represent real trading."
        ),
    }

    def __init__(
        self,
        historical: HistoricalMarketDataProvider,
        *,
        costs: BacktestCostModel | None = None,
        sizing: BacktestSizingModel | None = None,
        memory_hook: BacktestMemoryHook | None = None,
        proposal_adapter: StrategyProposalAdapter | None = None,
    ) -> None:
        self.historical = historical
        self.costs = costs or BacktestCostModel()
        self.sizing = sizing or BacktestSizingModel()
        self.execution = BacktestExecutionModel(self.costs)
        self.memory_hook = memory_hook
        self.proposal_adapter = proposal_adapter or StrategyProposalAdapter()

    def run(
        self,
        strategy: Strategy,
        *,
        symbols: list[str],
        timeframe: str,
        start: datetime | None = None,
        end: datetime | None = None,
        starting_capital: Decimal = Decimal("100000"),
        parameters: dict[str, Any] | None = None,
        asset_class: AssetClass = AssetClass.EQUITY,
        broker_account_id: UUID | None = None,
    ) -> BacktestResult:
        if not symbols:
            raise BacktestError("At least one symbol is required", code="no_symbols")
        if starting_capital <= 0:
            raise BacktestError("starting_capital must be positive", code="invalid_capital")

        params = strategy.validate_parameters(parameters or {})
        if timeframe not in strategy.required_timeframes:
            # Allow if strategy declares the timeframe; otherwise warn via result
            pass
        if asset_class not in strategy.supported_asset_classes:
            raise BacktestError(
                f"asset_class {asset_class} not supported by {strategy.strategy_id}",
                code="unsupported_asset_class",
            )

        md_asset = _ASSET_MAP.get(asset_class, MarketDataAssetClass.OTHER)
        series_by_symbol: dict[str, list[Bar]] = {}
        for sym in symbols:
            bars = self.historical.get_bars(
                sym,
                timeframe,
                start,
                end,
                asset_class=md_asset,
            )
            if not bars:
                raise HistoricalDataError(
                    f"No bars for {sym} in range",
                    code="empty_series",
                )
            # Enforce chronological order
            for i in range(1, len(bars)):
                if bars[i].timestamp <= bars[i - 1].timestamp:
                    raise HistoricalDataError(
                        "Historical bars must be chronological",
                        code="non_monotonic_bars",
                    )
            series_by_symbol[sym.strip().upper()] = bars

        # V1 timeline: merge unique timestamps across symbols (multi-symbol foundation)
        timeline = sorted(
            {b.timestamp for bars in series_by_symbol.values() for b in bars}
        )
        index_maps = {
            sym: {b.timestamp: i for i, b in enumerate(bars)}
            for sym, bars in series_by_symbol.items()
        }

        portfolio = BacktestPortfolio.create(
            starting_capital,
            strategy_id=strategy.strategy_id,
            strategy_version=strategy.version,
        )
        pending: list[PendingOrder] = []
        equity_curve: list[EquityPoint] = []
        simulated_proposals: list[dict[str, Any]] = []
        warnings: list[str] = []
        account_id = broker_account_id or uuid4()

        # Primary symbol for single-symbol strategies; multi-symbol iterates all
        for ts in timeline:
            # 1) Process fills for this bar before new signals (next-bar open model)
            for sym, bars in series_by_symbol.items():
                idx = index_maps[sym].get(ts)
                if idx is None:
                    continue
                bar = bars[idx]
                still_pending: list[PendingOrder] = []
                for order in pending:
                    if order.decision.symbol != sym:
                        still_pending.append(order)
                        continue
                    fill = self.execution.try_fill(order, bar, idx)
                    if fill is None:
                        still_pending.append(order)
                        continue
                    closed = portfolio.apply_fill(fill)
                    if self.memory_hook is not None:
                        from app.backtesting.memory_hook import BacktestMemoryEvent

                        self.memory_hook.on_event(
                            BacktestMemoryEvent(
                                event_type="fill",
                                timestamp=fill.fill_time,
                                symbol=fill.symbol,
                                strategy_id=strategy.strategy_id,
                                strategy_version=strategy.version,
                                outcome={
                                    "price": str(fill.price),
                                    "quantity": str(fill.quantity),
                                    "side": fill.side.value,
                                    "reason": fill.reason.value,
                                    "closed_trade": closed is not None,
                                },
                            )
                        )
                pending = still_pending

            # 2) Evaluate strategy per symbol with lookahead-safe bars
            for sym, bars in series_by_symbol.items():
                idx = index_maps[sym].get(ts)
                if idx is None:
                    continue
                bar = bars[idx]
                visible = LookaheadSafeBarView(bars, max_inclusive_index=idx).as_list()
                # Hard assert: no future bars
                if any(b.timestamp > ts for b in visible):
                    raise LookaheadError(
                        "Future bars leaked into StrategyContext",
                        code="lookahead_bars",
                    )

                marks = {
                    s: series_by_symbol[s][index_maps[s][ts]].close
                    if ts in index_maps[s]
                    else series_by_symbol[s][
                        max(i for t, i in index_maps[s].items() if t <= ts)
                    ].close
                    for s in series_by_symbol
                    if any(t <= ts for t in index_maps[s])
                }
                unrealized = portfolio.mark_unrealized(marks)
                eq = portfolio.equity(marks)

                ctx = StrategyContext(
                    symbol=sym,
                    asset_class=asset_class,
                    timestamp=ts,
                    timeframe=timeframe,
                    bars=visible,
                    reference_price=bar.close,
                    position=portfolio.position_view(sym),
                    portfolio=PortfolioContextView(
                        cash=portfolio.cash,
                        equity=eq,
                        buying_power=portfolio.cash,
                    ),
                    parameters=params,
                    strategy_id=strategy.strategy_id,
                    strategy_version=strategy.version,
                )
                decision = strategy.evaluate(ctx)
                if self.memory_hook is not None:
                    self.memory_hook.on_event(
                        decision_event(
                            timestamp=ts,
                            symbol=sym,
                            strategy_id=strategy.strategy_id,
                            strategy_version=strategy.version,
                            decision=decision,
                            market_context={
                                "close": str(bar.close),
                                "bar_index": idx,
                            },
                        )
                    )

                if decision.is_actionable:
                    qty = self.sizing.size(
                        decision,
                        equity=eq,
                        reference_price=bar.close,
                    )
                    if qty <= 0:
                        warnings.append(f"{ts.isoformat()} {sym}: sized quantity <= 0")
                        continue
                    # Exit sizing: use position size when exiting
                    if decision.action in {
                        DecisionAction.EXIT_LONG,
                        DecisionAction.EXIT_SHORT,
                    }:
                        pos = portfolio.positions.get(sym)
                        if pos is None:
                            warnings.append(
                                f"{ts.isoformat()} {sym}: exit with no position"
                            )
                            continue
                        qty = abs(pos.quantity)

                    # Simulate proposal creation (same normalized shape; no broker)
                    try:
                        proposal = self.proposal_adapter.to_proposal_input(
                            decision,
                            broker_account_id=account_id,
                            quantity=qty,
                            strategy_id=strategy.strategy_id,
                            strategy_version=strategy.version,
                            signal_reference=decision.rationale_code,
                            metadata={"backtest": True, "signal_time": ts.isoformat()},
                        )
                        simulated_proposals.append(proposal.model_dump(mode="json"))
                    except Exception as exc:  # noqa: BLE001 — capture as warning
                        warnings.append(f"proposal adaptation failed: {exc}")
                        continue

                    pending.append(
                        PendingOrder(
                            decision=_decision_with_qty(decision, qty),
                            signal_time=ts,
                            signal_bar_index=idx,
                            quantity=qty,
                            created_at_bar_index=idx,
                        )
                    )

            # 3) Equity curve point at bar close marks
            marks = {}
            for s, bars in series_by_symbol.items():
                if ts in index_maps[s]:
                    marks[s] = bars[index_maps[s][ts]].close
                else:
                    past = [t for t in index_maps[s] if t <= ts]
                    if past:
                        marks[s] = bars[index_maps[s][max(past)]].close
            unrealized = portfolio.mark_unrealized(marks)
            equity_curve.append(
                EquityPoint(
                    timestamp=ts,
                    equity=portfolio.equity(marks),
                    cash=portfolio.cash,
                    unrealized_pnl=unrealized,
                )
            )

        # Mark-to-market ending equity with last closes
        final_marks = {s: bars[-1].close for s, bars in series_by_symbol.items()}
        ending_equity = portfolio.equity(final_marks)

        trade_records = [
            BacktestTradeRecord(
                strategy_id=t.strategy_id,
                strategy_version=t.strategy_version,
                symbol=t.symbol,
                side=t.side,
                entry_time=t.entry_time,
                entry_price=t.entry_price,
                exit_time=t.exit_time,
                exit_price=t.exit_price,
                quantity=t.quantity,
                gross_pnl=t.gross_pnl,
                costs=t.costs,
                net_pnl=t.net_pnl,
                exit_reason=t.exit_reason,
                parameters=params,
            )
            for t in portfolio.closed_trades
        ]

        metrics = calculate_metrics(
            starting_capital=starting_capital,
            ending_equity=ending_equity,
            trades=portfolio.closed_trades,
            equity_curve=equity_curve,
        )
        all_warnings = list(warnings) + list(metrics.warnings)
        if pending:
            all_warnings.append(
                f"{len(pending)} order(s) still pending at end of series (no fill)"
            )
        all_warnings.append(
            "BACKTEST PERFORMANCE DOES NOT GUARANTEE FUTURE PERFORMANCE."
        )
        _ = simulated_proposals  # retained for debugging via memory if needed

        return BacktestResult(
            strategy_id=strategy.strategy_id,
            strategy_name=strategy.name,
            strategy_version=strategy.version,
            parameters=params,
            start=timeline[0] if timeline else start,
            end=timeline[-1] if timeline else end,
            symbols=[s.strip().upper() for s in symbols],
            timeframe=timeframe,
            starting_capital=starting_capital,
            ending_equity=ending_equity,
            metrics=metrics,
            trades=trade_records,
            equity_curve=equity_curve,
            warnings=all_warnings,
            execution_assumptions=dict(self.EXECUTION_ASSUMPTIONS),
            cost_assumptions=self.costs.model_dump(mode="json"),
        )


def _decision_with_qty(decision: StrategyDecision, qty: Decimal) -> StrategyDecision:
    data = decision.model_dump()
    data["quantity"] = qty
    return StrategyDecision.model_validate(data)
