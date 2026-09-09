"""Regime router — enable trigger families based on ADX / market regime."""
from __future__ import annotations

from typing import Any

import pandas as pd

TREND_TRIGGERS = {
    "golden_cross", "price_above_sma50", "price_above_ema21", "ema9_above_ema21",
    "52w_breakout", "donchian_breakout", "pivot_r1_break", "macd_zero_cross",
    "gap_up_continuation",
}
MEAN_REVERSION_TRIGGERS = {
    "rsi_oversold_bounce", "rsi_bullish_divergence", "lower_bb_touch",
    "stoch_oversold_cross", "willr_reversal", "cci_oversold", "mfi_oversold",
    "pivot_support_hold",
}


def route_regime(row: pd.Series, market_regime: dict[str, Any] | None = None) -> dict[str, Any]:
    adx = float(row.get("adx_14") or 0)
    regime = (market_regime or {}).get("regime")
    if regime in ("trending_up", "trending_down", "high_volatility"):
        mode = "trend"
    elif regime == "range_bound" or adx < 20:
        mode = "mean_reversion"
    elif adx > 25:
        mode = "trend"
    else:
        mode = "mixed"
    preferred = TREND_TRIGGERS if mode == "trend" else (
        MEAN_REVERSION_TRIGGERS if mode == "mean_reversion" else TREND_TRIGGERS | MEAN_REVERSION_TRIGGERS
    )
    return {"mode": mode, "preferred_triggers": sorted(preferred)}


def filter_triggers_by_regime(fired: list[str], route: dict[str, Any]) -> list[str]:
    preferred = set(route.get("preferred_triggers") or [])
    if not preferred:
        return fired
    matched = [t for t in fired if t in preferred]
    return matched if matched else fired
