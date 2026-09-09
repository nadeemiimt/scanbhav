"""Indicator columns for Layer 1 — pandas table built from existing technicals formulas."""
from __future__ import annotations

import pandas as pd

from quant_layer.ohlcv import rows_to_dataframe
from technicals import (
    adx,
    atr,
    bollinger,
    cci,
    ema,
    macd,
    mfi,
    obv,
    roc,
    rsi,
    sma,
    stochastic,
    williams_r,
)


def _series_to_col(values: list, index: pd.Index) -> pd.Series:
    start = len(index) - len(values)
    if start < 0:
        return pd.Series([None] * len(index), index=index, dtype=float)
    padded = [None] * start + list(values)
    return pd.Series(padded, index=index, dtype=float)


def add_indicator_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Extend OHLCV frame with indicator columns (pure math, no LLM)."""
    if df.empty or len(df) < 30:
        return df

    close = df["close_adj"].tolist()
    high = df["high"].tolist()
    low = df["low"].tolist()
    volume = df["volume"].tolist()
    idx = df.index

    df["rsi_14"] = _series_to_col(rsi(close, 14), idx)
    df["sma_20"] = _series_to_col(sma(close, 20), idx)
    df["sma_50"] = _series_to_col(sma(close, 50), idx)
    df["sma_200"] = _series_to_col(sma(close, 200), idx)
    df["ema_9"] = _series_to_col(ema(close, 9), idx)
    df["ema_21"] = _series_to_col(ema(close, 21), idx)

    macd_s = macd(close, 12, 26, 9)
    df["macd"] = _series_to_col(macd_s["macd"], idx)
    df["macd_signal"] = _series_to_col(macd_s["signal"], idx)
    df["macd_hist"] = _series_to_col(macd_s["hist"], idx)

    stoch = stochastic(high, low, close, 14, 3, 3)
    df["stoch_k"] = _series_to_col(stoch["k"], idx)
    df["stoch_d"] = _series_to_col(stoch["d"], idx)

    bb = bollinger(close, 20, 2)
    df["bb_lower"] = _series_to_col(bb["lower"], idx)
    df["bb_middle"] = _series_to_col(bb["middle"], idx)
    df["bb_upper"] = _series_to_col(bb["upper"], idx)
    df["bb_percent_b"] = _series_to_col(bb["pct_b"], idx)
    df["bb_bandwidth"] = _series_to_col(bb["bandwidth"], idx)

    df["atr_14"] = _series_to_col(atr(high, low, close, 14), idx)
    adx_s = adx(high, low, close, 14)
    df["adx_14"] = _series_to_col(adx_s["adx"], idx)
    df["plus_di"] = _series_to_col(adx_s["plus_di"], idx)
    df["minus_di"] = _series_to_col(adx_s["minus_di"], idx)

    df["obv"] = _series_to_col(obv(close, volume), idx)
    df["roc_10"] = _series_to_col(roc(close, 10), idx)
    df["willr_14"] = _series_to_col(williams_r(high, low, close, 14), idx)
    df["cci_20"] = _series_to_col(cci(high, low, close, 20), idx)
    df["mfi_14"] = _series_to_col(mfi(high, low, close, volume, 14), idx)

    df["vol_avg20"] = df["volume"].rolling(20).mean()
    df["vol_vs_avg20"] = df["volume"] / df["vol_avg20"]
    df["high_52w"] = df["close_adj"].rolling(min(252, len(df))).max()
    df["low_52w"] = df["close_adj"].rolling(min(252, len(df))).min()
    df["high_52w_prior"] = df["high_52w"].shift(1)
    df["donchian_upper_20"] = df["high"].rolling(20).max()
    df["donchian_lower_20"] = df["low"].rolling(20).min()

    prev = df.shift(1)
    pp = (prev["high"] + prev["low"] + prev["close_adj"]) / 3
    df["pivot_pp"] = pp
    df["pivot_r1"] = 2 * pp - prev["low"]
    df["pivot_s1"] = 2 * pp - prev["high"]

    df["is_gap_up"] = (df["open"] - prev["close_adj"]) / prev["close_adj"] > 0.01
    df["is_gap_down"] = (df["open"] - prev["close_adj"]) / prev["close_adj"] < -0.01
    df["gap_pct"] = (df["open"] - prev["close_adj"]) / prev["close_adj"] * 100

    df["trend_50_over_200"] = df["sma_50"] > df["sma_200"]

    # Keltner channel (ATR-based)
    mid = df["ema_21"]
    atr_col = df["atr_14"]
    df["kc_upper"] = mid + 2 * atr_col
    df["kc_lower"] = mid - 2 * atr_col

    # Rolling VWAP approximation on daily bars
    typical = (df["high"] + df["low"] + df["close_adj"]) / 3
    cum_pv = (typical * df["volume"]).cumsum()
    cum_v = df["volume"].cumsum().replace(0, pd.NA)
    df["vwap"] = cum_pv / cum_v

    # Simple PSAR proxy: close vs trailing stop at prior low cluster
    df["psar_proxy"] = df["low"].rolling(5).min().shift(1)

    # Candle heuristics
    body = (df["close_adj"] - df["open"]).abs()
    rng = (df["high"] - df["low"]).replace(0, pd.NA)
    df["candle_bullish_engulfing"] = (
        (df["close_adj"] > df["open"])
        & (df["close_adj"] > df["open"].shift(1))
        & (df["open"] < df["close_adj"].shift(1))
    )
    df["candle_bearish_engulfing"] = (
        (df["close_adj"] < df["open"])
        & (df["close_adj"] < df["open"].shift(1))
        & (df["open"] > df["close_adj"].shift(1))
    )
    lower_shadow = df[["open", "close_adj"]].min(axis=1) - df["low"]
    df["candle_hammer"] = (lower_shadow > 2 * body) & (body / rng < 0.35)
    df["candle_doji"] = body / rng < 0.1

    return df


def build_indicator_frame(rows: list[dict]) -> pd.DataFrame:
    df = rows_to_dataframe(rows)
    if df.empty:
        return df
    return add_indicator_columns(df)
