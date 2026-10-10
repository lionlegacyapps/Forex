"""Supervised single-strategy paper pilot configuration.

Separate from production defaults. Fail-closed. No broker credentials.
PAPER_SESSION_EXECUTE_ENABLED must remain false for this preparation milestone.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.config import Settings, get_settings
from app.paper_sessions.risk_limits import SessionRiskLimits

# First-party reference strategy used for preparation (honest signals; may NO_ACTION).
DEFAULT_PILOT_STRATEGY_ID = "sma_crossover"
DEFAULT_PILOT_STRATEGY_VERSION = "1.0.0"
DEFAULT_PILOT_SYMBOL = "AAPL"
DEFAULT_PILOT_TIMEFRAME = "1Day"


class PilotConfigError(ValueError):
    """Invalid or permissive pilot configuration."""


class PilotConfig(BaseModel):
    """Tightly constrained pilot parameters — never silent permissive defaults."""

    strategy_id: str = DEFAULT_PILOT_STRATEGY_ID
    strategy_version: str = DEFAULT_PILOT_STRATEGY_VERSION
    parameters: dict[str, Any] = Field(default_factory=dict)
    symbol: str = DEFAULT_PILOT_SYMBOL
    timeframe: str = DEFAULT_PILOT_TIMEFRAME
    max_quantity: Decimal = Decimal("1")
    max_notional: Decimal = Decimal("500")
    max_daily_loss: Decimal = Decimal("100")
    max_orders_per_session: int = 1
    max_concurrent_positions: int = 1
    max_outstanding_orders: int = 1
    max_session_duration_seconds: int = 3600
    market_data_max_age_seconds: int = 86400
    consent_ttl_seconds: int = 900
    require_stop_loss: bool = True
    # Preparation milestone: never auto-enable real paper execute.
    allow_real_paper_submit: bool = False
    background_worker_allowed: bool = False

    @field_validator("symbol")
    @classmethod
    def _symbol(cls, v: str) -> str:
        s = (v or "").strip().upper()
        if not s:
            raise PilotConfigError("symbol required")
        return s

    @field_validator("strategy_id", "strategy_version", "timeframe")
    @classmethod
    def _nonempty(cls, v: str) -> str:
        if not (v or "").strip():
            raise PilotConfigError("required string field empty")
        return v.strip()

    @model_validator(mode="after")
    def _conservative(self) -> PilotConfig:
        if self.max_quantity <= 0:
            raise PilotConfigError("max_quantity must be > 0")
        if self.max_quantity > Decimal("10"):
            raise PilotConfigError("pilot max_quantity exceeds hard cap of 10")
        if self.max_notional <= 0:
            raise PilotConfigError("max_notional must be > 0")
        if self.max_notional > Decimal("5000"):
            raise PilotConfigError("pilot max_notional exceeds hard cap of 5000")
        if self.max_daily_loss <= 0:
            raise PilotConfigError("max_daily_loss must be > 0")
        if self.max_orders_per_session != 1:
            raise PilotConfigError("pilot requires max_orders_per_session == 1")
        if self.max_outstanding_orders != 1:
            raise PilotConfigError("pilot requires max_outstanding_orders == 1")
        if self.max_concurrent_positions < 1:
            raise PilotConfigError("max_concurrent_positions must be >= 1")
        if self.max_session_duration_seconds <= 0 or self.max_session_duration_seconds > 86400:
            raise PilotConfigError("max_session_duration_seconds out of range")
        if self.consent_ttl_seconds <= 0 or self.consent_ttl_seconds > 3600:
            raise PilotConfigError("consent_ttl_seconds must be 1..3600 for pilot")
        if self.allow_real_paper_submit:
            raise PilotConfigError(
                "allow_real_paper_submit must be false for Pilot Preparation V1"
            )
        if self.background_worker_allowed:
            raise PilotConfigError(
                "background_worker_allowed must be false for Pilot Preparation V1"
            )
        return self

    def to_session_risk_limits(self) -> SessionRiskLimits:
        return SessionRiskLimits(
            max_position_size=self.max_quantity,
            max_notional_exposure=self.max_notional,
            max_daily_loss=self.max_daily_loss,
            max_orders_per_session=self.max_orders_per_session,
            max_concurrent_positions=self.max_concurrent_positions,
            allowed_instrument=self.symbol,
            require_stop_loss=self.require_stop_loss,
            market_data_max_age_seconds=self.market_data_max_age_seconds,
            max_session_duration_seconds=self.max_session_duration_seconds,
        )


def default_pilot_config(*, parameters: dict[str, Any] | None = None) -> PilotConfig:
    """Conservative first-party SMA crossover pilot (preparation only)."""
    return PilotConfig(
        strategy_id=DEFAULT_PILOT_STRATEGY_ID,
        strategy_version=DEFAULT_PILOT_STRATEGY_VERSION,
        parameters=dict(parameters or {"fast_period": 3, "slow_period": 5, "quantity": "1"}),
        symbol=DEFAULT_PILOT_SYMBOL,
        timeframe=DEFAULT_PILOT_TIMEFRAME,
        max_quantity=Decimal("1"),
        max_notional=Decimal("500"),
        max_daily_loss=Decimal("100"),
        max_orders_per_session=1,
        max_concurrent_positions=1,
        max_outstanding_orders=1,
        max_session_duration_seconds=3600,
        market_data_max_age_seconds=86400,
        consent_ttl_seconds=900,
        require_stop_loss=True,
        allow_real_paper_submit=False,
        background_worker_allowed=False,
    )


def assert_deployment_execute_disabled(settings: Settings | None = None) -> None:
    """Fail closed if deployment execution flag is enabled during preparation."""
    cfg = settings or get_settings()
    if cfg.paper_session_execute_enabled:
        raise PilotConfigError(
            "PAPER_SESSION_EXECUTE_ENABLED must be false during Pilot Preparation V1"
        )
