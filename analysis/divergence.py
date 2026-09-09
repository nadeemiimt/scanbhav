"""RSI and MACD divergence detection on daily bars."""
from __future__ import annotations

from typing import Any, Optional, Union

from analysis._helpers import extract_ohlcv
from technicals import macd, rsi


def _local_extrema(values: list[float], window: int = 3) -> tuple[list[int], list[int]]:
    peaks, troughs = [], []
    for i in range(window, len(values) - window):
        seg = values[i - window : i + window + 1]
        if values[i] == max(seg):
            peaks.append(i)
        if values[i] == min(seg):
            troughs.append(i)
    return peaks, troughs


def detect_divergence(
    closes: list[float],
    oscillator: list[Union[float, None]],
    lookback: int = 60,
    kind: str = "rsi",
) -> dict[str, Any]:
    clean_osc = [x if x is not None else 0.0 for x in oscillator]
    start = max(0, len(closes) - lookback)
    seg_c = closes[start:]
    seg_o = clean_osc[start:]
    peaks, troughs = _local_extrema(seg_c, 2)
    bullish = bearish = False
    notes: list[str] = []

    if len(troughs) >= 2:
        i1, i2 = troughs[-2], troughs[-1]
        if seg_c[i2] < seg_c[i1] and seg_o[i2] > seg_o[i1]:
            bullish = True
            notes.append(f"Bullish {kind.upper()} divergence: lower price low, higher oscillator low.")

    if len(peaks) >= 2:
        i1, i2 = peaks[-2], peaks[-1]
        if seg_c[i2] > seg_c[i1] and seg_o[i2] < seg_o[i1]:
            bearish = True
            notes.append(f"Bearish {kind.upper()} divergence: higher price high, lower oscillator high.")

    signal = "bullish" if bullish and not bearish else ("bearish" if bearish and not bullish else ("mixed" if bullish and bearish else "none"))
    return {"kind": kind, "signal": signal, "bullish": bullish, "bearish": bearish, "notes": notes}


def compute_divergence(rows: list[dict[str, Any]]) -> dict[str, Any]:
    _, highs, lows, closes, _ = extract_ohlcv(rows)
    if len(closes) < 40:
        return {"status": "insufficient_data", "rsi": {}, "macd": {}}
    rsi_s = rsi(closes, 14)
    macd_s = macd(closes, 12, 26, 9)
    rsi_div = detect_divergence(closes, rsi_s, kind="rsi")
    macd_div = detect_divergence(closes, macd_s["hist"], kind="macd_hist")
    composite = "none"
    if rsi_div["signal"] == macd_div["signal"] and rsi_div["signal"] != "none":
        composite = rsi_div["signal"]
    elif rsi_div["signal"] != "none" or macd_div["signal"] != "none":
        composite = "mixed"
    return {
        "status": "ok",
        "rsi": rsi_div,
        "macd": macd_div,
        "composite_signal": composite,
        "headline": (rsi_div["notes"] + macd_div["notes"])[:1][0] if (rsi_div["notes"] or macd_div["notes"]) else "No active RSI/MACD divergence.",
    }
