"""Market board: index strip + top winners/losers from cached daily data."""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

import requests

from config import BASE_DIR
from universe import universe_symbols

RAW_DIR = BASE_DIR / "data" / "raw"
MOVERS_CACHE = BASE_DIR / "data" / "screen_cache" / "movers.json"
INDICES_CACHE = BASE_DIR / "data" / "screen_cache" / "indices.json"

MOVERS_TTL_SEC = 30 * 60
INDICES_TTL_SEC = 3 * 60

INDEX_YAHOO = [
    {"id": "NIFTY", "yahoo": "^NSEI", "label": "NIFTY 50", "nse_names": ("NIFTY 50",)},
    # Sensex is BSE-only; keep Yahoo as optional fallback when not rate-limited.
    {"id": "SENSEX", "yahoo": "^BSESN", "label": "SENSEX", "nse_names": ()},
    {"id": "BANKNIFTY", "yahoo": "^NSEBANK", "label": "Bank Nifty", "nse_names": ("NIFTY BANK",)},
    {"id": "NIFTY500", "yahoo": "^CRSLDX", "label": "Nifty 500", "nse_names": ("NIFTY 500",)},
    {"id": "INDIA VIX", "yahoo": "^INDIAVIX", "label": "India VIX", "nse_names": ("INDIA VIX",)},
]


def _close_from_row(row: dict[str, Any]) -> Optional[float]:
    try:
        value = float(row.get("5. adjusted close") or row.get("4. close") or 0)
        return value if value > 0 else None
    except (TypeError, ValueError):
        return None


def _change_from_rows(rows: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if len(rows) < 2:
        return None
    last = _close_from_row(rows[-1])
    prev = _close_from_row(rows[-2])
    if last is None or prev in (None, 0):
        return None
    change_pct = (last / prev - 1) * 100
    return {
        "price": round(last, 2),
        "prev_close": round(prev, 2),
        "change_pct": round(change_pct, 2),
        "as_of": rows[-1].get("date"),
    }


def _load_cached_rows(symbol: str) -> list[dict[str, Any]]:
    path = RAW_DIR / symbol.replace("/", "_") / "daily_adjusted.json"
    import re

    safe = re.sub(r"[^A-Za-z0-9._-]", "_", symbol.upper())
    candidates = [
        RAW_DIR / safe / "daily_adjusted.json",
        RAW_DIR / symbol.upper() / "daily_adjusted.json",
        path,
    ]
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        series = payload.get("Time Series (Daily)") or {}
        rows = [{"date": date, **values} for date, values in series.items()]
        rows.sort(key=lambda r: r["date"])
        return rows
    return []


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def compute_stock_movers(limit_universe: int = 500, top_n: int = 10, *, force: bool = False) -> dict[str, Any]:
    """Rank cached NSE universe by latest 1D % change."""
    cached = _load_json(MOVERS_CACHE)
    fetched_at = float(cached.get("fetched_at") or 0)
    if (
        not force
        and cached.get("winners")
        and int(cached.get("universe_limit") or 0) >= int(limit_universe)
        and (time.time() - fetched_at) < MOVERS_TTL_SEC
    ):
        return cached

    symbols = universe_symbols(limit_universe)
    movers: list[dict[str, Any]] = []
    missing = 0
    for symbol in symbols:
        rows = _load_cached_rows(symbol)
        snap = _change_from_rows(rows)
        if not snap:
            missing += 1
            continue
        movers.append({
            "symbol": symbol,
            "name": symbol.split(".")[0],
            **snap,
        })
    winners = sorted(movers, key=lambda x: x["change_pct"], reverse=True)[:top_n]
    losers = sorted(movers, key=lambda x: x["change_pct"])[:top_n]
    for i, item in enumerate(winners, start=1):
        item["rank"] = i
    for i, item in enumerate(losers, start=1):
        item["rank"] = i
    payload = {
        "source": "cached_daily_closes",
        "live": False,
        "fetched_at": time.time(),
        "universe_limit": limit_universe,
        "note": (
            "Winners/losers use the latest two sessions in your local Yahoo/NSE cache "
            "(end-of-day). Run the screener or analyze stocks to refresh caches. "
            "Not a live tick feed."
        ),
        "scanned": len(movers),
        "missing_cache": missing,
        "winners": winners,
        "losers": losers,
    }
    _save_json(MOVERS_CACHE, payload)
    return payload


def _nse_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://www.nseindia.com/",
    })
    try:
        session.get("https://www.nseindia.com/", timeout=12)
    except Exception:
        pass
    return session


def _fetch_nse_indices() -> list[dict[str, Any]]:
    """Primary path: NSE allIndices (no Yahoo rate limit)."""
    try:
        session = _nse_session()
        response = session.get("https://www.nseindia.com/api/allIndices", timeout=15)
        if response.status_code != 200:
            return []
        rows = response.json().get("data") or []
    except Exception:
        return []

    by_name = {str(row.get("index") or "").strip().upper(): row for row in rows}
    out: list[dict[str, Any]] = []
    for meta in INDEX_YAHOO:
        row = None
        for name in meta.get("nse_names") or ():
            row = by_name.get(str(name).upper())
            if row:
                break
        if not row:
            continue
        try:
            price = float(row.get("last") or 0)
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        try:
            change_pct = float(row.get("percentChange")) if row.get("percentChange") is not None else None
        except (TypeError, ValueError):
            change_pct = None
        out.append({
            "id": meta["id"],
            "label": meta["label"],
            "yahoo": meta["yahoo"],
            "price": round(price, 2),
            "change_pct": round(change_pct, 2) if change_pct is not None else None,
            "live": True,
            "source": "nse_all_indices",
        })
    return out


def _series_last_two(close) -> tuple[Optional[float], Optional[float]]:
    try:
        if hasattr(close, "ndim") and close.ndim > 1:
            close = close.iloc[:, 0]
        last = float(close.iloc[-1])
        prev = float(close.iloc[-2]) if len(close) > 1 else None
        return last, prev
    except Exception:
        return None, None


def _fetch_yahoo_index(meta: dict[str, str]) -> Optional[dict[str, Any]]:
    """Fallback for symbols NSE does not publish (Sensex). Prefer one download call."""
    try:
        import yfinance as yf
    except Exception:
        return None
    sym = meta["yahoo"]
    try:
        frame = yf.download(sym, period="5d", progress=False, threads=False)
        if frame is None or getattr(frame, "empty", True):
            return None
        last, prev = _series_last_two(frame["Close"])
        if last is None:
            return None
        change_pct = None
        if prev not in (None, 0):
            change_pct = round((last / prev - 1) * 100, 2)
        return {
            "id": meta["id"],
            "label": meta["label"],
            "yahoo": sym,
            "price": round(last, 2),
            "change_pct": change_pct,
            "live": True,
            "source": "yahoo_download",
        }
    except Exception:
        return None


def fetch_live_indices(*, force: bool = False) -> list[dict[str, Any]]:
    """NSE first, Yahoo only for gaps, then short disk cache."""
    cached = _load_json(INDICES_CACHE)
    fetched_at = float(cached.get("fetched_at") or 0)
    cached_rows = list(cached.get("indices") or [])
    if not force and cached_rows and (time.time() - fetched_at) < INDICES_TTL_SEC:
        return cached_rows

    out = _fetch_nse_indices()
    have = {item["id"] for item in out}
    missing = [meta for meta in INDEX_YAHOO if meta["id"] not in have]
    if missing:
        # Sensex (and any other gap) — one Yahoo call at a time to reduce rate limits.
        for meta in missing:
            item = _fetch_yahoo_index(meta)
            if item:
                out.append(item)

    if not out and cached_rows:
        for item in cached_rows:
            item = dict(item)
            item["live"] = False
            item["stale"] = True
            out.append(item)

    order = {m["id"]: i for i, m in enumerate(INDEX_YAHOO)}
    out.sort(key=lambda x: order.get(x["id"], 99))
    if out and any(not item.get("stale") for item in out):
        _save_json(INDICES_CACHE, {"fetched_at": time.time(), "indices": out})
    return out


def build_ticker_strip(movers: dict[str, Any], indices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    strip: list[dict[str, Any]] = []
    for item in indices:
        ch = item.get("change_pct")
        strip.append({
            "s": item["id"],
            "v": f"{item['price']:,.2f}",
            "c": (f"{ch:+.2f}%" if ch is not None else "—"),
            "up": (ch or 0) >= 0,
            "live": bool(item.get("live")),
            "price": item["price"],
            "change_pct": ch,
        })
    for item in (movers.get("winners") or [])[:4]:
        strip.append({
            "s": item["name"],
            "v": f"{item['price']:,.2f}",
            "c": f"{item['change_pct']:+.2f}%",
            "up": item["change_pct"] >= 0,
            "live": False,
            "symbol": item["symbol"],
            "price": item["price"],
            "change_pct": item["change_pct"],
        })
    for item in (movers.get("losers") or [])[:3]:
        strip.append({
            "s": item["name"],
            "v": f"{item['price']:,.2f}",
            "c": f"{item['change_pct']:+.2f}%",
            "up": item["change_pct"] >= 0,
            "live": False,
            "symbol": item["symbol"],
            "price": item["price"],
            "change_pct": item["change_pct"],
        })
    return strip


def market_board(limit_universe: int = 500, top_n: int = 10, with_live_indices: bool = True) -> dict[str, Any]:
    with ThreadPoolExecutor(max_workers=2) as pool:
        movers_fut = pool.submit(compute_stock_movers, limit_universe, top_n)
        indices_fut = pool.submit(fetch_live_indices) if with_live_indices else None
        movers = movers_fut.result()
        indices = indices_fut.result() if indices_fut else []
    strip = build_ticker_strip(movers, indices)
    live_count = sum(1 for item in indices if item.get("live") and not item.get("stale"))
    return {
        "ticker": strip,
        "indices": indices,
        "winners": movers["winners"],
        "losers": movers["losers"],
        "meta": {
            "scanned": movers["scanned"],
            "missing_cache": movers["missing_cache"],
            "indices_live": live_count > 0,
            "indices_count": len(indices),
            "stock_moves_live": False,
            "note": movers["note"],
            "indices_note": (
                f"{live_count} index quotes from NSE"
                + (" (+ Yahoo for Sensex)" if any(i.get("source") == "yahoo_download" for i in indices) else "")
                + "."
                if live_count
                else "Index quotes unavailable right now — stock movers still from local cache."
            ),
        },
    }
