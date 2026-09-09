"""Deterministic trigger catalog (Layer 1) — PDF Sections A–I."""
from __future__ import annotations

from typing import Any

import pandas as pd

from quant_layer.helpers import (
    bearish_divergence,
    bullish_divergence,
    confirmed_cross,
    crossed_above,
    crossed_below,
)
from quant_layer.indicators import build_indicator_frame

BEARISH_ONLY = {
    "death_cross", "rsi_bearish_divergence", "macd_bear_cross", "macd_zero_cross_down",
    "52w_breakdown", "donchian_breakdown", "gap_down_filter", "rsi_overbought",
    "stoch_overbought_cross", "cci_overbought", "obv_bearish_divergence",
    "bearish_engulfing", "ma_cross_down_exit", "opposing_signal_exit",
}

TRIGGER_COLUMNS: list[str] = []


def _register(df: pd.DataFrame, name: str, series: pd.Series) -> None:
    col = f"trigger_{name}"
    df[col] = series.fillna(False).astype(bool)
    if col not in TRIGGER_COLUMNS:
        TRIGGER_COLUMNS.append(col)


def compute_triggers(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    c = df["close_adj"]
    _register(df, "golden_cross", confirmed_cross(df["sma_50"], df["sma_200"], hold_days=3))
    _register(df, "death_cross", confirmed_cross(df["sma_200"], df["sma_50"], hold_days=3))
    _register(df, "price_above_sma50", crossed_above(c, df["sma_50"]))
    _register(df, "price_above_ema21", crossed_above(c, df["ema_21"]))
    _register(df, "ema9_above_ema21", crossed_above(df["ema_9"], df["ema_21"]))
    _register(df, "adx_trend_gate", (df["adx_14"] > 25) & (df["plus_di"] > df["minus_di"]))
    _register(df, "adx_range_gate", df["adx_14"] < 20)
    _register(df, "psar_bull_flip", crossed_above(c, df["psar_proxy"]))

    _register(df, "rsi_oversold_bounce", crossed_above(df["rsi_14"], 30))
    _register(df, "rsi_overbought", crossed_above(df["rsi_14"], 70))
    _register(df, "rsi_midline_cross", crossed_above(df["rsi_14"], 50))
    _register(df, "rsi_bullish_divergence", bullish_divergence(c, df["rsi_14"]))
    _register(df, "rsi_bearish_divergence", bearish_divergence(c, df["rsi_14"]))

    _register(df, "macd_bull_cross", crossed_above(df["macd"], df["macd_signal"]))
    macd_bear = crossed_below(df["macd"], df["macd_signal"])
    _register(df, "macd_bear_cross", macd_bear)
    hist = df["macd_hist"]
    _register(df, "macd_hist_flip", (hist > 0) & (hist.shift(1) <= 0))
    _register(df, "macd_zero_cross", crossed_above(df["macd"], 0))
    _register(df, "macd_zero_cross_down", crossed_below(df["macd"], 0))

    _register(df, "stoch_oversold_cross", crossed_above(df["stoch_k"], df["stoch_d"]) & (df["stoch_k"] < 20))
    _register(df, "stoch_overbought_cross", crossed_below(df["stoch_k"], df["stoch_d"]) & (df["stoch_k"] > 80))
    _register(df, "roc_positive", crossed_above(df["roc_10"], 0))
    _register(df, "willr_reversal", crossed_above(df["willr_14"], -80))
    _register(df, "cci_oversold", crossed_above(df["cci_20"], -100))
    _register(df, "cci_overbought", crossed_below(df["cci_20"], 100))
    _register(df, "mfi_oversold", crossed_above(df["mfi_14"], 20))

    _register(df, "lower_bb_touch", df["bb_percent_b"] <= 0.05)
    _register(df, "upper_bb_touch", df["bb_percent_b"] >= 0.95)
    bw = df["bb_bandwidth"]
    _register(df, "bb_squeeze", bw <= bw.rolling(120, min_periods=20).min())
    _register(df, "keltner_breakout_up", c > df["kc_upper"])
    _register(df, "keltner_breakout_down", c < df["kc_lower"])
    tr = (df["high"] - df["low"]).abs()
    _register(df, "atr_expansion", tr > 1.5 * df["atr_14"])

    _register(df, "volume_spike", df["vol_vs_avg20"] >= 2.0)
    obv = df["obv"]
    _register(df, "obv_accumulation", obv >= obv.rolling(20).max())
    _register(df, "obv_bearish_divergence", bearish_divergence(c, obv))
    _register(df, "vwap_reclaim", crossed_above(c, df["vwap"]))

    _register(df, "52w_breakout", (c > df["high_52w_prior"]) & (df["vol_vs_avg20"] >= 1.5))
    _register(df, "52w_breakdown", c < df["low_52w"].shift(1))
    _register(df, "donchian_breakout", c > df["donchian_upper_20"].shift(1))
    _register(df, "donchian_breakdown", c < df["donchian_lower_20"].shift(1))
    _register(df, "pivot_r1_break", (c > df["pivot_r1"]) & (df["vol_vs_avg20"] >= 1.2))
    _register(df, "pivot_support_hold", (df["low"] <= df["pivot_s1"]) & (c > df["pivot_s1"]))
    _register(df, "gap_up_continuation", df["is_gap_up"] & (c >= df["open"]))
    _register(df, "gap_down_filter", df["is_gap_down"])

    _register(df, "bullish_engulfing", df["candle_bullish_engulfing"] & (df["bb_percent_b"] <= 0.2))
    _register(df, "bearish_engulfing", df["candle_bearish_engulfing"] & (df["bb_percent_b"] >= 0.8))
    _register(df, "hammer_downtrend", df["candle_hammer"] & (c < df["sma_50"]))
    _register(df, "doji_extreme", df["candle_doji"] & ((df["rsi_14"] > 70) | (df["rsi_14"] < 30)))

    # Multi-timeframe gates
    weekly = df.resample("W").agg({"open": "first", "high": "max", "low": "min", "close_adj": "last", "volume": "sum"})
    if len(weekly) >= 15:
        from technicals import rsi as rsi_fn, sma as sma_fn
        w_close = weekly["close_adj"].tolist()
        weekly["weekly_rsi_14"] = rsi_fn(w_close, 14)
        weekly["weekly_sma_20"] = sma_fn(w_close, 20)
        weekly_shifted = weekly[["weekly_rsi_14", "weekly_sma_20"]].shift(1)
        aligned = weekly_shifted.reindex(df.index, method="ffill")
        df["weekly_rsi_14"] = aligned["weekly_rsi_14"]
        df["weekly_sma_20"] = aligned["weekly_sma_20"]
        _register(df, "weekly_trend_gate", (df["weekly_rsi_14"] > 50) | (c > df["weekly_sma_20"]))
    else:
        _register(df, "weekly_trend_gate", pd.Series(True, index=df.index))

    monthly = df.resample("ME").agg({"close_adj": "last"})
    if len(monthly) >= 10:
        from technicals import sma as sma_fn
        m_close = monthly["close_adj"].tolist()
        monthly["monthly_sma_10"] = sma_fn(m_close, 10)
        m_aligned = monthly[["monthly_sma_10"]].shift(1).reindex(df.index, method="ffill")
        df["monthly_sma_10"] = m_aligned["monthly_sma_10"]
        _register(df, "monthly_context_gate", c > df["monthly_sma_10"])
    else:
        _register(df, "monthly_context_gate", pd.Series(True, index=df.index))

    # Exit triggers (for open positions review)
    _register(df, "rsi_overbought_exit", crossed_above(df["rsi_14"], 70))
    _register(df, "atr_stop_proxy", c < (c.rolling(5).max() - 2 * df["atr_14"]))
    _register(df, "ma_cross_down_exit", crossed_below(c, df["ema_21"]))
    _register(df, "opposing_signal_exit", macd_bear | crossed_above(df["rsi_14"], 70))

    return df


def build_trigger_frame(rows: list[dict]) -> pd.DataFrame:
    global TRIGGER_COLUMNS
    TRIGGER_COLUMNS = []
    df = build_indicator_frame(rows)
    if df.empty:
        return df
    return compute_triggers(df)


def fired_triggers(row: pd.Series) -> list[str]:
    return [
        col.replace("trigger_", "")
        for col in TRIGGER_COLUMNS
        if col in row.index and bool(row[col])
    ]


def any_entry_trigger(row: pd.Series) -> bool:
    fired = set(fired_triggers(row))
    if fired & BEARISH_ONLY:
        return False
    entry_like = fired - BEARISH_ONLY - {"adx_range_gate", "gap_down_filter", "doji_extreme"}
    return len(entry_like) > 0


def trigger_summary(row: pd.Series, market_regime: dict[str, Any] | None = None) -> dict[str, Any]:
    from quant_layer.regime_router import filter_triggers_by_regime, route_regime

    fired = fired_triggers(row)
    route = route_regime(row, market_regime)
    routed = filter_triggers_by_regime(fired, route)
    regime = "trend" if bool(row.get("trigger_adx_trend_gate")) else (
        "range" if bool(row.get("trigger_adx_range_gate")) else "mixed"
    )
    return {
        "triggers_fired": routed,
        "trigger_count": len(routed),
        "all_triggers_fired": fired,
        "regime_hint": regime,
        "regime_route": route.get("mode"),
        "weekly_gate_ok": bool(row.get("trigger_weekly_trend_gate", True)),
        "monthly_gate_ok": bool(row.get("trigger_monthly_context_gate", True)),
    }
