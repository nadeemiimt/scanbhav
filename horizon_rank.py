"""Horizon-based educational ratings from a technical snapshot."""
from __future__ import annotations

from typing import Any, Optional

from universe import HORIZONS


def _clamp(score: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, score))


def _grade(score: float) -> str:
    if score >= 80:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    if score >= 35:
        return "D"
    return "F"


def _stance(score: float) -> str:
    if score >= 75:
        return "strong_favorable"
    if score >= 60:
        return "favorable"
    if score >= 45:
        return "neutral"
    if score >= 30:
        return "cautious"
    return "unfavorable"


def _num(value: Any) -> Optional[float]:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def score_horizon(tech: dict[str, Any], horizon_id: str) -> dict[str, Any]:
    """Score one horizon using horizon-appropriate TA weights."""
    ma = tech.get("moving_averages") or {}
    mom = tech.get("momentum") or {}
    vol = tech.get("volatility") or {}
    trend = tech.get("trend") or {}
    volume = tech.get("volume") or {}
    levels = tech.get("levels") or {}
    rets = tech.get("returns_pct") or {}

    score = 50.0
    reasons: list[str] = []
    short = horizon_id in {"1d", "1w", "1m"}
    medium = horizon_id in {"3m", "6m", "9m"}
    long = horizon_id in {"1y", "2y", "3y", "5y"}

    # --- Momentum ---
    rsi = _num(mom.get("rsi_14"))
    if rsi is not None:
        if short:
            if 45 <= rsi <= 65:
                score += 8
                reasons.append(f"RSI(14)={rsi} in constructive short-term zone.")
            elif rsi >= 75:
                score -= 10
                reasons.append(f"RSI(14)={rsi} overbought for short horizon.")
            elif rsi <= 30:
                score += 4
                reasons.append(f"RSI(14)={rsi} oversold — mean-reversion bounce possible.")
            elif rsi < 45:
                score -= 4
        else:
            if rsi >= 55:
                score += 6
                reasons.append(f"RSI(14)={rsi} supports ongoing trend strength.")
            elif rsi <= 40:
                score -= 6
                reasons.append(f"RSI(14)={rsi} shows weak momentum.")

    macd_hist = _num(mom.get("macd_hist"))
    if macd_hist is not None:
        if macd_hist > 0:
            score += 7 if short or medium else 5
            reasons.append("MACD histogram positive.")
        else:
            score -= 7 if short or medium else 5
            reasons.append("MACD histogram negative.")

    stoch_k = _num(mom.get("stoch_k"))
    if stoch_k is not None and short:
        if stoch_k >= 80:
            score -= 6
            reasons.append(f"Stochastic %K={stoch_k} overbought.")
        elif stoch_k <= 20:
            score += 4
            reasons.append(f"Stochastic %K={stoch_k} oversold.")
        elif 40 <= stoch_k <= 70:
            score += 3

    # --- Trend / MAs ---
    if ma.get("ema_stack_bullish"):
        score += 8 if short or medium else 5
        reasons.append("EMA 9>21>50 stack bullish.")
    if ma.get("golden_cross"):
        score += 10 if long or medium else 4
        reasons.append("Golden cross (SMA50 > SMA200).")
    if ma.get("death_cross"):
        score -= 10 if long or medium else 4
        reasons.append("Death cross (SMA50 < SMA200).")

    vs_20 = _num(ma.get("price_vs_sma_20_pct"))
    vs_50 = _num(ma.get("price_vs_sma_50_pct"))
    vs_200 = _num(ma.get("price_vs_sma_200_pct"))
    if short and vs_20 is not None:
        score += 6 if vs_20 > 0 else -6
    if (medium or short) and vs_50 is not None:
        score += 6 if vs_50 > 0 else -6
    if (medium or long) and vs_200 is not None:
        if vs_200 > 0:
            score += 8
            reasons.append(f"Price above SMA200 ({vs_200}%).")
        else:
            score -= 8
            reasons.append(f"Price below SMA200 ({vs_200}%).")

    adx = _num(trend.get("adx_14"))
    plus_di = _num(trend.get("plus_di"))
    minus_di = _num(trend.get("minus_di"))
    if adx is not None:
        if adx >= 25 and plus_di is not None and minus_di is not None:
            if plus_di > minus_di:
                score += 7
                reasons.append(f"ADX={adx} with +DI dominant (trend up).")
            else:
                score -= 7
                reasons.append(f"ADX={adx} with -DI dominant (trend down).")
        elif adx < 15:
            score -= 2
            reasons.append(f"ADX={adx} — weak trend / choppy.")

    if trend.get("supertrend_dir") == 1:
        score += 6 if short or medium else 3
        reasons.append("Supertrend bullish.")
    elif trend.get("supertrend_dir") == -1:
        score -= 6 if short or medium else 3
        reasons.append("Supertrend bearish.")

    # --- Volatility / Bollinger ---
    pct_b = _num(vol.get("bb_pct_b"))
    if pct_b is not None and short:
        if pct_b >= 1:
            score -= 5
            reasons.append("Price at/above upper Bollinger band.")
        elif pct_b <= 0:
            score += 3
            reasons.append("Price at/below lower Bollinger band.")
        elif 0.4 <= pct_b <= 0.7:
            score += 2

    atr_pct = _num(vol.get("atr_pct"))
    if atr_pct is not None and long and atr_pct > 4:
        score -= 3
        reasons.append(f"Elevated ATR%={atr_pct} for long horizon.")

    # --- Volume ---
    rvol = _num(volume.get("rvol"))
    if rvol is not None and short:
        ret_1d = _num(rets.get("1d")) or 0
        if rvol >= 1.5 and ret_1d > 0:
            score += 5
            reasons.append(f"High relative volume ({rvol}x) with up day.")
        elif rvol >= 1.5 and ret_1d < 0:
            score -= 5
            reasons.append(f"High relative volume ({rvol}x) with down day.")
    if _num(volume.get("obv_slope_20")) is not None:
        if volume["obv_slope_20"] > 0:
            score += 3
        else:
            score -= 3

    # --- Horizon realized return (momentum confirmation, not a forecast) ---
    horizon_ret = _num(rets.get(horizon_id))
    if horizon_ret is not None:
        # Reward positive realized momentum for that horizon; penalize deep negatives.
        bump = max(-12, min(12, horizon_ret / (3 if short else 5 if medium else 8)))
        score += bump
        reasons.append(f"Realized {horizon_id} return {horizon_ret}%.")

    # --- Distance from highs (long-term quality of trend) ---
    from_high = _num(levels.get("dist_from_52w_high_pct"))
    if from_high is not None and (medium or long):
        if from_high >= -5:
            score += 5
            reasons.append("Near 52-week highs.")
        elif from_high <= -25:
            score -= 5
            reasons.append(f"{from_high}% below 52-week high.")

    score = round(_clamp(score), 1)
    return {
        "horizon": horizon_id,
        "score": score,
        "grade": _grade(score),
        "stance": _stance(score),
        "horizon_return_pct": horizon_ret,
        "reasons": reasons[:8],
    }


def rate_all_horizons(tech: dict[str, Any]) -> dict[str, Any]:
    ratings = {h["id"]: score_horizon(tech, h["id"]) for h in HORIZONS}
    # Composite: average of all available horizons
    scores = [r["score"] for r in ratings.values()]
    composite = round(sum(scores) / len(scores), 1) if scores else 50.0
    best = max(ratings.values(), key=lambda r: r["score"])
    worst = min(ratings.values(), key=lambda r: r["score"])
    return {
        "composite_score": composite,
        "composite_grade": _grade(composite),
        "composite_stance": _stance(composite),
        "best_horizon": best["horizon"],
        "worst_horizon": worst["horizon"],
        "horizons": ratings,
        "disclaimer": (
            "Educational technical screen only. Scores combine indicators and realized "
            "horizon returns; they are not forecasts or personalized investment advice."
        ),
    }
