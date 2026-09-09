"""Market-wide breadth: advance/decline, new 52-week highs/lows."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from config import BASE_DIR
from technicals import compute_technicals
from universe import universe_symbols


def _load_rows(symbol: str) -> list[dict[str, Any]]:
    import re
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", symbol.upper())
    path = BASE_DIR / "data" / "raw" / safe / "daily_adjusted.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    entries = sorted(payload.get("Time Series (Daily)", {}).items())
    return [{"date": day, **values} for day, values in entries]


def compute_market_breadth(limit: int = 500, lookback: int = 252) -> dict[str, Any]:
    """Full breadth from cached daily bars across Nifty universe."""
    symbols = universe_symbols(limit=limit)
    adv = dec = unch = 0
    new_highs = new_lows = 0
    above_sma200 = sma_known = 0
    scored = 0

    for sym in symbols:
        rows = _load_rows(sym)
        if len(rows) < 30:
            continue
        tech = compute_technicals(rows)
        rets = tech.get("returns_pct") or {}
        chg = rets.get("1d")
        if chg is not None:
            scored += 1
            if chg > 0.15:
                adv += 1
            elif chg < -0.15:
                dec += 1
            else:
                unch += 1
        levels = tech.get("levels") or {}
        dist_hi = levels.get("dist_from_52w_high_pct")
        dist_lo = levels.get("dist_from_52w_low_pct")
        if dist_hi is not None and dist_hi >= -0.5:
            new_highs += 1
        if dist_lo is not None and dist_lo <= 0.5:
            new_lows += 1
        vs200 = (tech.get("moving_averages") or {}).get("price_vs_sma_200_pct")
        if vs200 is not None:
            sma_known += 1
            if vs200 >= 0:
                above_sma200 += 1

    ratio = round(adv / max(dec, 1), 2) if dec else None
    return {
        "status": "ok" if scored else "unavailable",
        "source": "universe_cache",
        "scored": scored,
        "advances": adv,
        "declines": dec,
        "unchanged": unch,
        "advance_decline_ratio": ratio,
        "new_52w_highs": new_highs,
        "new_52w_lows": new_lows,
        "above_sma200_pct": round(above_sma200 / sma_known * 100, 1) if sma_known else None,
        "label": (
            "strong breadth" if ratio and ratio > 1.4 and new_highs > new_lows
            else ("weak breadth" if ratio and ratio < 0.7 and new_lows > new_highs else "mixed")
        ),
        "plain": (
            f"A/D {adv}/{dec} (ratio {ratio}) · {new_highs} at 52w highs · {new_lows} at 52w lows · "
            f"{round(above_sma200 / sma_known * 100, 1) if sma_known else '—'}% above SMA200"
        ),
    }
