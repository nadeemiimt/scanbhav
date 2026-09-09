"""Behavioral read on how traders may be reacting to the current tape.

Educational crowd-psychology heuristics from indicators — not clinical advice.
"""
from __future__ import annotations

from typing import Any, Optional

from market_signals import detect_psychological_barriers
from utils.numbers import parse_float as _num


def analyze_trader_behavior(
    technicals: dict[str, Any],
    ratings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a structured behavioral snapshot for the research desk psychologist."""
    mom = technicals.get("momentum") or {}
    ma = technicals.get("moving_averages") or {}
    vol = technicals.get("volatility") or {}
    volume = technicals.get("volume") or {}
    levels = technicals.get("levels") or {}
    ratings = ratings or {}

    rsi = _num(mom.get("rsi_14"))
    vs200 = _num(ma.get("price_vs_sma_200_pct"))
    vs50 = _num(ma.get("price_vs_sma_50_pct"))
    dist_high = _num(levels.get("dist_from_52w_high_pct"))
    dist_low = _num(levels.get("dist_from_52w_low_pct"))
    atr_pct = _num(vol.get("atr_pct"))
    rvol = _num(volume.get("rvol"))
    st = (technicals.get("trend") or {}).get("supertrend_dir")
    composite_stance = ratings.get("composite_stance") or "mixed"
    best_h = ratings.get("best_horizon")
    best = ((ratings.get("horizons") or {}).get(best_h or "") or {})
    horizon_ret = _num(best.get("horizon_return_pct"))

    biases: list[str] = []
    risks: list[str] = []
    supports: list[str] = []

    # RSI extremes — fear / greed shortcuts
    if rsi is not None:
        if rsi >= 72:
            biases.append("Overbought tape — late entrants may chase (FOMO); veterans watch for exhaustion.")
            risks.append("Euphoria / performance-chasing if price extended vs moving averages.")
        elif rsi <= 28:
            biases.append("Oversold tape — capitulation or panic selling may dominate short-term flows.")
            risks.append("Loss aversion — holders may freeze or dump into weakness.")
        elif 55 <= rsi < 72:
            supports.append("Momentum confidence — dip-buyers may treat pullbacks as normal in an uptrend.")
        elif 28 < rsi <= 45:
            supports.append("Cautious crowd — buyers want confirmation before adding size.")

    if vs200 is not None:
        if vs200 > 8:
            biases.append("Anchoring to recent highs — pullbacks can feel 'cheap' even when trend is stretched.")
        elif vs200 < -12:
            biases.append("Recency bias from drawdown — every bounce may be sold as 'dead cat' until proof builds.")
            risks.append("Pessimism premium — good news may be ignored until price reclaims key averages.")

    if dist_high is not None and dist_high > -3:
        biases.append("Near 52-week highs — winner's curse (reluctance to sell) vs breakout FOMO both rise.")
    if dist_low is not None and dist_low < 25:
        biases.append("Far above 52-week lows — survivors may feel vindicated; new money may still hesitate.")

    if atr_pct is not None and atr_pct > 3.5:
        risks.append(f"Elevated daily swings (~{atr_pct:.1f}% ATR) — stress, overtrading, and stop-hunting behavior rise.")
    if rvol is not None and rvol >= 1.6:
        biases.append("High relative volume — conviction trades and reactive flows are active (watch false breakouts).")

    if st == 1:
        supports.append("Supertrend bullish — trend-followers may add on dips; contrarians feel lonely.")
    elif st == -1:
        risks.append("Supertrend bearish — dip-buying reflexes may fail until trend flips.")

    if horizon_ret is not None:
        if horizon_ret > 15:
            biases.append("Strong recent gains — social proof may pull in incremental buyers.")
        elif horizon_ret < -12:
            biases.append("Painful recent drawdown — disposition effect (holding losers, cutting winners) may show up.")

    primary_mood = "balanced"
    if rsi is not None and rsi >= 70:
        primary_mood = "greed-prone"
    elif rsi is not None and rsi <= 30:
        primary_mood = "fear-prone"
    elif composite_stance in ("bullish", "strong_favorable", "favorable"):
        primary_mood = "optimistic"
    elif composite_stance in ("bearish", "cautious", "unfavorable"):
        primary_mood = "defensive"

    headline = (
        f"Crowd mood looks {primary_mood.replace('-', ' ')} on the {best_h or 'ranked'} horizon "
        f"({composite_stance.replace('_', ' ')} composite)."
    )
    if rsi is not None:
        headline += f" RSI14={rsi:.0f}."
    if vs200 is not None:
        headline += f" Price {vs200:+.1f}% vs SMA200."

    plain = " ".join(biases[:2]) if biases else headline
    if risks:
        plain += " Watch for: " + risks[0]

    barriers = detect_psychological_barriers(technicals)
    barrier_list = barriers.get("barriers") or []

    return {
        "primary_mood": primary_mood,
        "composite_stance": composite_stance,
        "rsi_14": rsi,
        "price_vs_sma_200_pct": vs200,
        "price_vs_sma_50_pct": vs50,
        "dist_from_52w_high_pct": dist_high,
        "atr_pct": atr_pct,
        "relative_volume": rvol,
        "headline": headline,
        "plain_english": plain[:480],
        "biases": biases[:6],
        "behavior_risks": risks[:5],
        "supportive_behaviors": supports[:4],
        "psychological_barriers": barrier_list,
        "psychological_barriers_read": barriers.get("headline"),
        "disclaimer": (
            "Behavioral read is an educational heuristic from price/volume indicators — "
            "not psychology advice or a forecast of what any person will do."
        ),
    }
