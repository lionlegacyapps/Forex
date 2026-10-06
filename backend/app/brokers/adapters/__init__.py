"""Concrete broker adapters.

Safety Pipeline V1 ships only SimulationBroker.
Real broker SDKs (Alpaca, Tradovate, IBKR, crypto exchanges) must NOT be
imported or configured here.
"""

from app.brokers.adapters.simulation import SIMULATION_PROVIDER, SimulationBroker

__all__ = ["SimulationBroker", "SIMULATION_PROVIDER"]
