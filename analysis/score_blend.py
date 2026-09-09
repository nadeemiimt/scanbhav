"""Blend extended analysis signals into horizon composite scores."""
from __future__ import annotations

from typing import Any

from analysis._helpers import clamp, num


def _adjust(score: float, delta: float, reason: str, reasons: list[str]) -> float:
    if abs(delta) >= 0.5:
        reasons.append(reason)
    return clamp(score + delta)


def blend_extended_scores(ratings: dict[str, Any], extended: dict[str, Any] | None) -> dict[str, Any]:
    """Return ratings copy with extended_adjustment metadata and updated composite."""
    if not extended:
        return ratings
    out = dict(ratings)
    horizons = dict(out.get("horizons") or {})
    adjustments: list[str] = []
    delta = 0.0

    ind = extended.get("indicators") or {}
    ich = ind.get("ichimoku") or {}
    if ich.get("price_vs_cloud") == "above":
        delta += 2
        adjustments.append("Above Ichimoku cloud (+2).")
    elif ich.get("price_vs_cloud") == "below":
        delta -= 2
        adjustments.append("Below Ichimoku cloud (-2).")

    cmf = (ind.get("cmf") or {}).get("cmf_20")
    if cmf is not None:
        if cmf > 0.08:
            delta += 2
            adjustments.append(f"CMF accumulation ({cmf}) (+2).")
        elif cmf < -0.08:
            delta -= 2
            adjustments.append(f"CMF distribution ({cmf}) (-2).")

    pat = extended.get("patterns") or {}
    if pat.get("composite_bias") == "bullish":
        delta += 3
        adjustments.append("Bullish pattern cluster (+3).")
    elif pat.get("composite_bias") == "bearish":
        delta -= 3
        adjustments.append("Bearish pattern cluster (-3).")

    div = extended.get("divergence") or {}
    if div.get("composite_signal") == "bullish":
        delta += 4
        adjustments.append("RSI/MACD bullish divergence (+4).")
    elif div.get("composite_signal") == "bearish":
        delta -= 4
        adjustments.append("RSI/MACD bearish divergence (-4).")

    fund = extended.get("fundamentals") or {}
    qs = (fund.get("quality_scores") or {}).get("composite_quality")
    if qs is not None:
        if qs >= 70:
            delta += 3
            adjustments.append(f"Quality score {qs} (+3).")
        elif qs < 45:
            delta -= 3
            adjustments.append(f"Weak quality score {qs} (-3).")

    opt = extended.get("options") or {}
    if opt.get("pcr_bias") == "bullish":
        delta += 2
        adjustments.append("Options PCR bullish (+2).")
    elif opt.get("pcr_bias") == "bearish":
        delta -= 2
        adjustments.append("Options PCR bearish (-2).")

    regime = ((extended.get("regime") or {}).get("regime") or {}).get("regime")
    if regime == "bear":
        delta -= 2
        adjustments.append("Bear regime context (-2).")
    elif regime == "bull":
        delta += 2
        adjustments.append("Bull regime context (+2).")

    beta_adj = num(((extended.get("market_context") or {}).get("beta_context") or {}).get("score_adjustment")) or 0
    if beta_adj:
        delta += beta_adj
        adjustments.append(f"Beta risk adjustment ({beta_adj:+.0f}).")

    sent = num(((extended.get("external") or {}).get("nlp_sentiment") or {}).get("score"))
    if sent is not None:
        if sent > 0.2:
            delta += 2
        elif sent < -0.2:
            delta -= 2

    social = ((extended.get("external") or {}).get("social_volume") or {})
    social_score = num(social.get("sentiment_score"))
    if social_score is not None and social.get("status") == "ok":
        if social_score >= 65:
            delta += 1
        elif social_score <= 35:
            delta -= 1

    india = extended.get("india") or {}
    prom = num(((india.get("shareholding") or {}).get("promoter_pct")))
    pledge = num(((india.get("shareholding") or {}).get("pledge_pct")))
    if pledge and pledge > 25:
        delta -= 3
        adjustments.append(f"High promoter pledge {pledge}% (-3).")

    # Apply delta to composite and short horizons more than long
    composite = num(out.get("composite_score")) or 50.0
    new_composite = round(_adjust(composite, delta, "", []), 1)
    out["composite_score"] = new_composite
    out["composite_grade"] = _grade(new_composite)
    out["composite_stance"] = _stance(new_composite)
    out["extended_adjustment"] = {
        "delta": round(delta, 1),
        "reasons": adjustments[:12],
        "base_composite": composite,
    }

    for hid, hr in horizons.items():
        hscore = num(hr.get("score")) or 50.0
        weight = 1.0 if hid in {"1d", "1w", "1m"} else 0.6
        hr = dict(hr)
        hr["score"] = round(clamp(hscore + delta * weight), 1)
        hr["grade"] = _grade(hr["score"])
        hr["stance"] = _stance(hr["score"])
        horizons[hid] = hr
    out["horizons"] = horizons
    return out


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
