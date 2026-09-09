"""NSE trading calendar — holidays, live market status, special sessions (Muhurat)."""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from config import BASE_DIR

CACHE_PATH = BASE_DIR / "data" / "trading" / "nse_holidays_cache.json"
SPECIAL_PATH = BASE_DIR / "data" / "trading" / "nse_special_sessions.json"
STATUS_CACHE_TTL_SEC = 120
HOLIDAY_CACHE_TTL_SEC = 24 * 3600

_DEFAULT_SPECIAL: dict[str, Any] = {
    "sessions": [
        {
            "date": "2026-11-08",
            "name": "Diwali Muhurat (Laxmi Pujan)",
            "note": "NSE circular — timings may update; refresh special_sessions file.",
            "premarket_start": 17 * 60 + 45,
            "market_open": 18 * 60,
            "market_close": 19 * 60,
            "square_off": 18 * 60 + 50,
        }
    ],
    "updated_at": None,
}


def _ist_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=5, minutes=30)))


def _parse_nse_date(raw: str) -> Optional[str]:
    """DD-Mon-YYYY → YYYY-MM-DD."""
    raw = str(raw or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%d-%b-%Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


def _nse_session() -> Any:
    import requests

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://www.nseindia.com/",
    })
    session.get("https://www.nseindia.com/", timeout=15)
    time.sleep(0.35)
    return session


def _load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        return dict(default)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(default)


def _save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_special_sessions() -> dict[str, Any]:
    data = _load_json(SPECIAL_PATH, _DEFAULT_SPECIAL)
    if not data.get("sessions"):
        data["sessions"] = list(_DEFAULT_SPECIAL["sessions"])
    return data


def special_session_for_date(iso_date: str) -> Optional[dict[str, Any]]:
    for row in load_special_sessions().get("sessions") or []:
        if str(row.get("date") or "") == iso_date:
            return row
    return None


def fetch_holiday_master(*, force: bool = False) -> dict[str, Any]:
    """Fetch NSE trading holidays (CM = cash equities); cache 24h."""
    cached = _load_json(CACHE_PATH, {})
    fetched_at = float(cached.get("fetched_at") or 0)
    if not force and cached.get("CM") and (time.time() - fetched_at) < HOLIDAY_CACHE_TTL_SEC:
        return cached

    try:
        session = _nse_session()
        r = session.get(
            "https://www.nseindia.com/api/holiday-master?type=trading",
            timeout=25,
        )
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}")
        data = r.json()
        cm = data.get("CM") or []
        holidays: list[dict[str, Any]] = []
        muhurat_hints: list[dict[str, Any]] = []
        for row in cm:
            iso = _parse_nse_date(row.get("tradingDate"))
            if not iso:
                continue
            desc = str(row.get("description") or "")
            entry = {
                "date": iso,
                "description": desc,
                "weekday": row.get("weekDay"),
            }
            holidays.append(entry)
            if desc.rstrip().endswith("*") or "muhurat" in desc.lower():
                muhurat_hints.append({**entry, "note": "NSE lists as holiday* — check special_sessions for Muhurat timings."})
        payload = {
            "CM": cm,
            "holidays": holidays,
            "muhurat_hints": muhurat_hints,
            "fetched_at": time.time(),
            "source": "nse_holiday_master",
        }
        _save_json(CACHE_PATH, payload)
        return payload
    except Exception as exc:
        if cached.get("holidays"):
            cached["stale"] = True
            cached["fetch_error"] = str(exc)[:200]
            return cached
        return {
            "holidays": [],
            "muhurat_hints": [],
            "fetched_at": 0,
            "source": "fallback",
            "fetch_error": str(exc)[:200],
        }


def is_cm_holiday(iso_date: str, holidays: Optional[list[dict[str, Any]]] = None) -> bool:
    if special_session_for_date(iso_date):
        return False
    rows = holidays if holidays is not None else (fetch_holiday_master().get("holidays") or [])
    return any(str(h.get("date") or "") == iso_date for h in rows)


def fetch_market_status(*, force: bool = False) -> dict[str, Any]:
    """Live NSE marketStatus — Capital Market row."""
    cached = _load_json(CACHE_PATH, {})
    status_cache = cached.get("market_status") or {}
    fetched_at = float(status_cache.get("fetched_at") or 0)
    if not force and status_cache.get("capital_market") and (time.time() - fetched_at) < STATUS_CACHE_TTL_SEC:
        return status_cache

    try:
        session = _nse_session()
        r = session.get("https://www.nseindia.com/api/marketStatus", timeout=20)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}")
        rows = r.json().get("marketState") or []
        cm = next((x for x in rows if x.get("market") == "Capital Market"), {})
        payload = {
            "capital_market": cm,
            "fetched_at": time.time(),
            "source": "nse_market_status",
        }
        cached["market_status"] = payload
        _save_json(CACHE_PATH, cached)
        return payload
    except Exception as exc:
        if status_cache.get("capital_market"):
            status_cache["stale"] = True
            status_cache["fetch_error"] = str(exc)[:200]
            return status_cache
        return {"capital_market": {}, "fetched_at": 0, "fetch_error": str(exc)[:200]}


def _schedule_for_date(iso_date: str, cfg: dict[str, Any]) -> dict[str, int]:
    ap = cfg.get("autopilot") or {}
    special = special_session_for_date(iso_date)
    if special:
        return {
            "premarket_start": int(special.get("premarket_start") or ap.get("nse_premarket_start_minute_ist") or 9 * 60),
            "market_open": int(special.get("market_open") or ap.get("nse_market_open_minute_ist") or 9 * 60 + 15),
            "market_close": int(special.get("market_close") or ap.get("nse_market_close_minute_ist") or 15 * 60 + 30),
            "square_off": int(special.get("square_off") or ap.get("square_off_minute_ist") or 15 * 60 + 20),
            "special_session": True,
            "special_name": str(special.get("name") or "Special session"),
        }
    return {
        "premarket_start": int(ap.get("nse_premarket_start_minute_ist") or 9 * 60),
        "market_open": int(ap.get("nse_market_open_minute_ist") or 9 * 60 + 15),
        "market_close": int(ap.get("nse_market_close_minute_ist") or 15 * 60 + 30),
        "square_off": int(ap.get("square_off_minute_ist") or 15 * 60 + 20),
        "special_session": False,
        "special_name": None,
    }


def is_trading_day(iso_date: Optional[str] = None, cfg: dict[str, Any] | None = None) -> bool:
    from trading.config_store import load_trading_config

    cfg = cfg or load_trading_config()
    ap = cfg.get("autopilot") or {}
    if not ap.get("use_nse_calendar", True):
        dt = datetime.strptime(iso_date, "%Y-%m-%d") if iso_date else _ist_now()
        return dt.weekday() < 5

    iso_date = iso_date or _ist_now().strftime("%Y-%m-%d")
    if special_session_for_date(iso_date):
        return True
    dt = datetime.strptime(iso_date, "%Y-%m-%d")
    if dt.weekday() >= 5:
        return False
    return not is_cm_holiday(iso_date)


def calendar_snapshot(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    from trading.config_store import load_trading_config

    cfg = cfg or load_trading_config()
    today = _ist_now().strftime("%Y-%m-%d")
    holidays = fetch_holiday_master()
    status = fetch_market_status()
    sched = _schedule_for_date(today, cfg)
    special = special_session_for_date(today)
    return {
        "trade_date": today,
        "is_trading_day": is_trading_day(today, cfg),
        "is_holiday": is_cm_holiday(today, holidays.get("holidays")),
        "special_session": special,
        "schedule_minutes": sched,
        "market_status": status.get("capital_market") or {},
        "muhurat_hints": holidays.get("muhurat_hints") or [],
        "holidays_cached": len(holidays.get("holidays") or []),
        "source": "nse_india",
    }


def live_capital_market_open(cfg: dict[str, Any] | None = None) -> Optional[bool]:
    """True/False from NSE marketStatus when fresh; None if unavailable."""
    from trading.config_store import load_trading_config

    cfg = cfg or load_trading_config()
    if not cfg.get("autopilot", {}).get("use_nse_calendar", True):
        return None
    if not cfg.get("autopilot", {}).get("use_nse_live_status", True):
        return None
    status = fetch_market_status().get("capital_market") or {}
    if not status:
        return None
    state = str(status.get("marketStatus") or "").lower()
    if state == "open":
        return True
    if state in {"close", "closed"}:
        return False
    return None
