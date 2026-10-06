"""Simple deterministic simulated cash / buying-power ledger.

Not a real margin model. Cash changes on fills only:
- BUY reduces cash by qty * price + commission
- SELL increases cash by qty * price - commission
"""

from __future__ import annotations

import uuid
from decimal import Decimal


class SimulatedCashLedger:
    def __init__(self, *, starting_cash: Decimal = Decimal("100000")) -> None:
        self._starting = Decimal(starting_cash)
        self._cash: dict[uuid.UUID, Decimal] = {}

    def ensure_account(self, account_id: uuid.UUID, *, starting_cash: Decimal | None = None) -> None:
        if account_id not in self._cash:
            self._cash[account_id] = (
                Decimal(starting_cash) if starting_cash is not None else self._starting
            )

    def get_cash(self, account_id: uuid.UUID) -> Decimal:
        self.ensure_account(account_id)
        return self._cash[account_id]

    def get_buying_power(self, account_id: uuid.UUID) -> Decimal:
        # V1: buying power == cash (no leverage / margin).
        return self.get_cash(account_id)

    def apply_fill(
        self,
        account_id: uuid.UUID,
        *,
        side: str,
        quantity: Decimal,
        price: Decimal,
        commission: Decimal = Decimal("0"),
    ) -> Decimal:
        self.ensure_account(account_id)
        notional = quantity * price
        if side == "buy":
            self._cash[account_id] -= notional + commission
        else:
            self._cash[account_id] += notional - commission
        return self._cash[account_id]


default_cash_ledger = SimulatedCashLedger()
