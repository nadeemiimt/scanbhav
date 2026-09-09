"""Agent 5 — event & earnings risk filter."""
from __future__ import annotations

from typing import Any, Optional

from quant_layer.agent0.etl import enrich_symbol_foundation, load_earnings_calendar


def event_risk_assessment(symbol: str, *, as_of_date: Optional[str] = None) -> dict[str, Any]:
    sym = symbol.upper()
    foundation = enrich_symbol_foundation(sym, as_of_date=as_of_date)
    flags: list[str] = []
    blocked = False
    if foundation.get("earnings_within_2d"):
        flags.append("earnings_imminent_2d")
        blocked = True
    elif foundation.get("earnings_within_5d"):
        flags.append("earnings_within_5d")
    if foundation.get("bulk_deal_flag"):
        flags.append("recent_bulk_deal")
    return {
        "symbol": sym,
        "blocked": blocked,
        "flags": flags,
        "foundation": foundation,
    }


def apply_event_risk_filter(ranked: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (survivors, filtered_out)."""
    survivors: list[dict[str, Any]] = []
    filtered: list[dict[str, Any]] = []
    for row in ranked:
        sym = str(row.get("symbol") or (row.get("quant") or {}).get("symbol") or "")
        risk = event_risk_assessment(sym)
        if risk["blocked"]:
            filtered.append({**row, "event_risk": risk})
            continue
        merged = dict(row)
        merged["event_risk"] = risk
        survivors.append(merged)
    return survivors, filtered
