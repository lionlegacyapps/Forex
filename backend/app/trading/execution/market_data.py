"""Deterministic in-process simulation prices — NOT real market data.

SIMULATION RESULTS DO NOT REPRESENT REAL MARKET EXECUTION.
Prices exist only when explicitly set by tests or simulation scenarios.
No network calls. No randomness. No fabricated defaults.
"""

from __future__ import annotations

from decimal import Decimal


class PriceUnavailableError(LookupError):
    """Raised when a simulation price has not been configured for a symbol."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.reason_code = "PRICE_UNAVAILABLE"
        super().__init__(f"Simulation price unavailable for {symbol}")


class SimulationMarketData:
    """Explicitly configured simulation price board."""

    def __init__(self) -> None:
        self._prices: dict[str, Decimal] = {}

    def set_price(self, symbol: str, price: Decimal) -> None:
        sym = symbol.strip().upper()
        if price < 0:
            raise ValueError("Simulation price must be >= 0")
        self._prices[sym] = Decimal(price)

    def clear_price(self, symbol: str) -> None:
        self._prices.pop(symbol.strip().upper(), None)

    def clear_all(self) -> None:
        self._prices.clear()

    def has_price(self, symbol: str) -> bool:
        return symbol.strip().upper() in self._prices

    def get_price(self, symbol: str) -> Decimal | None:
        return self._prices.get(symbol.strip().upper())

    def require_price(self, symbol: str) -> Decimal:
        price = self.get_price(symbol)
        if price is None:
            raise PriceUnavailableError(symbol)
        return price


# Process-wide default board for simulation adapters/tests.
default_simulation_market_data = SimulationMarketData()
