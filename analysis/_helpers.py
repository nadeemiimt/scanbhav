"""Shared helpers for extended analysis modules."""
from __future__ import annotations

from typing import Any, Optional

from technicals import _last, _series, row_close, sma


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def extract_ohlcv(rows: list[dict[str, Any]]) -> tuple[list[float], list[float], list[float], list[float], list[float]]:
    """Return aligned open/high/low/close/volume lists (positive closes only)."""
    opens, highs, lows, closes, volumes = [], [], [], [], []
    for row in rows:
        c = row_close(row)
        if c <= 0:
            continue
        opens.append(float(_series([row], "open")[0] or c))
        highs.append(float(_series([row], "high")[0] or c))
        lows.append(float(_series([row], "low")[0] or c))
        closes.append(c)
        volumes.append(float(_series([row], "volume")[0] or 0))
    return opens, highs, lows, closes, volumes


def swing_high_low(closes: list[float], lookback: int = 60) -> tuple[float, float, int, int]:
    window = closes[-lookback:] if len(closes) >= lookback else closes
    if not window:
        return 0.0, 0.0, 0, 0
    hi = max(window)
    lo = min(window)
    hi_i = len(closes) - len(window) + window.index(hi)
    lo_i = len(closes) - len(window) + window.index(lo)
    return hi, lo, hi_i, lo_i


def true_range(highs: list[float], lows: list[float], closes: list[float]) -> list[float]:
    out: list[float] = []
    for i in range(len(closes)):
        if i == 0:
            out.append(highs[i] - lows[i])
        else:
            out.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    return out


def typical_price(highs: list[float], lows: list[float], closes: list[float]) -> list[float]:
    return [(h + l + c) / 3.0 for h, l, c in zip(highs, lows, closes)]


def num(value: Any) -> Optional[float]:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
