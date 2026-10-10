"""RSI + MACD trend confirmation — first-party reference strategy.

Independently specified rules using public-domain indicator formulas.
NOT derived from Freqtrade (GPL-3.0) source code.
NOT a profitability claim. Trading is not auto-enabled.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.indicators.macd import macd
from app.indicators.rsi import rsi
from app.models.enums import AssetClass, OrderType
from app.strategies.context import StrategyContext
from app.strategies.decision import DecisionAction, StrategyDecision, no_action
from app.strategies.errors import StrategyParameterError
from app.strategies.protocol import Strategy


class RSIMACDTrendStrategy(Strategy):
    """Enter long on RSI oversold recovery confirmed by MACD bullish cross/state.

    Exit on RSI overbought or MACD bearish cross.
    """

    @property
    def strategy_id(self) -> str:
        return "rsi_macd_trend"

    @property
    def name(self) -> str:
        return "RSI + MACD Trend Confirmation (Reference)"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def supported_asset_classes(self) -> frozenset[AssetClass]:
        return frozenset({AssetClass.EQUITY, AssetClass.CRYPTO})

    @property
    def required_timeframes(self) -> frozenset[str]:
        return frozenset({"1Day"})

    def default_parameters(self) -> dict[str, Any]:
        return {
            "rsi_period": 14,
            "rsi_oversold": 30,
            "rsi_overbought": 70,
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            "quantity": "1",
            "stop_loss_pct": "0.05",
            "require_macd_cross": True,
        }

    def _validate_parameters(self, parameters: dict[str, Any]) -> None:
        try:
            rsi_period = int(parameters["rsi_period"])
            oversold = Decimal(str(parameters["rsi_oversold"]))
            overbought = Decimal(str(parameters["rsi_overbought"]))
            fast = int(parameters["macd_fast"])
            slow = int(parameters["macd_slow"])
            signal = int(parameters["macd_signal"])
            qty = Decimal(str(parameters["quantity"]))
            stop = Decimal(str(parameters["stop_loss_pct"]))
        except Exception as exc:
            raise StrategyParameterError("invalid parameter types", code="invalid_params") from exc
        if rsi_period < 2:
            raise StrategyParameterError("rsi_period must be >= 2", code="invalid_rsi_period")
        if not (0 < oversold < overbought < 100):
            raise StrategyParameterError(
                "require 0 < rsi_oversold < rsi_overbought < 100",
                code="invalid_rsi_thresholds",
            )
        if fast < 1 or slow < 1 or signal < 1 or fast >= slow:
            raise StrategyParameterError("invalid MACD periods", code="invalid_macd")
        if qty <= 0:
            raise StrategyParameterError("quantity must be positive", code="invalid_quantity")
        if stop < 0 or stop >= 1:
            raise StrategyParameterError(
                "stop_loss_pct must be in [0, 1)",
                code="invalid_stop",
            )
        if not isinstance(parameters.get("require_macd_cross", True), bool):
            raise StrategyParameterError(
                "require_macd_cross must be bool",
                code="invalid_require_cross",
            )

    def evaluate(self, context: StrategyContext) -> StrategyDecision:
        params = self.validate_parameters(context.parameters or {})
        closes = context.closes
        warm = max(
            int(params["rsi_period"]) + 1,
            int(params["macd_slow"]) + int(params["macd_signal"]),
        )
        if len(closes) < warm + 1:
            return no_action(rationale_code="insufficient_bars")

        rsi_vals = rsi(closes, int(params["rsi_period"]))
        macd_line, signal_line, hist = macd(
            closes,
            fast=int(params["macd_fast"]),
            slow=int(params["macd_slow"]),
            signal=int(params["macd_signal"]),
        )
        i = len(closes) - 1
        r_now, r_prev = rsi_vals[i], rsi_vals[i - 1]
        m_now, m_prev = macd_line[i], macd_line[i - 1]
        s_now, s_prev = signal_line[i], signal_line[i - 1]
        h_now = hist[i]

        if None in (r_now, r_prev, m_now, m_prev, s_now, s_prev, h_now):
            return no_action(rationale_code="indicator_warmup")

        assert r_now is not None and r_prev is not None
        assert m_now is not None and m_prev is not None
        assert s_now is not None and s_prev is not None
        assert h_now is not None

        oversold = Decimal(str(params["rsi_oversold"]))
        overbought = Decimal(str(params["rsi_overbought"]))
        require_cross = bool(params["require_macd_cross"])
        qty = Decimal(str(params["quantity"]))
        stop_pct = Decimal(str(params["stop_loss_pct"]))

        rsi_recovered = r_prev <= oversold and r_now > oversold
        macd_bull = m_now > s_now
        macd_cross_up = m_prev <= s_prev and m_now > s_now
        macd_cross_down = m_prev >= s_prev and m_now < s_now
        rsi_overbought_cross = r_prev < overbought and r_now >= overbought

        meta = {
            "rsi": str(r_now),
            "macd": str(m_now),
            "macd_signal": str(s_now),
            "macd_hist": str(h_now),
            "source": "independent_public_formulas",
            "freqtrade_code_used": False,
        }

        pos = context.position
        is_long = pos is not None and pos.is_long
        is_flat = pos is None or pos.is_flat

        stop_loss = None
        if context.reference_price is not None and stop_pct > 0:
            stop_loss = context.reference_price * (Decimal("1") - stop_pct)

        if is_flat and rsi_recovered and macd_bull and (
            macd_cross_up if require_cross else True
        ):
            return StrategyDecision(
                action=DecisionAction.ENTER_LONG,
                symbol=context.symbol,
                asset_class=context.asset_class,
                quantity=qty,
                order_type=OrderType.MARKET,
                stop_loss_price=stop_loss,
                rationale_code="rsi_macd_enter_long",
                rationale="RSI recovered from oversold with MACD confirmation",
                signal_metadata=meta,
            )

        if is_long and (rsi_overbought_cross or macd_cross_down):
            return StrategyDecision(
                action=DecisionAction.EXIT_LONG,
                symbol=context.symbol,
                asset_class=context.asset_class,
                quantity=abs(pos.quantity) if pos else qty,
                order_type=OrderType.MARKET,
                rationale_code="rsi_macd_exit_long",
                rationale="RSI overbought or MACD bearish cross",
                signal_metadata=meta,
            )

        return no_action(rationale_code="no_signal", rationale="No RSI/MACD confirmation")
