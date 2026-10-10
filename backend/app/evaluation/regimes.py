"""Deterministic market regime classification (point-in-time only)."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field

from app.indicators.atr import atr
from app.indicators.ema import ema, sma
from app.indicators.macd import macd
from app.indicators.rsi import rsi
from app.market_data.models import Bar


class MarketRegime(StrEnum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    UNKNOWN = "unknown"


class RegimeClassifierConfig(BaseModel):
    trend_ema_fast: int = 10
    trend_ema_slow: int = 30
    ranging_band_pct: Decimal = Field(default=Decimal("0.01"))
    atr_period: int = 14
    atr_high_mult: Decimal = Field(default=Decimal("1.5"))
    atr_low_mult: Decimal = Field(default=Decimal("0.5"))
    rsi_period: int = 14
    volume_lookback: int = 20


class MarketContextSnapshot(BaseModel):
    """Point-in-time market features + multi-label regimes."""

    symbol: str
    timeframe: str
    timestamp: str  # ISO
    bar_index: int
    close: Decimal
    trend_direction: str | None = None  # up|down|flat|None
    trend_strength: Decimal | None = None
    momentum: Decimal | None = None
    rsi: Decimal | None = None
    macd_hist: Decimal | None = None
    atr: Decimal | None = None
    atr_pct: Decimal | None = None
    realized_vol_proxy: Decimal | None = None
    volume: Decimal | None = None
    volume_ratio: Decimal | None = None
    regimes: list[MarketRegime] = Field(default_factory=list)
    warmup_complete: bool = False
    warnings: list[str] = Field(default_factory=list)


def classify_market_context(
    bars: list[Bar],
    *,
    as_of_index: int,
    timeframe: str,
    config: RegimeClassifierConfig | None = None,
) -> MarketContextSnapshot:
    """Classify using bars ``[0..as_of_index]`` only — no future leakage."""
    cfg = config or RegimeClassifierConfig()
    if as_of_index < 0 or as_of_index >= len(bars):
        raise ValueError("as_of_index out of range")
    visible = bars[: as_of_index + 1]
    symbol = visible[-1].symbol.strip().upper()
    closes = [b.close for b in visible]
    highs = [b.high for b in visible]
    lows = [b.low for b in visible]
    volumes = [b.volume for b in visible]
    warnings: list[str] = []
    need = max(cfg.trend_ema_slow, cfg.atr_period, cfg.rsi_period, cfg.volume_lookback) + 1
    warmup = len(visible) >= need

    fast = ema(closes, cfg.trend_ema_fast)
    slow = ema(closes, cfg.trend_ema_slow)
    rsi_vals = rsi(closes, cfg.rsi_period)
    _, _, hist = macd(closes, fast=12, slow=26, signal=9)
    atr_vals = atr(highs, lows, closes, cfg.atr_period)
    sma_close = sma(closes, cfg.trend_ema_slow)

    i = len(visible) - 1
    f, s = fast[i], slow[i]
    r = rsi_vals[i]
    h = hist[i] if i < len(hist) else None
    a = atr_vals[i]
    mid = sma_close[i]
    close = closes[i]

    trend_direction = None
    trend_strength = None
    regimes: list[MarketRegime] = []

    if f is not None and s is not None and mid is not None and mid != 0:
        gap = (f - s) / mid
        trend_strength = abs(gap)
        band = cfg.ranging_band_pct
        if gap > band:
            trend_direction = "up"
            regimes.append(MarketRegime.TRENDING_UP)
        elif gap < -band:
            trend_direction = "down"
            regimes.append(MarketRegime.TRENDING_DOWN)
        else:
            trend_direction = "flat"
            regimes.append(MarketRegime.RANGING)
    else:
        warnings.append("insufficient_warmup_for_trend")

    atr_pct = None
    realized = None
    if a is not None and close != 0:
        atr_pct = a / close
        # Compare to median ATR% over available history (point-in-time)
        atr_pcts = [
            atr_vals[j] / closes[j]
            for j in range(len(visible))
            if atr_vals[j] is not None and closes[j] != 0
        ]
        if atr_pcts:
            sorted_ap = sorted(atr_pcts)
            median = sorted_ap[len(sorted_ap) // 2]
            realized = atr_pct
            if median > 0:
                if atr_pct >= median * cfg.atr_high_mult:
                    regimes.append(MarketRegime.HIGH_VOLATILITY)
                elif atr_pct <= median * cfg.atr_low_mult:
                    regimes.append(MarketRegime.LOW_VOLATILITY)
    else:
        warnings.append("insufficient_warmup_for_volatility")

    momentum = None
    if len(closes) >= 6 and closes[-6] != 0:
        momentum = closes[-1] / closes[-6] - Decimal("1")

    vol = volumes[-1]
    vol_ratio = None
    if vol is not None:
        prior = [v for v in volumes[-cfg.volume_lookback - 1 : -1] if v is not None]
        if prior:
            avg = sum(prior, Decimal("0")) / Decimal(len(prior))
            if avg > 0:
                vol_ratio = vol / avg

    if not regimes:
        regimes = [MarketRegime.UNKNOWN]
        if not warmup:
            warnings.append("insufficient_warmup_history")

    return MarketContextSnapshot(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=visible[-1].timestamp.isoformat(),
        bar_index=as_of_index,
        close=close,
        trend_direction=trend_direction,
        trend_strength=trend_strength,
        momentum=momentum,
        rsi=r,
        macd_hist=h,
        atr=a,
        atr_pct=atr_pct,
        realized_vol_proxy=realized,
        volume=vol,
        volume_ratio=vol_ratio,
        regimes=regimes,
        warmup_complete=warmup,
        warnings=warnings,
    )


def index_at_or_before(bars: list[Bar], timestamp) -> int | None:
    """Largest index with bar.timestamp <= timestamp (no future)."""
    idx = None
    for i, b in enumerate(bars):
        if b.timestamp <= timestamp:
            idx = i
        else:
            break
    return idx
