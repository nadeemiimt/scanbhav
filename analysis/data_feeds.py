"""Optional external data feeds (RBI, calendar, social) via env API keys."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional


def _key(name: str) -> Optional[str]:
    return os.environ.get(name) or os.environ.get(f"STOCK_ADDA_{name}")


def fetch_rbi_macro() -> dict[str, Any]:
    """Dynamic RBI repo + India CPI (RBI.gov.in scrape + World Bank / data.gov.in)."""
    from analysis.rbi_macro import fetch_dynamic_rbi_macro

    return fetch_dynamic_rbi_macro()


def fetch_economic_calendar() -> dict[str, Any]:
    from analysis.finnhub_client import fetch_economic_calendar as finnhub_calendar

    static = [
        {"event": "RBI MPC", "impact": "high", "region": "IN"},
        {"event": "Union Budget", "impact": "high", "region": "IN"},
        {"event": "US CPI", "impact": "medium", "region": "US"},
        {"event": "India CPI/WPI", "impact": "medium", "region": "IN"},
        {"event": "FOMC", "impact": "high", "region": "US"},
    ]
    live = finnhub_calendar()
    if live.get("status") in {"ok", "partial", "restricted"} and live.get("events"):
        live["as_of"] = datetime.now(timezone.utc).isoformat()
        if live.get("status") != "ok":
            static_note = live.get("note") or ""
            live["events"] = live["events"] + [
                e for e in static if e["event"] not in {x.get("event") for x in live["events"]}
            ][:5]
            live["note"] = static_note
        return live
    if live.get("status") == "unconfigured":
        return {"status": "stub", "as_of": datetime.now(timezone.utc).isoformat(), "events": static}
    return {"status": live.get("status", "stub"), "as_of": datetime.now(timezone.utc).isoformat(), "events": static}


def fetch_social_volume(symbol: str, **kwargs: Any) -> dict[str, Any]:
    from analysis.social_volume import fetch_social_volume as composite_social

    return composite_social(symbol, **kwargs)
