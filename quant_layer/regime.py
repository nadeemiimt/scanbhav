"""Agent 6 — market regime from index proxy (deterministic)."""
from __future__ import annotations

from typing import Any, Callable, Optional

from quant_layer.triggers import build_trigger_frame


def get_market_regime(
    index_rows: list[dict[str, Any]],
    *,
    vix_level: Optional[float] = None,
) -> dict[str, Any]:
    """Classify trend / range / high-vol from Nifty (or proxy) daily bars."""
    df = build_trigger_frame(index_rows)
    if df.empty:
        return {"regime": "unknown", "confidence": 0.0}
    row = df.iloc[-1]
    adx = float(row.get("adx_14") or 0)
    trend_up = bool(row.get("trend_50_over_200"))
    atr_pct = float(row.get("atr_14") or 0) / float(row.get("close_adj") or 1) * 100

    if vix_level and vix_level > 22:
        regime = "high_volatility"
    elif adx > 25 and trend_up:
        regime = "trending_up"
    elif adx > 25 and not trend_up:
        regime = "trending_down"
    elif adx < 20:
        regime = "range_bound"
    else:
        regime = "mixed"

    route = "trend_breakout" if regime in ("trending_up", "trending_down") else "mean_reversion"
    return {
        "regime": regime,
        "route": route,
        "adx_14": round(adx, 2),
        "trend_50_over_200": trend_up,
        "atr_pct": round(atr_pct, 3),
        "vix_level": vix_level,
        "confidence": 0.7 if regime != "mixed" else 0.4,
    }


def fetch_nifty_regime(load_rows: Callable[[str], list[dict]]) -> dict[str, Any]:
    for sym in ("^NSEI", "NIFTY50.NSE", "NIFTYBEES.NSE"):
        try:
            rows = load_rows(sym)
            if len(rows) >= 50:
                return get_market_regime(rows)
        except Exception:
            continue
    return {"regime": "unknown", "confidence": 0.0}
