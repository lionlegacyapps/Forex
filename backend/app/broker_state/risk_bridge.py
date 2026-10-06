"""Risk Engine foundation for verified broker account state.

V1 wires data structures only. Risk decisions still use internal accounting.
Broker snapshots are available for future buying-power / open-order checks.

CONNECTING AN ALPACA ACCOUNT DOES NOT AUTHORIZE TRADING.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.broker_state.models import AccountSnapshot, BrokerOrderSnapshot, BrokerPositionSnapshot


@dataclass(frozen=True)
class VerifiedBrokerState:
    """Immutable broker state bag for Risk Engine consumption (future use)."""

    account: AccountSnapshot
    positions: tuple[BrokerPositionSnapshot, ...] = ()
    open_orders: tuple[BrokerOrderSnapshot, ...] = ()

    @property
    def paper_verified(self) -> bool:
        return self.account.paper_verified

    @property
    def buying_power(self):
        return self.account.buying_power

    @property
    def cash(self):
        return self.account.cash
