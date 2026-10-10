"""Internal reference strategies for framework testing only.

These are NOT claimed to be profitable.
"""

from app.strategies.reference.rsi_macd_trend import RSIMACDTrendStrategy
from app.strategies.reference.sma_crossover import SMACrossoverStrategy

__all__ = ["RSIMACDTrendStrategy", "SMACrossoverStrategy"]
