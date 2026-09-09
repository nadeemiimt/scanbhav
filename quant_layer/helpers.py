"""Shared cross/divergence helpers for deterministic trigger rules."""
from __future__ import annotations

import pandas as pd


def crossed_above(series_a: pd.Series, series_b: pd.Series | float) -> pd.Series:
    prev_a = series_a.shift(1)
    if isinstance(series_b, pd.Series):
        prev_b = series_b.shift(1)
        return (series_a > series_b) & (prev_a <= prev_b)
    return (series_a > series_b) & (prev_a <= series_b)


def crossed_below(series_a: pd.Series, series_b: pd.Series | float) -> pd.Series:
    prev_a = series_a.shift(1)
    if isinstance(series_b, pd.Series):
        prev_b = series_b.shift(1)
        return (series_a < series_b) & (prev_a >= prev_b)
    return (series_a < series_b) & (prev_a >= series_b)


def confirmed_cross(fast: pd.Series, slow: pd.Series, hold_days: int = 2) -> pd.Series:
    state = fast > slow
    holding = state.rolling(hold_days).sum() == hold_days
    prev_holding = holding.shift(1).fillna(False).astype(bool)
    return holding & ~prev_holding


def find_swing_lows(series: pd.Series, window: int = 5) -> pd.Series:
    rolled = series.rolling(window * 2 + 1, center=True).min()
    return (series == rolled).fillna(False)


def find_swing_highs(series: pd.Series, window: int = 5) -> pd.Series:
    rolled = series.rolling(window * 2 + 1, center=True).max()
    return (series == rolled).fillna(False)


def bullish_divergence(price: pd.Series, indicator: pd.Series, window: int = 5, max_gap_days: int = 40) -> pd.Series:
    swing_idxs = price.index[find_swing_lows(price, window)]
    result = pd.Series(False, index=price.index)
    for i in range(1, len(swing_idxs)):
        cur, prev = swing_idxs[i], swing_idxs[i - 1]
        if (cur - prev).days > max_gap_days:
            continue
        if price.loc[cur] < price.loc[prev] and indicator.loc[cur] > indicator.loc[prev]:
            result.loc[cur] = True
    return result


def bearish_divergence(price: pd.Series, indicator: pd.Series, window: int = 5, max_gap_days: int = 40) -> pd.Series:
    swing_idxs = price.index[find_swing_highs(price, window)]
    result = pd.Series(False, index=price.index)
    for i in range(1, len(swing_idxs)):
        cur, prev = swing_idxs[i], swing_idxs[i - 1]
        if (cur - prev).days > max_gap_days:
            continue
        if price.loc[cur] > price.loc[prev] and indicator.loc[cur] < indicator.loc[prev]:
            result.loc[cur] = True
    return result


def classify_oi_change(price_change: float, oi_change: float) -> str:
    if price_change > 0 and oi_change > 0:
        return "long_buildup"
    if price_change > 0 and oi_change < 0:
        return "short_covering"
    if price_change < 0 and oi_change > 0:
        return "short_buildup"
    if price_change < 0 and oi_change < 0:
        return "long_unwinding"
    return "neutral"
