"""India-specific disclosures: promoter holding, FII/DII, bulk deals, announcements (NSE)."""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from typing import Any, Optional

import requests

from fetch_stock_data import nse_symbol


def _nse_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://www.nseindia.com/",
    })
    try:
        session.get("https://www.nseindia.com/", timeout=15)
        time.sleep(0.3)
    except Exception:
        pass
    return session


def fetch_shareholding(symbol: str) -> dict[str, Any]:
    sym = nse_symbol(symbol)
    try:
        session = _nse_session()
        r = session.get(
            "https://www.nseindia.com/api/corporate-share-holdings",
            params={"symbol": sym, "market": "equities"},
            timeout=20,
        )
        if r.status_code != 200:
            return {"status": "unavailable", "source": "NSE", "symbol": sym}
        data = r.json()
        rows = data if isinstance(data, list) else data.get("data") or []
        latest = rows[0] if rows else {}
        return {
            "status": "ok",
            "source": "NSE",
            "promoter_pct": _pct(latest.get("promoterAndPromoterGroup")),
            "public_pct": _pct(latest.get("public")),
            "fii_pct": _pct(latest.get("fii")),
            "dii_pct": _pct(latest.get("dii")),
            "pledge_pct": _pct(latest.get("pledge")),
            "as_of": latest.get("date") or latest.get("shareholdingDate"),
        }
    except Exception as exc:
        return {"status": "error", "source": "NSE", "error": str(exc)[:120]}


def _pct(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        return round(float(str(val).replace("%", "")), 2)
    except (TypeError, ValueError):
        return None


def fetch_fii_dii_flows() -> dict[str, Any]:
    try:
        session = _nse_session()
        r = session.get("https://www.nseindia.com/api/fiidiiTradeReact", timeout=20)
        if r.status_code != 200:
            return {"status": "unavailable", "source": "NSE"}
        data = r.json()
        return {"status": "ok", "source": "NSE", "flows": data}
    except Exception as exc:
        return {"status": "error", "source": "NSE", "error": str(exc)[:120]}


def fetch_bulk_block_deals(symbol: str) -> dict[str, Any]:
    sym = nse_symbol(symbol)
    try:
        session = _nse_session()
        r = session.get(
            "https://www.nseindia.com/api/snapshot-capital-market-largedeal",
            timeout=20,
        )
        if r.status_code != 200:
            return {"status": "unavailable", "deals": []}
        data = r.json()
        bulk = data.get("bulk") or data.get("Bulk") or []
        block = data.get("block") or data.get("Block") or []
        sym_deals = [d for d in (bulk + block) if str(d.get("symbol", "")).upper() == sym.upper()]
        return {"status": "ok", "source": "NSE", "symbol": sym, "deals": sym_deals[:10], "count": len(sym_deals)}
    except Exception as exc:
        return {"status": "error", "deals": [], "error": str(exc)[:120]}


def _date_range(days: int = 90) -> tuple[str, str]:
    end = datetime.now()
    start = end - timedelta(days=max(1, days))
    return start.strftime("%d-%m-%Y"), end.strftime("%d-%m-%Y")


def fetch_corporate_announcements(symbol: str, *, days: int = 90, limit: int = 15) -> dict[str, Any]:
    """NSE corporate announcements for a symbol."""
    sym = nse_symbol(symbol)
    from_d, to_d = _date_range(days)
    try:
        session = _nse_session()
        r = session.get(
            "https://www.nseindia.com/api/corporate-announcements",
            params={"index": "equities", "symbol": sym, "from_date": from_d, "to_date": to_d},
            timeout=25,
        )
        if r.status_code != 200:
            return {"status": "unavailable", "source": "NSE", "symbol": sym, "announcements": []}
        rows = r.json() if isinstance(r.json(), list) else []
        announcements = []
        for row in rows[:limit]:
            announcements.append({
                "date": row.get("an_dt") or row.get("sort_date"),
                "subject": row.get("desc") or row.get("attchmntText") or row.get("sm_name"),
                "text": (row.get("attchmntText") or "")[:400],
                "attachment": row.get("attchmntFile"),
                "symbol": row.get("symbol") or sym,
            })
        return {
            "status": "ok",
            "source": "NSE",
            "symbol": sym,
            "count": len(rows),
            "announcements": announcements,
            "from_date": from_d,
            "to_date": to_d,
        }
    except Exception as exc:
        return {"status": "error", "symbol": sym, "announcements": [], "error": str(exc)[:120]}


def fetch_event_calendar(symbol: str, *, days: int = 180) -> dict[str, Any]:
    """Upcoming board meetings / results dates from NSE event calendar."""
    sym = nse_symbol(symbol)
    from_d, to_d = _date_range(days)
    try:
        session = _nse_session()
        r = session.get(
            "https://www.nseindia.com/api/event-calendar",
            params={"index": "equities", "symbol": sym, "from_date": from_d, "to_date": to_d},
            timeout=20,
        )
        if r.status_code != 200:
            return {"status": "unavailable", "source": "NSE", "events": []}
        rows = r.json() if isinstance(r.json(), list) else []
        events = []
        for row in rows[:10]:
            events.append({
                "date": row.get("date"),
                "purpose": row.get("purpose"),
                "description": row.get("bm_desc"),
                "company": row.get("company"),
            })
        return {"status": "ok", "source": "NSE", "symbol": sym, "events": events, "count": len(rows)}
    except Exception as exc:
        return {"status": "error", "events": [], "error": str(exc)[:120]}


def compute_india_disclosures(symbol: str) -> dict[str, Any]:
    holding = fetch_shareholding(symbol)
    deals = fetch_bulk_block_deals(symbol)
    flows = fetch_fii_dii_flows()
    announcements = fetch_corporate_announcements(symbol)
    events = fetch_event_calendar(symbol)
    headline_parts = []
    if holding.get("promoter_pct") is not None:
        headline_parts.append(f"Promoter {holding['promoter_pct']}%")
    if holding.get("fii_pct") is not None:
        headline_parts.append(f"FII {holding['fii_pct']}%")
    if deals.get("count"):
        headline_parts.append(f"{deals['count']} bulk/block today")
    if announcements.get("count"):
        headline_parts.append(f"{announcements['count']} NSE announcements (90d)")
    if events.get("count"):
        headline_parts.append(f"{events['count']} upcoming event(s)")
    latest_ann = (announcements.get("announcements") or [{}])[0]
    return {
        "shareholding": holding,
        "bulk_block_deals": deals,
        "fii_dii_flows_market": flows,
        "corporate_announcements": announcements,
        "event_calendar": events,
        "latest_announcement": latest_ann if latest_ann else None,
        "headline": " · ".join(headline_parts) if headline_parts else "India disclosure feed pending.",
    }
