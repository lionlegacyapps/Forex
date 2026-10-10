"""Associate internal broker_accounts rows with verified Alpaca PAPER accounts.

Never stores credentials. Connecting does NOT authorize trading
(is_enabled remains false by default).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.broker_state.errors import PAPER_ACCOUNT_NOT_VERIFIED, BrokerStateError
from app.broker_state.models import AccountSnapshot
from app.models.broker_account import BrokerAccount
from app.models.enums import AccountType, TradingMode

ALPACA_BROKER_SLUG = "alpaca"


def register_alpaca_paper_account(
    session: Session,
    *,
    snapshot: AccountSnapshot,
    name: str,
    account_type: AccountType = AccountType.CASH,
    is_enabled: bool = False,
) -> BrokerAccount:
    """Create or update a broker_accounts row for a verified Alpaca paper account.

    Credentials are never persisted. ``is_enabled`` defaults to False —
    CONNECTING AN ALPACA ACCOUNT DOES NOT AUTHORIZE TRADING.
    """
    if snapshot.broker != ALPACA_BROKER_SLUG:
        raise BrokerStateError(
            f"Expected broker=alpaca, got {snapshot.broker!r}",
            code=PAPER_ACCOUNT_NOT_VERIFIED,
        )
    if not snapshot.paper_verified:
        raise BrokerStateError(
            "Snapshot is not paper-verified",
            code=PAPER_ACCOUNT_NOT_VERIFIED,
        )
    if not snapshot.external_account_id:
        raise BrokerStateError(
            "external_account_id required",
            code=PAPER_ACCOUNT_NOT_VERIFIED,
        )

    existing = session.scalar(
        select(BrokerAccount).where(
            BrokerAccount.broker == ALPACA_BROKER_SLUG,
            BrokerAccount.external_account_id == snapshot.external_account_id,
        )
    )
    if existing is not None:
        # Refresh safe identity fields only; never flip enabled without explicit arg.
        existing.name = name
        existing.account_type = account_type
        existing.trading_mode = TradingMode.PAPER
        if is_enabled:
            existing.is_enabled = True
        # If is_enabled=False, leave existing flag unchanged (do not silently enable).
        session.flush()
        return existing

    account = BrokerAccount(
        name=name,
        broker=ALPACA_BROKER_SLUG,
        external_account_id=snapshot.external_account_id,
        account_type=account_type,
        trading_mode=TradingMode.PAPER,
        is_enabled=is_enabled,  # default False
    )
    session.add(account)
    session.flush()
    return account
