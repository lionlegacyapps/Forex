"""Idempotent Alpaca paper broker account registration (no credentials stored)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.broker_state.models import AccountSnapshot
from app.broker_state.readers.alpaca_paper import (
    AlpacaPaperAccountReader,
    assert_paper_base_url,
)
from app.broker_state.registration import register_alpaca_paper_account
from app.core.config import Settings, get_settings
from app.models.broker_account import BrokerAccount
from app.models.enums import AccountType, TradingMode
from app.onboarding.errors import OnboardingBlockedError, OnboardingError
from app.qualification.auth import AuthenticatedOwner

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PaperAccountRegistrationResult:
    account_id: str
    external_account_id_masked: str
    trading_mode: str
    is_enabled: bool
    created_new: bool
    paper_endpoint_host: str


def _mask_external_id(external_id: str) -> str:
    ext = (external_id or "").strip()
    if len(ext) < 8:
        return "***"
    return f"{ext[:4]}…{ext[-4:]}"


async def verify_and_register_alpaca_paper_account(
    db: Session,
    *,
    owner: AuthenticatedOwner,
    settings: Settings | None = None,
    name: str = "Alpaca Paper (Pilot)",
    enable_account: bool = False,
    reader: AlpacaPaperAccountReader | None = None,
) -> PaperAccountRegistrationResult:
    """Verify live paper identity, then register/update broker_accounts.

    Requires an authenticated owner. Never stores API secrets.
    Never registers a live account. Idempotent on external_account_id.
    ``enable_account`` defaults False — connecting ≠ authorizing trading.
    """
    _ = owner  # authorization prerequisite enforced by caller type
    cfg = settings or get_settings()
    if not cfg.alpaca_api_key or not cfg.alpaca_api_secret:
        raise OnboardingBlockedError(
            "ALPACA_API_KEY / ALPACA_API_SECRET missing in private environment",
            code="alpaca_credentials_missing",
        )

    try:
        base = assert_paper_base_url(cfg.alpaca_paper_base_url)
    except Exception as exc:  # noqa: BLE001
        raise OnboardingBlockedError(
            f"Alpaca paper endpoint rejected: {exc}",
            code="paper_endpoint_rejected",
        ) from exc

    host = (urlparse(base).hostname or "").lower()
    if host != "paper-api.alpaca.markets":
        raise OnboardingBlockedError(
            f"Refusing non-paper host {host!r}",
            code="live_endpoint_rejected",
        )

    owns_reader = reader is None
    paper_reader = reader or AlpacaPaperAccountReader(
        api_key=cfg.alpaca_api_key,
        api_secret=cfg.alpaca_api_secret,
        base_url=base,
        timeout_seconds=cfg.alpaca_paper_timeout_seconds,
    )
    try:
        snapshot: AccountSnapshot = await paper_reader.get_account()
    finally:
        # Reader holds credentials in memory only; no persistence.
        if owns_reader:
            pass

    if not snapshot.paper_verified:
        raise OnboardingBlockedError(
            "Alpaca account snapshot is not paper-verified",
            code="paper_not_verified",
        )
    if snapshot.broker != "alpaca":
        raise OnboardingError("unexpected broker slug", code="broker_mismatch")

    # Detect prior row for created_new flag
    from sqlalchemy import select

    prior = db.scalar(
        select(BrokerAccount).where(
            BrokerAccount.broker == "alpaca",
            BrokerAccount.external_account_id == snapshot.external_account_id,
        )
    )
    created_new = prior is None

    # Guard: never allow flipping an existing LIVE row via this path
    if prior is not None and prior.trading_mode != TradingMode.PAPER:
        raise OnboardingBlockedError(
            "Existing broker account is not PAPER; refusing to treat as paper",
            code="live_account_conflict",
        )

    account = register_alpaca_paper_account(
        db,
        snapshot=snapshot,
        name=name,
        account_type=AccountType.CASH,
        is_enabled=enable_account,
    )
    if account.trading_mode != TradingMode.PAPER:
        raise OnboardingBlockedError(
            "Registered account trading_mode is not paper",
            code="live_account_rejected",
        )

    logger.info(
        "alpaca_paper_account_registered",
        extra={
            "external_masked": _mask_external_id(account.external_account_id or ""),
            "enabled": account.is_enabled,
            "created_new": created_new,
            "owner_subject_present": bool(owner.subject),
        },
    )
    return PaperAccountRegistrationResult(
        account_id=str(account.id),
        external_account_id_masked=_mask_external_id(account.external_account_id or ""),
        trading_mode=account.trading_mode.value,
        is_enabled=account.is_enabled,
        created_new=created_new,
        paper_endpoint_host=host,
    )
