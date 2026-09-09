"""Extended technical indicators: Ichimoku, Fib, channels, PSAR, CMF, AD, Aroon, TSI, Hull."""
from __future__ import annotations

from typing import Any, Optional

from analysis._helpers import clamp, extract_ohlcv, swing_high_low, true_range, typical_price
from technicals import _last, atr, ema, sma


def hull_ma(values: list[float], period: int = 21) -> list[Optional[float]]:
    half = max(1, period // 2)
    sqrt_p = max(1, int(period ** 0.5))
    wma_half = _wma(values, half)
    wma_full = _wma(values, period)
    diff = []
    for a, b in zip(wma_half, wma_full):
        diff.append((a + b) * 2 - b if a is not None and b is not None else None)
    clean = [d if d is not None else values[i] for i, d in enumerate(diff)]
    return _wma(clean, sqrt_p)


def _wma(values: list[float], period: int) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    denom = period * (period + 1) / 2
    for i in range(period - 1, len(values)):
        wsum = sum(values[i - j] * (period - j) for j in range(period))
        out[i] = wsum / denom
    return out


def ichimoku(highs: list[float], lows: list[float], closes: list[float]) -> dict[str, Any]:
    tenkan_p, kijun_p, senkou_b_p = 9, 26, 52

    def mid(h: list[float], l: list[float], i: int, p: int) -> Optional[float]:
        if i + 1 < p:
            return None
        seg_h = h[i - p + 1 : i + 1]
        seg_l = l[i - p + 1 : i + 1]
        return (max(seg_h) + min(seg_l)) / 2

    tenkan, kijun, senkou_a, senkou_b = [], [], [], []
    for i in range(len(closes)):
        t = mid(highs, lows, i, tenkan_p)
        k = mid(highs, lows, i, kijun_p)
        tenkan.append(t)
        kijun.append(k)
        senkou_a.append((t + k) / 2 if t is not None and k is not None else None)
        sb = mid(highs, lows, i, senkou_b_p)
        senkou_b.append(sb)

    last = closes[-1]
    t, k = _last(tenkan), _last(kijun)
    sa, sb = _last(senkou_a), _last(senkou_b)
    cloud_top = max(sa, sb) if sa is not None and sb is not None else None
    cloud_bot = min(sa, sb) if sa is not None and sb is not None else None
    above_cloud = cloud_top is not None and last > cloud_top
    below_cloud = cloud_bot is not None and last < cloud_bot
    tk_cross = "bullish" if t and k and t > k else ("bearish" if t and k and t < k else "neutral")

    return {
        "tenkan": round(t, 4) if t else None,
        "kijun": round(k, 4) if k else None,
        "senkou_a": round(sa, 4) if sa else None,
        "senkou_b": round(sb, 4) if sb else None,
        "cloud_top": round(cloud_top, 4) if cloud_top else None,
        "cloud_bottom": round(cloud_bot, 4) if cloud_bot else None,
        "price_vs_cloud": "above" if above_cloud else ("below" if below_cloud else "inside"),
        "tenkan_kijun_cross": tk_cross,
    }


def fibonacci_levels(closes: list[float], lookback: int = 120) -> dict[str, Any]:
    hi, lo, hi_i, lo_i = swing_high_low(closes, lookback)
    if hi <= lo:
        return {"swing_high": hi, "swing_low": lo, "levels": {}, "extensions": {}}
    diff = hi - lo
    retr = {
        "0.236": round(hi - 0.236 * diff, 4),
        "0.382": round(hi - 0.382 * diff, 4),
        "0.500": round(hi - 0.500 * diff, 4),
        "0.618": round(hi - 0.618 * diff, 4),
        "0.786": round(hi - 0.786 * diff, 4),
    }
    ext = {
        "1.272": round(hi + 0.272 * diff, 4),
        "1.618": round(hi + 0.618 * diff, 4),
        "2.000": round(hi + diff, 4),
    }
    last = closes[-1]
    nearest = min(retr.items(), key=lambda kv: abs(last - kv[1]))
    return {
        "swing_high": round(hi, 4),
        "swing_low": round(lo, 4),
        "trend_leg": "up" if hi_i > lo_i else "down",
        "levels": retr,
        "extensions": ext,
        "nearest_retracement": nearest[0],
        "nearest_level": nearest[1],
    }


def keltner_channels(highs: list[float], lows: list[float], closes: list[float], period: int = 20, mult: float = 2.0) -> dict[str, Any]:
    mid = ema(closes, period)
    atr_s = atr(highs, lows, closes, period)
    upper, lower = [], []
    for m, a in zip(mid, atr_s):
        if m is None or a is None:
            upper.append(None)
            lower.append(None)
        else:
            upper.append(m + mult * a)
            lower.append(m - mult * a)
    u, m, l = _last(upper), _last(mid), _last(lower)
    last = closes[-1]
    return {
        "upper": round(u, 4) if u else None,
        "middle": round(m, 4) if m else None,
        "lower": round(l, 4) if l else None,
        "price_position": "upper" if u and last > u else ("lower" if l and last < l else "mid"),
    }


def donchian_channels(highs: list[float], lows: list[float], period: int = 20) -> dict[str, Any]:
    if len(highs) < period:
        return {"upper": None, "lower": None, "mid": None, "breakout": None}
    u = max(highs[-period:])
    l = min(lows[-period:])
    last = highs[-1]  # use close from caller context — fixed below in compute
    return {"upper": round(u, 4), "lower": round(l, 4), "mid": round((u + l) / 2, 4)}


def parabolic_sar(highs: list[float], lows: list[float], closes: list[float], af_step: float = 0.02, af_max: float = 0.2) -> dict[str, Any]:
    if len(closes) < 3:
        return {"value": None, "direction": None}
    bull = True
    af = af_step
    ep = highs[0]
    sar = lows[0]
    for i in range(1, len(closes)):
        prev_sar = sar
        sar = prev_sar + af * (ep - prev_sar)
        if bull:
            sar = min(sar, lows[i - 1], lows[i] if i > 0 else lows[i - 1])
            if lows[i] < sar:
                bull = False
                sar = ep
                ep = lows[i]
                af = af_step
            elif highs[i] > ep:
                ep = highs[i]
                af = min(af + af_step, af_max)
        else:
            sar = max(sar, highs[i - 1], highs[i] if i > 0 else highs[i - 1])
            if highs[i] > sar:
                bull = True
                sar = ep
                ep = highs[i]
                af = af_step
            elif lows[i] < ep:
                ep = lows[i]
                af = min(af + af_step, af_max)
    return {
        "value": round(sar, 4),
        "direction": "bullish" if bull else "bearish",
        "price_above_sar": closes[-1] > sar,
    }


def chaikin_money_flow(highs: list[float], lows: list[float], closes: list[float], volumes: list[float], period: int = 20) -> dict[str, Any]:
    mfv_sum = 0.0
    vol_sum = 0.0
    start = max(0, len(closes) - period)
    for i in range(start, len(closes)):
        hl = highs[i] - lows[i]
        mfm = ((closes[i] - lows[i]) - (highs[i] - closes[i])) / hl if hl else 0.0
        mfv_sum += mfm * volumes[i]
        vol_sum += volumes[i]
    cmf = mfv_sum / vol_sum if vol_sum else 0.0
    bias = "accumulation" if cmf > 0.05 else ("distribution" if cmf < -0.05 else "neutral")
    return {"cmf_20": round(cmf, 4), "bias": bias}


def accumulation_distribution(highs: list[float], lows: list[float], closes: list[float], volumes: list[float]) -> dict[str, Any]:
    ad = 0.0
    prev = 0.0
    for i in range(len(closes)):
        hl = highs[i] - lows[i]
        mfm = ((closes[i] - lows[i]) - (highs[i] - closes[i])) / hl if hl else 0.0
        ad += mfm * volumes[i]
        prev = ad
    slope = ad - (ad * 0.98)  # placeholder; compute 20-bar slope
    if len(closes) >= 21:
        ad_series = []
        running = 0.0
        for i in range(len(closes)):
            hl = highs[i] - lows[i]
            mfm = ((closes[i] - lows[i]) - (highs[i] - closes[i])) / hl if hl else 0.0
            running += mfm * volumes[i]
            ad_series.append(running)
        slope = ad_series[-1] - ad_series[-21]
    return {"ad_line": round(ad, 2), "ad_slope_20": round(slope, 2), "bias": "rising" if slope > 0 else "falling"}


def aroon(highs: list[float], lows: list[float], period: int = 25) -> dict[str, Any]:
    if len(highs) < period + 1:
        return {"aroon_up": None, "aroon_down": None, "oscillator": None, "trend": None}
    seg_h = highs[-period:]
    seg_l = lows[-period:]
    days_since_high = period - 1 - seg_h.index(max(seg_h))
    days_since_low = period - 1 - seg_l.index(min(seg_l))
    up = (period - days_since_high) / period * 100
    down = (period - days_since_low) / period * 100
    osc = up - down
    trend = "uptrend" if up > 70 and down < 30 else ("downtrend" if down > 70 and up < 30 else "mixed")
    return {
        "aroon_up": round(up, 2),
        "aroon_down": round(down, 2),
        "oscillator": round(osc, 2),
        "trend": trend,
    }


def true_strength_index(closes: list[float], long_p: int = 25, short_p: int = 13, signal_p: int = 7) -> dict[str, Any]:
    if len(closes) < long_p + 2:
        return {"tsi": None, "signal": None, "bias": None}
    pc = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    abs_pc = [abs(x) for x in pc]
    ema1 = ema(pc, long_p)
    ema2 = ema([x if x is not None else 0 for x in ema1], short_p)
    ema3 = ema(abs_pc, long_p)
    ema4 = ema([x if x is not None else 0 for x in ema3], short_p)
    tsi_s: list[Optional[float]] = []
    for num, den in zip(ema2, ema4):
        if num is None or den in (None, 0):
            tsi_s.append(None)
        else:
            tsi_s.append(100 * num / den)
    sig = ema([x if x is not None else 0 for x in tsi_s], signal_p)
    t, s = _last(tsi_s), _last(sig)
    bias = "bullish" if t and s and t > s and t > 0 else ("bearish" if t and s and t < s else "neutral")
    return {"tsi": round(t, 2) if t else None, "signal": round(s, 2) if s else None, "bias": bias}


def compute_extended_indicators(rows: list[dict[str, Any]]) -> dict[str, Any]:
    opens, highs, lows, closes, volumes = extract_ohlcv(rows)
    if len(closes) < 30:
        return {"bars": len(closes), "status": "insufficient_data"}
    don = donchian_channels(highs, lows, 20)
    last = closes[-1]
    if don.get("upper") and last > don["upper"]:
        don["breakout"] = "upper"
    elif don.get("lower") and last < don["lower"]:
        don["breakout"] = "lower"
    else:
        don["breakout"] = None
    hull = hull_ma(closes, 21)
    h = _last(hull)
    return {
        "bars": len(closes),
        "status": "ok",
        "ichimoku": ichimoku(highs, lows, closes),
        "fibonacci": fibonacci_levels(closes),
        "keltner": keltner_channels(highs, lows, closes),
        "donchian": don,
        "parabolic_sar": parabolic_sar(highs, lows, closes),
        "cmf": chaikin_money_flow(highs, lows, closes, volumes),
        "ad_line": accumulation_distribution(highs, lows, closes, volumes),
        "aroon": aroon(highs, lows),
        "tsi": true_strength_index(closes),
        "hull_ma_21": round(h, 4) if h else None,
        "price_vs_hull": "above" if h and last > h else ("below" if h else None),
    }
