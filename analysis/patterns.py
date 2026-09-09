"""Candlestick and chart geometry pattern detection (heuristic, daily bars)."""
from __future__ import annotations

from typing import Any

from analysis._helpers import extract_ohlcv


def _body(o: float, c: float) -> float:
    return abs(c - o)


def _range(h: float, l: float) -> float:
    return max(h - l, 1e-9)


def detect_candlestick_patterns(rows: list[dict[str, Any]]) -> dict[str, Any]:
    opens, highs, lows, closes, _ = extract_ohlcv(rows)
    if len(closes) < 5:
        return {"patterns": [], "bias": "neutral"}
    patterns: list[dict[str, Any]] = []
    o, h, l, c = opens[-1], highs[-1], lows[-1], closes[-1]
    po, ph, pl, pc = opens[-2], highs[-2], lows[-2], closes[-2]
    body = _body(o, c)
    rng = _range(h, l)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l

    if body / rng < 0.1:
        patterns.append({"name": "Doji", "type": "candlestick", "bias": "indecision", "strength": "medium"})
    if lower_wick > 2 * body and upper_wick < body and c > o:
        patterns.append({"name": "Hammer", "type": "candlestick", "bias": "bullish", "strength": "medium"})
    if upper_wick > 2 * body and lower_wick < body and c < o:
        patterns.append({"name": "Shooting Star", "type": "candlestick", "bias": "bearish", "strength": "medium"})
    if c > o and pc < po and c >= po and o <= pc:
        patterns.append({"name": "Bullish Engulfing", "type": "candlestick", "bias": "bullish", "strength": "strong"})
    if c < o and pc > po and c <= po and o >= pc:
        patterns.append({"name": "Bearish Engulfing", "type": "candlestick", "bias": "bearish", "strength": "strong"})

    if len(closes) >= 3:
        o2, c2 = opens[-3], closes[-3]
        mid = opens[-2]
        if c2 < o2 and _body(mid, closes[-2]) / _range(highs[-2], lows[-2]) < 0.35 and c > o and c > (o2 + c2) / 2:
            patterns.append({"name": "Morning Star", "type": "candlestick", "bias": "bullish", "strength": "strong"})
        if c2 > o2 and _body(mid, closes[-2]) / _range(highs[-2], lows[-2]) < 0.35 and c < o and c < (o2 + c2) / 2:
            patterns.append({"name": "Evening Star", "type": "candlestick", "bias": "bearish", "strength": "strong"})

    bullish = sum(1 for p in patterns if p["bias"] == "bullish")
    bearish = sum(1 for p in patterns if p["bias"] == "bearish")
    bias = "bullish" if bullish > bearish else ("bearish" if bearish > bullish else "neutral")
    return {"patterns": patterns, "bias": bias, "count": len(patterns)}


def detect_chart_patterns(closes: list[float], highs: list[float], lows: list[float]) -> dict[str, Any]:
    if len(closes) < 40:
        return {"patterns": [], "bias": "neutral"}
    patterns: list[dict[str, Any]] = []
    w = closes[-40:]
    wh, wl = highs[-40:], lows[-40:]
    mid = len(w) // 2
    left_hi, right_hi = max(w[:mid]), max(w[mid:])
    left_lo, right_lo = min(wl[:mid]), min(wl[mid:])
    peak1, peak2 = max(w[: mid // 2]), max(w[mid // 2 : mid])
    trough1, trough2 = min(wl[: mid // 2]), min(wl[mid // 2 : mid])

    if abs(peak1 - peak2) / max(peak1, 1) < 0.03 and w[-1] < min(peak1, peak2) * 0.97:
        patterns.append({"name": "Double Top", "type": "chart", "bias": "bearish", "strength": "medium"})
    if abs(trough1 - trough2) / max(trough1, 1) < 0.03 and w[-1] > max(trough1, trough2) * 1.03:
        patterns.append({"name": "Double Bottom", "type": "chart", "bias": "bullish", "strength": "medium"})

    # Head & shoulders: three peaks, middle highest
    third = len(w) // 3
    p1 = max(w[:third])
    p2 = max(w[third : 2 * third])
    p3 = max(w[2 * third :])
    if p2 > p1 * 1.02 and p2 > p3 * 1.02 and w[-1] < (p1 + p3) / 2:
        patterns.append({"name": "Head and Shoulders", "type": "chart", "bias": "bearish", "strength": "strong"})

    # Triangle: narrowing range
    early_range = max(wh[:15]) - min(wl[:15])
    late_range = max(wh[-15:]) - min(wl[-15:])
    if early_range > 0 and late_range / early_range < 0.55:
        slope_up = wl[-1] > wl[-15]
        slope_dn = wh[-1] < wh[-15]
        if slope_up and slope_dn:
            patterns.append({"name": "Symmetrical Triangle", "type": "chart", "bias": "neutral", "strength": "medium"})
        elif slope_up:
            patterns.append({"name": "Ascending Triangle", "type": "chart", "bias": "bullish", "strength": "medium"})
        elif slope_dn:
            patterns.append({"name": "Descending Triangle", "type": "chart", "bias": "bearish", "strength": "medium"})

    # Flag: sharp move then tight consolidation
    if len(w) >= 30:
        impulse = (w[10] - w[0]) / max(w[0], 1)
        consol = (max(w[-10:]) - min(w[-10:])) / max(w[-10], 1)
        if impulse > 0.08 and consol < 0.04:
            patterns.append({"name": "Bull Flag", "type": "chart", "bias": "bullish", "strength": "medium"})
        elif impulse < -0.08 and consol < 0.04:
            patterns.append({"name": "Bear Flag", "type": "chart", "bias": "bearish", "strength": "medium"})

    # Cup and handle (very rough)
    if len(w) >= 35:
        cup_low = min(w[5:25])
        cup_left, cup_right = w[5], w[24]
        if cup_low < min(cup_left, cup_right) * 0.92 and w[-1] > cup_right * 0.98:
            patterns.append({"name": "Cup and Handle", "type": "chart", "bias": "bullish", "strength": "medium"})

    bullish = sum(1 for p in patterns if p.get("bias") == "bullish")
    bearish = sum(1 for p in patterns if p.get("bias") == "bearish")
    bias = "bullish" if bullish > bearish else ("bearish" if bearish > bullish else "neutral")
    return {"patterns": patterns, "bias": bias, "count": len(patterns)}


def compute_patterns(rows: list[dict[str, Any]]) -> dict[str, Any]:
    opens, highs, lows, closes, _ = extract_ohlcv(rows)
    candle = detect_candlestick_patterns(rows)
    chart = detect_chart_patterns(closes, highs, lows)
    all_p = (candle.get("patterns") or []) + (chart.get("patterns") or [])
    bullish = sum(1 for p in all_p if p.get("bias") == "bullish")
    bearish = sum(1 for p in all_p if p.get("bias") == "bearish")
    composite = "bullish" if bullish > bearish else ("bearish" if bearish > bullish else "neutral")
    names = [p["name"] for p in all_p[-5:]]
    return {
        "candlestick": candle,
        "chart_geometry": chart,
        "composite_bias": composite,
        "active_patterns": names,
        "headline": ", ".join(names) if names else "No classical patterns flagged on latest bars.",
    }
