"""Agent 0 — data foundation ETL (delivery, F&O, FII/DII, bulk deals, calendar)."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from config import BASE_DIR

FOUNDATION_DIR = BASE_DIR / "data" / "quant_foundation"
DELIVERY_PATH = FOUNDATION_DIR / "delivery_pct.csv"
FII_DII_PATH = FOUNDATION_DIR / "fii_dii_flow.json"
BULK_DEALS_PATH = FOUNDATION_DIR / "bulk_deals.json"
EARNINGS_PATH = FOUNDATION_DIR / "earnings_calendar.json"
FO_OI_PATH = FOUNDATION_DIR / "fo_oi.json"
META_PATH = FOUNDATION_DIR / "last_etl.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def apply_publication_lag(df, lagged_columns: list[str], lag_days: int = 1):
    """Shift lagged columns so backtests never see same-day publication."""
    import pandas as pd

    out = df.copy()
    for col in lagged_columns:
        if col in out.columns:
            out[col] = out[col].shift(lag_days)
    return out


def load_delivery_pct(symbol: str, as_of_date: Optional[str] = None) -> Optional[float]:
    """Load delivery % from cache CSV: symbol,date,delivery_pct."""
    if not DELIVERY_PATH.exists():
        return None
    sym = symbol.replace(".NSE", "").replace(".BSE", "").upper()
    try:
        with DELIVERY_PATH.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        if as_of_date:
            for row in reversed(rows):
                if row.get("symbol", "").upper() == sym and row.get("date") == as_of_date:
                    return float(row["delivery_pct"])
        for row in reversed(rows):
            if row.get("symbol", "").upper() == sym:
                return float(row["delivery_pct"])
    except Exception:
        return None
    return None


def load_fii_dii_flow(as_of_date: Optional[str] = None) -> dict[str, Any]:
    if not FII_DII_PATH.exists():
        return {"fii_net_inr": None, "dii_net_inr": None, "as_of": None}
    try:
        data = json.loads(FII_DII_PATH.read_text(encoding="utf-8"))
        rows = data.get("rows") or []
        if as_of_date:
            hit = next((r for r in rows if r.get("date") == as_of_date), None)
            return hit or rows[-1] if rows else {}
        return rows[-1] if rows else {}
    except Exception:
        return {}


def load_bulk_deals(symbol: str, days: int = 5) -> list[dict[str, Any]]:
    if not BULK_DEALS_PATH.exists():
        return []
    sym = symbol.replace(".NSE", "").upper()
    try:
        data = json.loads(BULK_DEALS_PATH.read_text(encoding="utf-8"))
        return [r for r in (data.get("deals") or []) if str(r.get("symbol", "")).upper() == sym][-days:]
    except Exception:
        return []


def load_earnings_calendar(symbol: Optional[str] = None) -> list[dict[str, Any]]:
    if not EARNINGS_PATH.exists():
        return []
    try:
        data = json.loads(EARNINGS_PATH.read_text(encoding="utf-8"))
        events = data.get("events") or []
        if not symbol:
            return events
        sym = symbol.replace(".NSE", "").upper()
        return [e for e in events if str(e.get("symbol", "")).upper() == sym]
    except Exception:
        return []


def load_fo_oi(symbol: str) -> dict[str, Any]:
    if not FO_OI_PATH.exists():
        return {}
    sym = symbol.replace(".NSE", "").upper()
    try:
        data = json.loads(FO_OI_PATH.read_text(encoding="utf-8"))
        return (data.get("symbols") or {}).get(sym) or {}
    except Exception:
        return {}


def enrich_symbol_foundation(symbol: str, *, as_of_date: Optional[str] = None) -> dict[str, Any]:
    """Merge Agent-0 fields for one symbol (for Layer-2 JSON)."""
    fo = load_fo_oi(symbol)
    price_chg = fo.get("price_change_pct")
    oi_chg = fo.get("oi_change_pct")
    from quant_layer.helpers import classify_oi_change

    oi_signal = "neutral"
    if price_chg is not None and oi_chg is not None:
        oi_signal = classify_oi_change(float(price_chg), float(oi_chg))
    bulk = load_bulk_deals(symbol)
    earnings = load_earnings_calendar(symbol)
    return {
        "delivery_pct": load_delivery_pct(symbol, as_of_date),
        "oi_change_signal": oi_signal,
        "fo_oi_change_pct": fo.get("oi_change_pct"),
        "pcr": fo.get("pcr"),
        "bulk_deal_flag": bool(bulk),
        "bulk_deals_recent": len(bulk),
        "earnings_within_5d": _earnings_within_days(earnings, days=5),
        "earnings_within_2d": _earnings_within_days(earnings, days=2),
    }


def _earnings_within_days(events: list[dict[str, Any]], days: int) -> bool:
    if not events:
        return False
    from datetime import date, timedelta

    today = date.today()
    horizon = today + timedelta(days=days)
    for ev in events:
        try:
            d = date.fromisoformat(str(ev.get("date") or "")[:10])
            if today <= d <= horizon:
                return True
        except ValueError:
            continue
    return False


def run_agent0_etl(*, force: bool = False) -> dict[str, Any]:
    """
    Refresh foundation caches. Tries NSE helpers; falls back to existing files.
    Populate data/quant_foundation/*.json via broker/vendor feeds for production.
    """
    FOUNDATION_DIR.mkdir(parents=True, exist_ok=True)
    stats: dict[str, Any] = {"started_at": _now(), "sources": {}}

    try:
        from quant_layer.agent0.nse_fetch import sync_nse_foundation_caches

        stats["sources"]["nse"] = sync_nse_foundation_caches(force=force)
    except Exception as exc:
        stats["sources"]["nse"] = {"ok": False, "error": str(exc)[:200]}

    stats["files"] = {
        "delivery": DELIVERY_PATH.exists(),
        "fii_dii": FII_DII_PATH.exists(),
        "bulk_deals": BULK_DEALS_PATH.exists(),
        "earnings": EARNINGS_PATH.exists(),
        "fo_oi": FO_OI_PATH.exists(),
    }
    stats["finished_at"] = _now()
    META_PATH.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    return stats


def agent0_status() -> dict[str, Any]:
    meta = {}
    if META_PATH.exists():
        try:
            meta = json.loads(META_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"meta": meta, "files": {
        "delivery": DELIVERY_PATH.exists(),
        "fii_dii": FII_DII_PATH.exists(),
        "bulk_deals": BULK_DEALS_PATH.exists(),
        "earnings": EARNINGS_PATH.exists(),
        "fo_oi": FO_OI_PATH.exists(),
    }}
