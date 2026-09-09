"""Famous-investor persona views based on technical + simple fundamental cues.

Educational pattern matching only — not the actual investors' opinions or advice.
"""
from __future__ import annotations

from typing import Any, Optional


def _f(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _stance(score: float) -> str:
    if score >= 22:
        return "would_buy"
    if score >= 8:
        return "would_hold_or_accumulate"
    if score <= -22:
        return "would_sell_or_avoid"
    if score <= -8:
        return "would_reduce"
    return "neutral_watch"


def _label(stance: str) -> str:
    return {
        "would_buy": "Likely BUY / invest",
        "would_hold_or_accumulate": "Likely HOLD / add on dips",
        "neutral_watch": "WATCH — no clear fit",
        "would_reduce": "Likely REDUCE",
        "would_sell_or_avoid": "Likely SELL / avoid",
    }.get(stance, stance)


def warren_buffett(tech: dict[str, Any], fundamentals: dict[str, Any] | None = None) -> dict[str, Any]:
    """Value + quality + long runway. Prefers durable businesses near reasonable prices."""
    f = fundamentals or {}
    ma = tech.get("moving_averages") or {}
    levels = tech.get("levels") or {}
    returns = tech.get("returns_pct") or {}
    score = 0.0
    reasons: list[str] = []

    pe = _f(f.get("trailingPE") or f.get("forwardPE"))
    roe = _f(f.get("returnOnEquity"))
    debt = _f(f.get("debtToEquity"))
    margin = _f(f.get("profitMargins"))
    vs200 = _f(ma.get("price_vs_sma_200_pct"))
    dist_high = _f(levels.get("dist_from_52w_high_pct"))
    r1y = _f(returns.get("1y"))
    r5y = _f(returns.get("5y"))

    if pe is not None and 0 < pe < 22:
        score += 12
        reasons.append(f"Valuation looks approachable (PE ~{pe:.1f}).")
    elif pe is not None and pe > 40:
        score -= 10
        reasons.append(f"Rich multiple (PE ~{pe:.1f}) — Buffett-style caution on price.")
    elif pe is None:
        reasons.append("Limited PE data — leaning on trend/quality proxies.")

    if roe is not None and roe > 0.15:
        score += 14
        reasons.append(f"High ROE (~{roe * 100:.1f}%) fits quality compounder pattern.")
    elif roe is not None and roe < 0.08:
        score -= 8
        reasons.append("ROE looks modest for a classic Buffett quality bar.")

    if debt is not None and debt < 80:
        score += 8
        reasons.append("Balance-sheet leverage appears manageable.")
    elif debt is not None and debt > 150:
        score -= 10
        reasons.append("Elevated leverage — typically avoided in value-quality style.")

    if margin is not None and margin > 0.12:
        score += 6
        reasons.append("Healthy profit margins support economic moat narrative.")

    if vs200 is not None and -15 <= vs200 <= 8:
        score += 8
        reasons.append("Price near long-term average — less frothy entry zone.")
    elif vs200 is not None and vs200 > 35:
        score -= 8
        reasons.append("Far above SMA200 — patience for a better price is typical.")

    if dist_high is not None and dist_high < -20:
        score += 6
        reasons.append("Meaningful discount to 52w high — Mr. Market may be offering a sale.")

    if r5y is not None and r5y > 40:
        score += 5
        reasons.append("Multi-year price path shows durable upward compounding.")
    if r1y is not None and r1y < -25:
        score += 3
        reasons.append("1Y weakness can create value opportunity if business quality holds.")

    if not reasons:
        reasons.append("Insufficient fundamental cues; treating as watch-only.")

    stance = _stance(score)
    return {
        "id": "warren_buffett",
        "name": "Warren Buffett",
        "style": "Value + quality compounding",
        "pattern": "Buy wonderful businesses at fair prices; favour ROE, margins, sensible PE, and patience over momentum.",
        "score": round(score, 1),
        "stance": stance,
        "label": _label(stance),
        "reasons": reasons[:6],
        "disclaimer": "Simulated style lens only — not Buffett’s view or advice.",
    }


def rakesh_jhunjhunwala(tech: dict[str, Any], fundamentals: dict[str, Any] | None = None) -> dict[str, Any]:
    """Growth + conviction + India story. Likes momentum with structural uptrends."""
    f = fundamentals or {}
    ma = tech.get("moving_averages") or {}
    mom = tech.get("momentum") or {}
    trend = tech.get("trend") or {}
    returns = tech.get("returns_pct") or {}
    score = 0.0
    reasons: list[str] = []

    growth = _f(f.get("revenueGrowth") or f.get("earningsGrowth"))
    vs50 = _f(ma.get("price_vs_sma_50_pct"))
    rsi = _f(mom.get("rsi_14"))
    adx = _f(trend.get("adx_14"))
    st_dir = trend.get("supertrend_dir")
    r3m = _f(returns.get("3m"))
    r1y = _f(returns.get("1y"))
    golden = bool(ma.get("golden_cross"))

    if growth is not None and growth > 0.15:
        score += 12
        reasons.append(f"Strong growth print (~{growth * 100:.0f}%) matches high-conviction growth style.")
    elif growth is not None and growth < 0:
        score -= 8
        reasons.append("Negative growth — less aligned with aggressive India-growth bets.")

    if golden or (ma.get("ema_stack_bullish")):
        score += 10
        reasons.append("Bullish MA structure — trend following with conviction.")
    if st_dir == 1:
        score += 8
        reasons.append("Supertrend bullish — ride the tape while structure holds.")
    elif st_dir == -1:
        score -= 10
        reasons.append("Supertrend bearish — RJ-style traders often wait for trend repair.")

    if adx is not None and adx >= 25:
        score += 7
        reasons.append(f"ADX {adx:.0f} shows a usable trend to back a big idea.")
    if rsi is not None and 45 <= rsi <= 68:
        score += 6
        reasons.append("RSI in constructive mid-zone — strength without extreme euphoria.")
    elif rsi is not None and rsi > 78:
        score -= 5
        reasons.append("Very stretched RSI — even bulls may wait for a pause.")

    if r3m is not None and r3m > 8:
        score += 6
        reasons.append("Positive 3M momentum supports growth-momentum narrative.")
    if r1y is not None and r1y > 20:
        score += 6
        reasons.append("Strong 1Y trend — markets already validating the story.")
    if vs50 is not None and vs50 < -12:
        score -= 6
        reasons.append("Price well below SMA50 — momentum thesis is damaged for now.")

    if not reasons:
        reasons.append("Mixed tape — conviction not high enough for a forceful call.")

    stance = _stance(score)
    return {
        "id": "rakesh_jhunjhunwala",
        "name": "Rakesh Jhunjhunwala",
        "style": "High-conviction India growth",
        "pattern": "Back structural growth stories with trend confirmation; hold through volatility when thesis is intact.",
        "score": round(score, 1),
        "stance": stance,
        "label": _label(stance),
        "reasons": reasons[:6],
        "disclaimer": "Simulated style lens only — educational, not RJ’s recommendation.",
    }


def peter_lynch(tech: dict[str, Any], fundamentals: dict[str, Any] | None = None) -> dict[str, Any]:
    """GARP / PEG / know-what-you-own growth at reasonable price."""
    f = fundamentals or {}
    ma = tech.get("moving_averages") or {}
    returns = tech.get("returns_pct") or {}
    levels = tech.get("levels") or {}
    score = 0.0
    reasons: list[str] = []

    pe = _f(f.get("trailingPE") or f.get("forwardPE"))
    growth = _f(f.get("earningsGrowth") or f.get("revenueGrowth"))
    peg = _f(f.get("pegRatio"))
    vs200 = _f(ma.get("price_vs_sma_200_pct"))
    r1y = _f(returns.get("1y"))
    dist_low = _f(levels.get("dist_from_52w_low_pct"))

    if peg is not None and 0 < peg < 1.2:
        score += 14
        reasons.append(f"Attractive PEG (~{peg:.2f}) — classic GARP sweet spot.")
    elif peg is not None and peg > 2.5:
        score -= 8
        reasons.append(f"PEG elevated (~{peg:.2f}) — growth may already be priced in.")

    if pe is not None and growth is not None and growth > 0:
        implied = pe / (growth * 100) if growth > 1 else pe / max(growth * 100, 0.01)
        # growth may be decimal (0.2) or percent-like
        g_pct = growth * 100 if abs(growth) < 5 else growth
        if g_pct > 0 and pe / g_pct < 1.0:
            score += 10
            reasons.append(f"PE {pe:.1f} vs growth ~{g_pct:.0f}% looks like growth at a reasonable price.")
        elif g_pct > 0 and pe / g_pct > 2.0:
            score -= 6
            reasons.append("PE looks rich versus growth rate.")

    if growth is not None:
        g = growth * 100 if abs(growth) < 5 else growth
        if g > 20:
            score += 8
            reasons.append("Fast growth profile fits Lynch-style ten-bagger hunting.")
        elif g < 5:
            score -= 5
            reasons.append("Growth too slow for a classic Lynch story stock.")

    if vs200 is not None and vs200 < 0:
        score += 5
        reasons.append("Below SMA200 — possible ‘early story’ or recovery setup.")
    if r1y is not None and 5 < r1y < 60:
        score += 5
        reasons.append("Steady 1Y advance without blow-off — constructive for GARP.")
    if dist_low is not None and dist_low > 80:
        score -= 4
        reasons.append("Already far off 52w lows — less ‘undiscovered’.")

    if not reasons:
        reasons.append("Need clearer growth/valuation data for a Lynch-style read.")

    stance = _stance(score)
    return {
        "id": "peter_lynch",
        "name": "Peter Lynch",
        "style": "GARP / growth at a reasonable price",
        "pattern": "Favour understandable growth where PE is justified by earnings expansion (PEG).",
        "score": round(score, 1),
        "stance": stance,
        "label": _label(stance),
        "reasons": reasons[:6],
        "disclaimer": "Simulated style lens only — not Lynch’s view or advice.",
    }


def charlie_munger(tech: dict[str, Any], fundamentals: dict[str, Any] | None = None) -> dict[str, Any]:
    """Quality moat, rationality, avoid stupidity — fewer better businesses."""
    f = fundamentals or {}
    ma = tech.get("moving_averages") or {}
    vol = tech.get("volatility") or {}
    score = 0.0
    reasons: list[str] = []

    roe = _f(f.get("returnOnEquity"))
    margin = _f(f.get("profitMargins") or f.get("operatingMargins"))
    debt = _f(f.get("debtToEquity"))
    pe = _f(f.get("trailingPE"))
    atr_pct = _f(vol.get("atr_pct"))
    death = bool(ma.get("death_cross"))
    golden = bool(ma.get("golden_cross"))

    if roe is not None and roe > 0.18:
        score += 14
        reasons.append(f"Excellent ROE (~{roe * 100:.1f}%) — quality over mediocrity.")
    elif roe is not None and roe < 0.10:
        score -= 8
        reasons.append("ROE below quality threshold — invert: avoid average businesses.")

    if margin is not None and margin > 0.15:
        score += 10
        reasons.append("Wide margins suggest pricing power / durable advantage.")
    if debt is not None and debt < 50:
        score += 8
        reasons.append("Conservative leverage — less room for ‘stupid’ financial risk.")
    elif debt is not None and debt > 200:
        score -= 12
        reasons.append("Heavy leverage — avoidable complexity and risk.")

    if pe is not None and pe > 50:
        score -= 8
        reasons.append("Expensive — great businesses still need a rational price.")
    elif pe is not None and 10 < pe < 28:
        score += 6
        reasons.append("Valuation within a rational band for quality.")

    if atr_pct is not None and atr_pct > 4:
        score -= 4
        reasons.append("High daily volatility — harder to stay rational.")
    if golden:
        score += 4
        reasons.append("Long-term MA regime supportive.")
    if death:
        score -= 6
        reasons.append("Death cross — patience until structure improves.")

    if not reasons:
        reasons.append("Quality signals incomplete — defaulting to cautious watch.")

    stance = _stance(score)
    return {
        "id": "charlie_munger",
        "name": "Charlie Munger",
        "style": "Quality + rationality",
        "pattern": "Sit on great businesses; avoid leverage, froth, and average economics.",
        "score": round(score, 1),
        "stance": stance,
        "label": _label(stance),
        "reasons": reasons[:6],
        "disclaimer": "Simulated style lens only — not Munger’s view or advice.",
    }


def radhakishan_damani(tech: dict[str, Any], fundamentals: dict[str, Any] | None = None) -> dict[str, Any]:
    """Patient value, retail/consumer bias, buy beaten-down quality, hold long."""
    f = fundamentals or {}
    ma = tech.get("moving_averages") or {}
    levels = tech.get("levels") or {}
    mom = tech.get("momentum") or {}
    returns = tech.get("returns_pct") or {}
    score = 0.0
    reasons: list[str] = []

    pe = _f(f.get("trailingPE") or f.get("forwardPE"))
    pb = _f(f.get("priceToBook"))
    sector = str(f.get("sector") or f.get("industry") or "").lower()
    vs200 = _f(ma.get("price_vs_sma_200_pct"))
    dist_high = _f(levels.get("dist_from_52w_high_pct"))
    rsi = _f(mom.get("rsi_14"))
    r6m = _f(returns.get("6m"))

    if any(k in sector for k in ("consumer", "retail", "food", "beverage", "staples")):
        score += 8
        reasons.append("Sector tilt overlaps Damani-style consumer/retail comfort zone.")

    if pe is not None and 0 < pe < 25:
        score += 10
        reasons.append(f"Reasonable PE (~{pe:.1f}) supports patient value accumulation.")
    elif pe is not None and pe > 45:
        score -= 8
        reasons.append("Stretched valuation — typically wait for a better price.")

    if pb is not None and 0 < pb < 4:
        score += 6
        reasons.append(f"P/B ~{pb:.1f} within a value-friendly zone.")

    if dist_high is not None and dist_high < -18:
        score += 10
        reasons.append("Clear drawdown from highs — classic patient-buy opportunity zone.")
    if vs200 is not None and vs200 < -5:
        score += 6
        reasons.append("Trading below SMA200 — accumulation territory for long-horizon value.")
    if rsi is not None and rsi < 40:
        score += 5
        reasons.append("Soft RSI — fear/discount more than euphoria.")
    if r6m is not None and r6m < -10:
        score += 4
        reasons.append("6M weakness can create entry for multi-year holders.")
    if vs200 is not None and vs200 > 40:
        score -= 10
        reasons.append("Very extended vs SMA200 — unlikely to chase.")

    if not reasons:
        reasons.append("No strong value-discount signal yet — remain patient.")

    stance = _stance(score)
    return {
        "id": "radhakishan_damani",
        "name": "Radhakishan Damani",
        "style": "Patient deep value / consumer",
        "pattern": "Buy quality when unpopular; ignore short-term noise; hold for years.",
        "score": round(score, 1),
        "stance": stance,
        "label": _label(stance),
        "reasons": reasons[:6],
        "disclaimer": "Simulated style lens only — not Damani’s view or advice.",
    }


INVESTOR_FNS = [
    warren_buffett,
    rakesh_jhunjhunwala,
    peter_lynch,
    charlie_munger,
    radhakishan_damani,
]


def investor_perspectives(tech: dict[str, Any], fundamentals: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return [fn(tech, fundamentals) for fn in INVESTOR_FNS]
