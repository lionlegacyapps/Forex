"""Historical market data abstraction for offline backtesting.

Historical backtesting must not depend directly on Alpaca or any live broker.
Future sources (Alpaca, Polygon, Databento, Parquet/CSV) implement this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal

from app.backtesting.errors import HistoricalDataError
from app.market_data.models import Bar, MarketDataAssetClass


class HistoricalMarketDataProvider(ABC):
    """Provider-independent historical OHLCV access."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...

    @abstractmethod
    def get_bars(
        self,
        symbol: str,
        timeframe: str,
        start: datetime | None,
        end: datetime | None,
        *,
        asset_class: MarketDataAssetClass = MarketDataAssetClass.EQUITY,
    ) -> list[Bar]:
        """Return normalized bars sorted ascending by timestamp (no lookahead)."""


class InMemoryHistoricalMarketDataProvider(HistoricalMarketDataProvider):
    """Deterministic in-memory OHLCV sequences for reproducible tests."""

    def __init__(self) -> None:
        # key: (symbol, timeframe) → sorted bars
        self._bars: dict[tuple[str, str], list[Bar]] = {}

    @property
    def provider_name(self) -> str:
        return "in_memory_historical"

    def load_bars(
        self,
        symbol: str,
        timeframe: str,
        bars: list[Bar],
        *,
        replace: bool = True,
    ) -> None:
        sym = symbol.strip().upper()
        if not sym:
            raise HistoricalDataError("symbol must be non-empty", code="invalid_symbol")
        if not timeframe.strip():
            raise HistoricalDataError("timeframe must be non-empty", code="invalid_timeframe")
        validated = [_validate_bar(b, expected_symbol=sym, expected_timeframe=timeframe) for b in bars]
        validated.sort(key=lambda b: b.timestamp)
        _assert_strictly_increasing(validated)
        key = (sym, timeframe)
        if replace or key not in self._bars:
            self._bars[key] = validated
        else:
            merged = self._bars[key] + validated
            merged.sort(key=lambda b: b.timestamp)
            _assert_strictly_increasing(merged)
            self._bars[key] = merged

    def get_bars(
        self,
        symbol: str,
        timeframe: str,
        start: datetime | None,
        end: datetime | None,
        *,
        asset_class: MarketDataAssetClass = MarketDataAssetClass.EQUITY,
    ) -> list[Bar]:
        _ = asset_class
        sym = symbol.strip().upper()
        key = (sym, timeframe)
        series = self._bars.get(key)
        if series is None:
            raise HistoricalDataError(
                f"No historical bars loaded for {sym} {timeframe}",
                code="bars_not_found",
            )
        out: list[Bar] = []
        for bar in series:
            if start is not None and bar.timestamp < start:
                continue
            if end is not None and bar.timestamp > end:
                continue
            out.append(bar)
        return out


def _validate_bar(bar: Bar, *, expected_symbol: str, expected_timeframe: str) -> Bar:
    if bar.symbol.strip().upper() != expected_symbol:
        raise HistoricalDataError(
            f"Bar symbol {bar.symbol!r} does not match {expected_symbol!r}",
            code="symbol_mismatch",
        )
    if bar.timeframe != expected_timeframe:
        raise HistoricalDataError(
            f"Bar timeframe {bar.timeframe!r} does not match {expected_timeframe!r}",
            code="timeframe_mismatch",
        )
    if bar.high < bar.low:
        raise HistoricalDataError("Bar high < low", code="invalid_ohlc")
    if bar.open < 0 or bar.high < 0 or bar.low < 0 or bar.close < 0:
        raise HistoricalDataError("Negative OHLC not allowed", code="invalid_ohlc")
    # High/low must contain open/close
    if bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close):
        raise HistoricalDataError(
            "OHLC inconsistency: high/low must span open/close",
            code="invalid_ohlc",
        )
    if bar.volume is not None and bar.volume < 0:
        raise HistoricalDataError("Negative volume", code="invalid_volume")
    return bar


def _assert_strictly_increasing(bars: list[Bar]) -> None:
    for i in range(1, len(bars)):
        if bars[i].timestamp <= bars[i - 1].timestamp:
            raise HistoricalDataError(
                "Bars must be strictly increasing by timestamp",
                code="non_monotonic_bars",
            )


def make_bar(
    symbol: str,
    timestamp: datetime,
    open: str | Decimal,
    high: str | Decimal,
    low: str | Decimal,
    close: str | Decimal,
    *,
    volume: str | Decimal | None = "1000",
    timeframe: str = "1Day",
    provider: str = "in_memory_historical",
    asset_class: MarketDataAssetClass = MarketDataAssetClass.EQUITY,
) -> Bar:
    """Helper to build a normalized Bar for tests/datasets."""
    return Bar(
        symbol=symbol.strip().upper(),
        open=Decimal(str(open)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=None if volume is None else Decimal(str(volume)),
        timestamp=timestamp,
        timeframe=timeframe,
        provider=provider,
        asset_class=asset_class,
    )
