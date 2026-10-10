"""Convert platform historical bars into research frames.

Normalized OHLCV only. No automatic external dataset downloads.
Timezone-aware timestamps required. Chronological order enforced.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.backtesting.errors import HistoricalDataError
from app.market_data.models import Bar


class ResearchBarRow(BaseModel):
    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None = None
    timeframe: str

    @field_validator("symbol")
    @classmethod
    def _sym(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("timestamp")
    @classmethod
    def _tz(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        return value


class ResearchBarFrame(BaseModel):
    symbol: str
    timeframe: str
    rows: list[ResearchBarRow] = Field(default_factory=list)
    price_convention: str = "as_provided"  # adjusted prices not assumed
    data_version: str = "v1-fixture"

    @property
    def closes(self) -> list[Decimal]:
        return [r.close for r in self.rows]

    @property
    def timestamps(self) -> list[datetime]:
        return [r.timestamp for r in self.rows]


def bars_to_research_frame(
    bars: list[Bar],
    *,
    data_version: str = "v1-fixture",
    price_convention: str = "as_provided",
) -> ResearchBarFrame:
    if not bars:
        raise HistoricalDataError("No bars provided for research frame", code="empty_bars")

    symbol = bars[0].symbol.strip().upper()
    timeframe = bars[0].timeframe
    rows: list[ResearchBarRow] = []
    prev_ts: datetime | None = None

    for bar in bars:
        if bar.symbol.strip().upper() != symbol:
            raise HistoricalDataError("Mixed symbols in bar list", code="mixed_symbols")
        if bar.timeframe != timeframe:
            raise HistoricalDataError("Mixed timeframes in bar list", code="mixed_timeframes")
        if bar.timestamp.tzinfo is None:
            raise HistoricalDataError(
                "Bar timestamp must be timezone-aware",
                code="naive_timestamp",
            )
        if prev_ts is not None and bar.timestamp <= prev_ts:
            raise HistoricalDataError(
                "Bars must be strictly chronological",
                code="non_monotonic_bars",
            )
        if bar.high < bar.low:
            raise HistoricalDataError("Invalid OHLC high < low", code="invalid_ohlc")
        rows.append(
            ResearchBarRow(
                symbol=symbol,
                timestamp=bar.timestamp,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                timeframe=timeframe,
            )
        )
        prev_ts = bar.timestamp

    return ResearchBarFrame(
        symbol=symbol,
        timeframe=timeframe,
        rows=rows,
        price_convention=price_convention,
        data_version=data_version,
    )
