"""Technical-indicator engine from daily OHLCV rows (pure Python)."""
from __future__ import annotations

import math
from typing import Any, Optional


def parse_float(value: Any, default: float = 0.0) -> float:
    """Parse a numeric field; reject NaN/inf and common bad string sentinels."""
    if value is None or value in ("", "None", "-", "nan", "NaN", "null"):
        return default
    try:
        x = float(value)
    except (TypeError, ValueError):
        return default
    return x if math.isfinite(x) else default


def row_close(row: dict[str, Any]) -> float:
    """Best available positive close/adj close for one daily bar."""
    for key in ("5. adjusted close", "4. close"):
        value = parse_float(row.get(key))
        if value > 0:
            return value
    return 0.0


def _closes(rows: list[dict[str, Any]]) -> list[float]:
    out = []
    for row in rows:
        value = row_close(row)
        if value > 0:
            out.append(value)
    return out


def _series(rows: list[dict[str, Any]], key: str) -> list[float]:
    mapping = {
        "open": "1. open",
        "high": "2. high",
        "low": "3. low",
        "close": "4. close",
        "adj": "5. adjusted close",
        "volume": "6. volume",
    }
    field = mapping.get(key, key)
    values = []
    for row in rows:
        raw = row.get(field)
        if raw is None and key == "adj":
            raw = row.get("4. close")
        try:
            values.append(parse_float(raw))
        except (TypeError, ValueError):
            values.append(0.0)
    return values


def sma(values: list[float], period: int) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    window = sum(values[:period])
    out[period - 1] = window / period
    for i in range(period, len(values)):
        window += values[i] - values[i - period]
        out[i] = window / period
    return out


def ema(values: list[float], period: int) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    k = 2 / (period + 1)
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def _last(series: list[Optional[float]]) -> Optional[float]:
    for value in reversed(series):
        if value is not None:
            return float(value)
    return None


def rsi(values: list[float], period: int = 14) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(values)
    if len(values) <= period:
        return out
    gains = losses = 0.0
    for i in range(1, period + 1):
        change = values[i] - values[i - 1]
        gains += max(change, 0)
        losses += max(-change, 0)
    avg_gain = gains / period
    avg_loss = losses / period
    out[period] = 100 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))
    for i in range(period + 1, len(values)):
        change = values[i] - values[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(change, 0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-change, 0)) / period
        out[i] = 100 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))
    return out


def macd(values: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, list[Optional[float]]]:
    fast_ema = ema(values, fast)
    slow_ema = ema(values, slow)
    line: list[Optional[float]] = [None] * len(values)
    for i, (f, s) in enumerate(zip(fast_ema, slow_ema)):
        if f is not None and s is not None:
            line[i] = f - s
    # Signal EMA over available MACD line values
    compact = [v for v in line if v is not None]
    signal_compact = ema(compact, signal) if len(compact) >= signal else [None] * len(compact)
    signal_full: list[Optional[float]] = [None] * len(values)
    hist: list[Optional[float]] = [None] * len(values)
    idx = 0
    for i, value in enumerate(line):
        if value is None:
            continue
        sig = signal_compact[idx] if idx < len(signal_compact) else None
        signal_full[i] = sig
        if sig is not None:
            hist[i] = value - sig
        idx += 1
    return {"macd": line, "signal": signal_full, "hist": hist}


def stochastic(highs: list[float], lows: list[float], closes: list[float], period: int = 14, smooth_k: int = 3, smooth_d: int = 3) -> dict[str, list[Optional[float]]]:
    raw_k: list[Optional[float]] = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        hh = max(highs[i - period + 1 : i + 1])
        ll = min(lows[i - period + 1 : i + 1])
        raw_k[i] = 50.0 if hh == ll else ((closes[i] - ll) / (hh - ll)) * 100
    # Smooth %K then %D using SMA of available values
    k_vals = [v if v is not None else float("nan") for v in raw_k]
    k_sma = sma([0 if v != v else v for v in k_vals], smooth_k)
    # Rebuild carefully
    percent_k: list[Optional[float]] = [None] * len(closes)
    buffer: list[float] = []
    for i, value in enumerate(raw_k):
        if value is None:
            continue
        buffer.append(value)
        if len(buffer) >= smooth_k:
            percent_k[i] = sum(buffer[-smooth_k:]) / smooth_k
    percent_d: list[Optional[float]] = [None] * len(closes)
    buffer_d: list[float] = []
    for i, value in enumerate(percent_k):
        if value is None:
            continue
        buffer_d.append(value)
        if len(buffer_d) >= smooth_d:
            percent_d[i] = sum(buffer_d[-smooth_d:]) / smooth_d
    return {"k": percent_k, "d": percent_d}


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(closes)
    if len(closes) < 2:
        return out
    trs = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    if len(trs) < period:
        return out
    avg = sum(trs[1 : period + 1]) / period
    out[period] = avg
    for i in range(period + 1, len(trs)):
        avg = (avg * (period - 1) + trs[i]) / period
        out[i] = avg
    return out


def bollinger(values: list[float], period: int = 20, num_std: float = 2.0) -> dict[str, list[Optional[float]]]:
    mid = sma(values, period)
    upper: list[Optional[float]] = [None] * len(values)
    lower: list[Optional[float]] = [None] * len(values)
    pct_b: list[Optional[float]] = [None] * len(values)
    width: list[Optional[float]] = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        mean = mid[i]
        if mean is None:
            continue
        var = sum((x - mean) ** 2 for x in window) / period
        std = var ** 0.5
        upper[i] = mean + num_std * std
        lower[i] = mean - num_std * std
        band = upper[i] - lower[i]
        width[i] = (band / mean) * 100 if mean else None
        pct_b[i] = (values[i] - lower[i]) / band if band else 0.5
    return {"middle": mid, "upper": upper, "lower": lower, "pct_b": pct_b, "bandwidth": width}


def adx(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> dict[str, list[Optional[float]]]:
    n = len(closes)
    plus_dm = [0.0] * n
    minus_dm = [0.0] * n
    tr = [0.0] * n
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm[i] = up if up > down and up > 0 else 0.0
        minus_dm[i] = down if down > up and down > 0 else 0.0
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
    def wilder(series: list[float]) -> list[Optional[float]]:
        out: list[Optional[float]] = [None] * n
        if n <= period:
            return out
        avg = sum(series[1 : period + 1]) / period
        out[period] = avg
        for i in range(period + 1, n):
            avg = (avg * (period - 1) + series[i]) / period
            out[i] = avg
        return out
    atr_s = wilder(tr)
    plus_s = wilder(plus_dm)
    minus_s = wilder(minus_dm)
    plus_di: list[Optional[float]] = [None] * n
    minus_di: list[Optional[float]] = [None] * n
    dx: list[Optional[float]] = [None] * n
    for i in range(n):
        if atr_s[i] in (None, 0) or plus_s[i] is None or minus_s[i] is None:
            continue
        plus_di[i] = 100 * (plus_s[i] / atr_s[i])
        minus_di[i] = 100 * (minus_s[i] / atr_s[i])
        denom = plus_di[i] + minus_di[i]
        dx[i] = 0.0 if denom == 0 else abs(plus_di[i] - minus_di[i]) / denom * 100
    # ADX = Wilder smooth of DX
    adx_out: list[Optional[float]] = [None] * n
    seed_vals = [v for v in dx if v is not None][:period]
    if len(seed_vals) >= period:
        # find index of period-th dx value
        count = 0
        avg = 0.0
        start_i = None
        for i, value in enumerate(dx):
            if value is None:
                continue
            count += 1
            if count <= period:
                avg += value
            if count == period:
                avg /= period
                adx_out[i] = avg
                start_i = i
                break
        if start_i is not None:
            prev = avg
            for i in range(start_i + 1, n):
                if dx[i] is None:
                    continue
                prev = (prev * (period - 1) + dx[i]) / period
                adx_out[i] = prev
    return {"adx": adx_out, "plus_di": plus_di, "minus_di": minus_di}


def supertrend(highs: list[float], lows: list[float], closes: list[float], period: int = 10, multiplier: float = 3.0) -> dict[str, Any]:
    atr_s = atr(highs, lows, closes, period)
    n = len(closes)
    st: list[Optional[float]] = [None] * n
    direction: list[Optional[int]] = [None] * n  # 1 bull, -1 bear
    final_upper: list[Optional[float]] = [None] * n
    final_lower: list[Optional[float]] = [None] * n
    for i in range(n):
        if atr_s[i] is None:
            continue
        mid = (highs[i] + lows[i]) / 2
        basic_upper = mid + multiplier * atr_s[i]
        basic_lower = mid - multiplier * atr_s[i]
        if i == 0 or final_upper[i - 1] is None:
            final_upper[i] = basic_upper
            final_lower[i] = basic_lower
            direction[i] = 1
            st[i] = final_lower[i]
            continue
        final_upper[i] = basic_upper if basic_upper < final_upper[i - 1] or closes[i - 1] > final_upper[i - 1] else final_upper[i - 1]
        final_lower[i] = basic_lower if basic_lower > final_lower[i - 1] or closes[i - 1] < final_lower[i - 1] else final_lower[i - 1]
        prev_dir = direction[i - 1] or 1
        if prev_dir == 1:
            if closes[i] < final_lower[i]:
                direction[i] = -1
                st[i] = final_upper[i]
            else:
                direction[i] = 1
                st[i] = final_lower[i]
        else:
            if closes[i] > final_upper[i]:
                direction[i] = 1
                st[i] = final_lower[i]
            else:
                direction[i] = -1
                st[i] = final_upper[i]
    return {"supertrend": st, "direction": direction}


def obv(closes: list[float], volumes: list[float]) -> list[float]:
    out = [0.0] * len(closes)
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            out[i] = out[i - 1] + volumes[i]
        elif closes[i] < closes[i - 1]:
            out[i] = out[i - 1] - volumes[i]
        else:
            out[i] = out[i - 1]
    return out


def cci(highs: list[float], lows: list[float], closes: list[float], period: int = 20) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(closes)
    tp = [(highs[i] + lows[i] + closes[i]) / 3 for i in range(len(closes))]
    for i in range(period - 1, len(closes)):
        window = tp[i - period + 1 : i + 1]
        mean = sum(window) / period
        mad = sum(abs(x - mean) for x in window) / period
        out[i] = 0.0 if mad == 0 else (tp[i] - mean) / (0.015 * mad)
    return out


def williams_r(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        hh = max(highs[i - period + 1 : i + 1])
        ll = min(lows[i - period + 1 : i + 1])
        out[i] = -50.0 if hh == ll else ((hh - closes[i]) / (hh - ll)) * -100
    return out


def roc(values: list[float], period: int = 12) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(values)
    for i in range(period, len(values)):
        if values[i - period] == 0:
            continue
        out[i] = ((values[i] / values[i - period]) - 1) * 100
    return out


def mfi(highs: list[float], lows: list[float], closes: list[float], volumes: list[float], period: int = 14) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(closes)
    tp = [(highs[i] + lows[i] + closes[i]) / 3 for i in range(len(closes))]
    raw_flow = [tp[i] * volumes[i] for i in range(len(closes))]
    for i in range(period, len(closes)):
        pos = neg = 0.0
        for j in range(i - period + 1, i + 1):
            if tp[j] > tp[j - 1]:
                pos += raw_flow[j]
            elif tp[j] < tp[j - 1]:
                neg += raw_flow[j]
        if neg == 0:
            out[i] = 100.0
        else:
            out[i] = 100 - (100 / (1 + pos / neg))
    return out


def pct_change(values: list[float], bars: int) -> Optional[float]:
    if bars <= 0 or len(values) <= bars or values[-1 - bars] == 0:
        return None
    return round((values[-1] / values[-1 - bars] - 1) * 100, 3)


def compute_technicals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute a broad TA snapshot from daily candles."""
    if len(rows) < 30:
        raise ValueError("Need at least 30 daily candles for technical analysis.")

    opens, highs, lows, closes, volumes, px = [], [], [], [], [], []
    for row in rows:
        adj = row_close(row)
        if adj <= 0:
            continue
        opens.append(parse_float(row.get("1. open"), adj))
        highs.append(parse_float(row.get("2. high"), adj))
        lows.append(parse_float(row.get("3. low"), adj))
        closes.append(parse_float(row.get("4. close"), adj))
        volumes.append(parse_float(row.get("6. volume")))
        px.append(adj)

    if len(px) < 30:
        raise ValueError("Need at least 30 valid closes.")

    sma_20 = sma(px, 20)
    sma_50 = sma(px, 50)
    sma_100 = sma(px, 100)
    sma_200 = sma(px, 200)
    ema_9 = ema(px, 9)
    ema_12 = ema(px, 12)
    ema_21 = ema(px, 21)
    ema_26 = ema(px, 26)
    ema_50 = ema(px, 50)
    ema_200 = ema(px, 200)
    rsi_14 = rsi(px, 14)
    rsi_7 = rsi(px, 7)
    macd_s = macd(px, 12, 26, 9)
    stoch = stochastic(highs, lows, px, 14, 3, 3)
    bb = bollinger(px, 20, 2)
    atr_14 = atr(highs, lows, px, 14)
    adx_s = adx(highs, lows, px, 14)
    st = supertrend(highs, lows, px, 10, 3)
    obv_s = obv(px, volumes)
    vol_sma_20 = sma(volumes, 20)
    cci_20 = cci(highs, lows, px, 20)
    will_r = williams_r(highs, lows, px, 14)
    roc_12 = roc(px, 12)
    mfi_14 = mfi(highs, lows, px, volumes, 14)

    last = px[-1]
    if len(px) > 1:
        prev_high, prev_low, prev_close = highs[-2], lows[-2], px[-2]
    else:
        prev_high, prev_low, prev_close = highs[-1], lows[-1], px[-1]
    pivot = (prev_high + prev_low + prev_close) / 3
    r1 = 2 * pivot - prev_low
    s1 = 2 * pivot - prev_high
    r2 = pivot + (prev_high - prev_low)
    s2 = pivot - (prev_high - prev_low)

    def dist(ma_value: Optional[float]) -> Optional[float]:
        return None if ma_value in (None, 0) else round((last / ma_value - 1) * 100, 3)

    high_52 = max(px[-252:]) if len(px) >= 50 else max(px)
    low_52 = min(px[-252:]) if len(px) >= 50 else min(px)

    # Chart payloads (last 120 sessions) for candles + oscillators.
    chart_len = min(120, len(px))
    start = len(px) - chart_len
    valid_dates = []
    for row in rows:
        if row_close(row) > 0:
            valid_dates.append(row["date"])
    dates = valid_dates[-chart_len:]
    candles = []
    for i in range(start, len(px)):
        atr_val = atr_14[i]
        close_i = px[i]
        candles.append({
            "date": dates[i - start],
            "open": round(opens[i], 4),
            "high": round(highs[i], 4),
            "low": round(lows[i], 4),
            "close": round(close_i, 4),
            "volume": volumes[i],
            "sma_20": sma_20[i],
            "sma_50": sma_50[i],
            "ema_21": ema_21[i],
            "bb_upper": bb["upper"][i],
            "bb_lower": bb["lower"][i],
            "rsi_14": rsi_14[i],
            "atr_14": round(atr_val, 4) if atr_val is not None else None,
            "atr_pct": round((atr_val / close_i) * 100, 3) if atr_val and close_i else None,
            "atr_upper": round(close_i + atr_val, 4) if atr_val is not None else None,
            "atr_lower": round(close_i - atr_val, 4) if atr_val is not None else None,
            "macd": macd_s["macd"][i],
            "macd_signal": macd_s["signal"][i],
            "macd_hist": macd_s["hist"][i],
            "vwap": None,
            "pivot_line": None,
        })

    # Cumulative VWAP across the chart window (typical price × volume).
    cum_pv = 0.0
    cum_v = 0.0
    for c in candles:
        typ = (c["high"] + c["low"] + c["close"]) / 3.0
        vol = float(c.get("volume") or 0)
        if vol > 0:
            cum_pv += typ * vol
            cum_v += vol
        c["vwap"] = round(cum_pv / cum_v, 4) if cum_v > 0 else None
        c["pivot_line"] = round(pivot, 4)
        c["r1_line"] = round(r1, 4)
        c["s1_line"] = round(s1, 4)

    return {
        "price": round(last, 4),
        "as_of": rows[-1]["date"],
        "bars": len(px),
        "moving_averages": {
            "sma_20": _last(sma_20), "sma_50": _last(sma_50), "sma_100": _last(sma_100), "sma_200": _last(sma_200),
            "ema_9": _last(ema_9), "ema_12": _last(ema_12), "ema_21": _last(ema_21), "ema_26": _last(ema_26),
            "ema_50": _last(ema_50), "ema_200": _last(ema_200),
            "price_vs_sma_20_pct": dist(_last(sma_20)),
            "price_vs_sma_50_pct": dist(_last(sma_50)),
            "price_vs_sma_200_pct": dist(_last(sma_200)),
            "price_vs_ema_21_pct": dist(_last(ema_21)),
            "golden_cross": bool(_last(sma_50) and _last(sma_200) and _last(sma_50) > _last(sma_200)),
            "death_cross": bool(_last(sma_50) and _last(sma_200) and _last(sma_50) < _last(sma_200)),
            "ema_stack_bullish": bool(_last(ema_9) and _last(ema_21) and _last(ema_50) and _last(ema_9) > _last(ema_21) > _last(ema_50)),
        },
        "momentum": {
            "rsi_14": round(_last(rsi_14), 2) if _last(rsi_14) is not None else None,
            "rsi_7": round(_last(rsi_7), 2) if _last(rsi_7) is not None else None,
            "macd": round(_last(macd_s["macd"]), 4) if _last(macd_s["macd"]) is not None else None,
            "macd_signal": round(_last(macd_s["signal"]), 4) if _last(macd_s["signal"]) is not None else None,
            "macd_hist": round(_last(macd_s["hist"]), 4) if _last(macd_s["hist"]) is not None else None,
            "stoch_k": round(_last(stoch["k"]), 2) if _last(stoch["k"]) is not None else None,
            "stoch_d": round(_last(stoch["d"]), 2) if _last(stoch["d"]) is not None else None,
            "cci_20": round(_last(cci_20), 2) if _last(cci_20) is not None else None,
            "williams_r": round(_last(will_r), 2) if _last(will_r) is not None else None,
            "roc_12": round(_last(roc_12), 2) if _last(roc_12) is not None else None,
            "mfi_14": round(_last(mfi_14), 2) if _last(mfi_14) is not None else None,
        },
        "volatility": {
            "atr_14": round(_last(atr_14), 4) if _last(atr_14) is not None else None,
            "atr_pct": round((_last(atr_14) / last) * 100, 3) if _last(atr_14) else None,
            "bb_upper": _last(bb["upper"]),
            "bb_middle": _last(bb["middle"]),
            "bb_lower": _last(bb["lower"]),
            "bb_pct_b": round(_last(bb["pct_b"]), 3) if _last(bb["pct_b"]) is not None else None,
            "bb_bandwidth_pct": round(_last(bb["bandwidth"]), 3) if _last(bb["bandwidth"]) is not None else None,
        },
        "trend": {
            "adx_14": round(_last(adx_s["adx"]), 2) if _last(adx_s["adx"]) is not None else None,
            "plus_di": round(_last(adx_s["plus_di"]), 2) if _last(adx_s["plus_di"]) is not None else None,
            "minus_di": round(_last(adx_s["minus_di"]), 2) if _last(adx_s["minus_di"]) is not None else None,
            "supertrend": _last(st["supertrend"]),
            "supertrend_dir": st["direction"][-1],
        },
        "volume": {
            "volume": volumes[-1],
            "volume_sma_20": _last(vol_sma_20),
            "rvol": round(volumes[-1] / _last(vol_sma_20), 2) if _last(vol_sma_20) else None,
            "obv": obv_s[-1],
            "obv_slope_20": round(obv_s[-1] - obv_s[-21], 2) if len(obv_s) > 21 else None,
        },
        "levels": {
            "high_52w": round(high_52, 4),
            "low_52w": round(low_52, 4),
            "dist_from_52w_high_pct": round((last / high_52 - 1) * 100, 3) if high_52 else None,
            "dist_from_52w_low_pct": round((last / low_52 - 1) * 100, 3) if low_52 else None,
            "pivot": round(pivot, 4),
            "r1": round(r1, 4),
            "s1": round(s1, 4),
            "r2": round(r2, 4),
            "s2": round(s2, 4),
        },
        "returns_pct": {
            "1d": pct_change(px, 1),
            "1w": pct_change(px, 5),
            "7d": pct_change(px, 7),
            "15d": pct_change(px, 15),
            "1m": pct_change(px, 21),
            "3m": pct_change(px, 63),
            "6m": pct_change(px, 126),
            "9m": pct_change(px, 189),
            "1y": pct_change(px, 252),
            "2y": pct_change(px, 504),
            "3y": pct_change(px, 756),
            "5y": pct_change(px, 1260),
        },
        "charts": {"candles": candles},
    }
