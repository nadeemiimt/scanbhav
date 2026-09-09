"""Finnhub API helpers (key from .env only — never commit)."""
from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any, Optional

import requests

from fetch_stock_data import yahoo_symbol


def finnhub_key() -> Optional[str]:
    return os.environ.get("FINNHUB_API_KEY") or os.environ.get("STOCK_ADDA_FINNHUB_API_KEY")


def finnhub_webhook_secret() -> Optional[str]:
    return os.environ.get("FINNHUB_WEBHOOK_SECRET") or os.environ.get("STOCK_ADDA_FINNHUB_WEBHOOK_SECRET")


def finnhub_symbol(symbol: str) -> str:
    """Map NSE tickers to Finnhub exchange-prefixed symbols (e.g. NSE:RELIANCE)."""
    sym = yahoo_symbol(symbol)
    bare = sym.upper().removesuffix(".NS").removesuffix(".BO").removesuffix(".NSE")
    if sym.endswith(".BO"):
        return f"BSE:{bare}"
    return f"NSE:{bare}"


def _get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    key = finnhub_key()
    if not key:
        return {"status": "unconfigured"}
    p = dict(params or {})
    p["token"] = key
    try:
        r = requests.get(f"https://finnhub.io/api/v1{path}", params=p, timeout=20)
        if r.status_code != 200:
            return {"status": "error", "http_status": r.status_code, "body": r.text[:200]}
        return {"status": "ok", "data": r.json()}
    except Exception as exc:
        return {"status": "error", "error": str(exc)[:120]}


def fetch_economic_calendar(days_ahead: int = 14, days_back: int = 3) -> dict[str, Any]:
    key = finnhub_key()
    if not key:
        return {"status": "stub", "source": "none", "events": [], "note": "Set FINNHUB_API_KEY in .env"}
    start = date.today() - timedelta(days=days_back)
    end = date.today() + timedelta(days=days_ahead)
    resp = _get("/calendar/economic", {"from": start.isoformat(), "to": end.isoformat()})
    if resp.get("status") == "ok":
        raw = resp.get("data") or {}
        rows = raw.get("economicCalendar") or raw.get("data") or []
        if isinstance(raw, list):
            rows = raw
        events = _normalize_economic_rows(rows)
        india = [x for x in events if str(x.get("region", "")).upper() in {"IN", "INDIA", "IND"}]
        return {
            "status": "ok",
            "source": "finnhub",
            "from": start.isoformat(),
            "to": end.isoformat(),
            "events": events,
            "india_events": india[:8],
            "count": len(events),
        }

    earn_resp = _get(
        "/calendar/earnings",
        {"from": start.isoformat(), "to": end.isoformat(), "symbol": "", "international": True},
    )
    earn_events: list[dict[str, Any]] = []
    if earn_resp.get("status") == "ok":
        earn_rows = (earn_resp.get("data") or {}).get("earningsCalendar") or []
        for e in earn_rows[:20]:
            earn_events.append({
                "event": f"Earnings — {e.get('symbol')}",
                "date": e.get("date"),
                "impact": "medium",
                "region": "global",
                "kind": "earnings",
            })

    note = "Economic calendar requires Finnhub paid tier on this key."
    if resp.get("http_status") == 403:
        status = "restricted"
    else:
        status = "partial" if earn_events else "error"

    return {
        "status": status,
        "source": "finnhub",
        "from": start.isoformat(),
        "to": end.isoformat(),
        "events": earn_events,
        "india_events": [],
        "count": len(earn_events),
        "note": note if not earn_events else f"{note} Showing earnings calendar (free tier).",
        "http_status": resp.get("http_status"),
    }


def _normalize_economic_rows(rows: list) -> list[dict[str, Any]]:
    events = []
    for e in rows[:25]:
        events.append({
            "event": e.get("event"),
            "date": e.get("time") or e.get("date"),
            "impact": e.get("impact"),
            "region": e.get("country"),
            "actual": e.get("actual"),
            "estimate": e.get("estimate"),
            "prev": e.get("prev"),
        })
    return events


def fetch_recommendation_trends(symbol: str) -> dict[str, Any]:
    sym = finnhub_symbol(symbol)
    resp = _get("/stock/recommendation", {"symbol": sym})
    if resp.get("status") != "ok":
        return {"status": resp.get("status", "error"), "symbol": sym, **{k: v for k, v in resp.items() if k != "data"}}
    data = resp.get("data")
    if not isinstance(data, list):
        return {"status": "empty", "symbol": sym}
    history = []
    for row in data[-8:]:
        history.append({
            "period": row.get("period"),
            "strong_buy": int(row.get("strongBuy") or 0),
            "buy": int(row.get("buy") or 0),
            "hold": int(row.get("hold") or 0),
            "sell": int(row.get("sell") or 0),
            "strong_sell": int(row.get("strongSell") or 0),
        })
    latest = history[-1] if history else {}
    bull = latest.get("strong_buy", 0) + latest.get("buy", 0)
    bear = latest.get("sell", 0) + latest.get("strong_sell", 0)
    bias = "upgrades" if bull > bear else ("downgrades" if bear > bull else "neutral")
    return {"status": "ok", "source": "finnhub", "symbol": sym, "history": history, "upgrade_bias": bias}


def fetch_price_target(symbol: str) -> dict[str, Any]:
    sym = finnhub_symbol(symbol)
    resp = _get("/stock/price-target", {"symbol": sym})
    if resp.get("status") != "ok":
        return {}
    d = resp.get("data") or {}
    return {
        "target_high": d.get("targetHigh"),
        "target_low": d.get("targetLow"),
        "target_mean": d.get("targetMean"),
        "target_median": d.get("targetMedian"),
        "last_updated": d.get("lastUpdated"),
    }


def fetch_company_news(symbol: str, days: int = 14) -> dict[str, Any]:
    """Recent company headlines from Finnhub (best for US; NSE may be sparse)."""
    if not finnhub_key():
        return {"status": "unconfigured", "note": "Set FINNHUB_API_KEY in .env"}
    sym = finnhub_symbol(symbol)
    start = date.today() - timedelta(days=max(1, days))
    end = date.today()
    resp = _get("/company-news", {"symbol": sym, "from": start.isoformat(), "to": end.isoformat()})
    if resp.get("status") != "ok":
        return resp
    rows = resp.get("data") or []
    if not isinstance(rows, list):
        rows = []
    headlines = [r.get("headline") or r.get("summary") for r in rows[:25]]
    headlines = [h for h in headlines if h]
    return {
        "status": "ok" if headlines else "empty",
        "source": "finnhub",
        "symbol": sym,
        "headlines": headlines,
        "count": len(headlines),
        "note": None if headlines else f"No Finnhub news for {sym} in window.",
    }


def list_webhooks() -> dict[str, Any]:
    return _get("/webhook/list")


def register_webhook(event: str, symbol: str) -> dict[str, Any]:
    """Register outbound webhook subscription (earnings, etc.) with Finnhub."""
    sym = finnhub_symbol(symbol) if symbol else symbol
    resp = _post("/webhook/add", {"event": event, "symbol": sym})
    if resp.get("status") != "ok":
        return resp
    data = resp.get("data") or {}
    return {"status": "ok", "id": data.get("id"), "event": event, "symbol": sym}


def delete_webhook(webhook_id: str) -> dict[str, Any]:
    return _post("/webhook/delete", {"id": webhook_id})


def _post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    key = finnhub_key()
    if not key:
        return {"status": "unconfigured"}
    try:
        r = requests.post(f"https://finnhub.io/api/v1{path}", params={"token": key}, json=body, timeout=20)
        if r.status_code != 200:
            return {"status": "error", "http_status": r.status_code, "body": r.text[:200]}
        return {"status": "ok", "data": r.json()}
    except Exception as exc:
        return {"status": "error", "error": str(exc)[:120]}
