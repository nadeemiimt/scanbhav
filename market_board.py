"""Market board: live-ish index ticker + top winners/losers from cached daily data."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Optional

from config import BASE_DIR
from universe import universe_symbols

RAW_DIR = BASE_DIR / "data" / "raw"
MOVERS_CACHE = BASE_DIR / "data" / "screen_cache" / "movers.json"

INDEX_YAHOO = [
    {"id": "NIFTY", "yahoo": "^NSEI", "label": "NIFTY 50"},
    {"id": "SENSEX", "yahoo": "^BSESN", "label": "SENSEX"},
    {"id": "BANKNIFTY", "yahoo": "^NSEBANK", "label": "Bank Nifty"},
    {"id": "INDIA VIX", "yahoo": "^INDIAVIX", "label": "India VIX"},
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
    # safe_name style used in api — try both
    candidates = [
        RAW_DIR / symbol.upper() / "daily_adjusted.json",
        path,
    ]
    # Match api.safe_name loosely
    import re
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", symbol.upper())
    candidates.insert(0, RAW_DIR / safe / "daily_adjusted.json")
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


def compute_stock_movers(limit_universe: int = 500, top_n: int = 10) -> dict[str, Any]:
    """Rank cached NSE universe by latest 1D % change."""
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
    MOVERS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    MOVERS_CACHE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def fetch_live_indices() -> list[dict[str, Any]]:
    """Best-effort live (or delayed) index quotes from Yahoo Finance."""
    try:
        import yfinance as yf
    except Exception:
        return []

    out: list[dict[str, Any]] = []

    def one(meta: dict[str, str]) -> Optional[dict[str, Any]]:
        try:
            t = yf.Ticker(meta["yahoo"])
            fast = {}
            try:
                fast = t.fast_info or {}
            except Exception:
                fast = {}
            info = {}
            try:
                info = t.info or {}
            except Exception:
                info = {}

            def val(*names: str) -> Any:
                for name in names:
                    candidate = fast.get(name, info.get(name))
                    if candidate is not None:
                        try:
                            return float(candidate)
                        except (TypeError, ValueError):
                            return candidate
                return None

            price = val("lastPrice", "regularMarketPrice", "previousClose")
            prev = val("previousClose", "regularMarketPreviousClose")
            if price is None:
                return None
            change_pct = None
            if prev not in (None, 0):
                change_pct = round((float(price) / float(prev) - 1) * 100, 2)
            return {
                "id": meta["id"],
                "label": meta["label"],
                "yahoo": meta["yahoo"],
                "price": round(float(price), 2),
                "change_pct": change_pct,
                "live": True,
            }
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = [pool.submit(one, m) for m in INDEX_YAHOO]
        for fut in as_completed(futs):
            item = fut.result()
            if item:
                out.append(item)

    # Keep stable order
    order = {m["id"]: i for i, m in enumerate(INDEX_YAHOO)}
    out.sort(key=lambda x: order.get(x["id"], 99))
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
            "live": True,
            "price": item["price"],
            "change_pct": ch,
        })
    # Mix a few winners + losers so the tape feels alive
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
    movers = compute_stock_movers(limit_universe=limit_universe, top_n=top_n)
    indices = fetch_live_indices() if with_live_indices else []
    strip = build_ticker_strip(movers, indices)
    return {
        "ticker": strip,
        "indices": indices,
        "winners": movers["winners"],
        "losers": movers["losers"],
        "meta": {
            "scanned": movers["scanned"],
            "missing_cache": movers["missing_cache"],
            "indices_live": bool(indices),
            "stock_moves_live": False,
            "note": movers["note"],
            "indices_note": (
                "Index strip values are Yahoo delayed/live quotes when available."
                if indices
                else "Index live quotes unavailable — stock movers still from local cache."
            ),
        },
    }
