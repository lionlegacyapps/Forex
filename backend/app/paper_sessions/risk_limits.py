"""Session-level risk limits — fail closed when incomplete."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.paper_sessions.errors import ActivationRejectedError


class SessionRiskLimits(BaseModel):
    max_position_size: Decimal
    max_notional_exposure: Decimal
    max_daily_loss: Decimal
    max_orders_per_session: int = Field(gt=0)
    max_concurrent_positions: int = Field(gt=0)
    allowed_instrument: str
    require_stop_loss: bool = True
    market_data_max_age_seconds: int = Field(default=120, gt=0)
    max_session_duration_seconds: int = Field(default=86400, gt=0)

    @model_validator(mode="after")
    def _positive(self) -> SessionRiskLimits:
        for name in (
            "max_position_size",
            "max_notional_exposure",
            "max_daily_loss",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be > 0")
        self.allowed_instrument = self.allowed_instrument.strip().upper()
        if not self.allowed_instrument:
            raise ValueError("allowed_instrument required")
        return self

    def to_storage(self) -> dict:
        return self.model_dump(mode="json")

    @classmethod
    def from_storage(cls, data: dict | None) -> SessionRiskLimits:
        if not data:
            raise ActivationRejectedError(
                "session risk limits missing", code="missing_risk_limits"
            )
        try:
            return cls.model_validate(data)
        except Exception as exc:  # noqa: BLE001
            raise ActivationRejectedError(
                f"invalid session risk limits: {exc}",
                code="invalid_risk_limits",
            ) from exc
