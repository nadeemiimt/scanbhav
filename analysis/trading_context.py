"""Extended signals for autopilot, morning scan, and latency compensation."""
from __future__ import annotations

from typing import Any, Optional

from analysis.patterns import compute_patterns
from analysis.score_blend import blend_extended_scores
from horizon_rank import rate_all_horizons


def extended_trade_context(
    symbol: str,
    rows: list[dict[str, Any]],
    tech: dict[str, Any],
    *,
    quote: dict[str, Any] | None = None,
    side: str = "buy",
) -> dict[str, Any]:
    """Lightweight extended gate without slow NSE calls."""
    ratings = rate_all_horizons(tech)
    patterns = compute_patterns(rows)
    pat_bias = patterns.get("composite_bias") or "neutral"
    try:
        from analysis.bundle import build_extended_analysis
        ext = build_extended_analysis(
            symbol=symbol, rows=rows, tech=tech, quote=quote, ratings=ratings, include_slow=False,
        )
        ratings = ext.get("ratings_blended") or ratings
        regime = (((ext.get("regime") or {}).get("regime") or {}).get("regime")) or "sideways"
        fund_flags = ((ext.get("fundamentals") or {}).get("fundamental_screener_flags") or {})
        div_sig = (ext.get("divergence") or {}).get("composite_signal") or "none"
    except Exception:
        ext = None
        regime = "sideways"
        fund_flags = {}
        div_sig = "none"

    composite = float(ratings.get("composite_score") or 50)
    pattern_score = 0
    if pat_bias == "bullish":
        pattern_score += 2
    elif pat_bias == "bearish":
        pattern_score -= 2
    if div_sig == "bullish":
        pattern_score += 2
    elif div_sig == "bearish":
        pattern_score -= 2
    if regime == "bear" and side == "buy":
        pattern_score -= 1
    elif regime == "bull" and side == "buy":
        pattern_score += 1

    quality_ok = fund_flags.get("quality_ok", True)
    debt_ok = fund_flags.get("debt_ok", True)
    growth_ok = fund_flags.get("growth_ok", True)
    allowed = composite >= 45 and quality_ok and debt_ok
    if side == "buy" and pat_bias == "bearish" and pattern_score < 0:
        allowed = allowed and composite >= 55

    return {
        "symbol": symbol.upper(),
        "composite_score": composite,
        "pattern_bias": pat_bias,
        "pattern_score": pattern_score,
        "divergence_signal": div_sig,
        "regime": regime,
        "quality_ok": quality_ok,
        "debt_ok": debt_ok,
        "growth_ok": growth_ok,
        "extended_allowed": allowed,
        "active_patterns": patterns.get("active_patterns") or [],
        "extended_adjustment": (ratings.get("extended_adjustment") or {}),
        "extended": ext,
    }
