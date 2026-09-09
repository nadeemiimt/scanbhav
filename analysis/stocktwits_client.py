"""Stocktwits production API (HTTP Basic auth — credentials in .env only)."""
from __future__ import annotations

import os
from typing import Any, Optional

import requests
from requests.auth import HTTPBasicAuth


def _username() -> Optional[str]:
    return os.environ.get("STOCKTWITS_USERNAME") or os.environ.get("SCAN_BHAV_STOCKTWITS_USERNAME")


def _password() -> Optional[str]:
    return os.environ.get("STOCKTWITS_PASSWORD") or os.environ.get("SCAN_BHAV_STOCKTWITS_PASSWORD")


def stocktwits_configured() -> bool:
    return bool(_username() and _password())


def _base() -> str:
    return (os.environ.get("STOCKTWITS_API_BASE") or "https://api-gw-prd.stocktwits.com").rstrip("/")


def _auth() -> Optional[HTTPBasicAuth]:
    user, pwd = _username(), _password()
    if not user or not pwd:
        return None
    return HTTPBasicAuth(user, pwd)


def stocktwits_symbol(symbol: str) -> str:
    """Normalize NSE tickers for Stocktwits symbol paths."""
    sym = symbol.upper().strip()
    for suffix in (".NSE", ".NS", ".BO"):
        if sym.endswith(suffix):
            sym = sym[: -len(suffix)]
    if sym and "." not in sym:
        return f"{sym}.XNSE"
    return sym


def _get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    auth = _auth()
    if not auth:
        return {"status": "unconfigured"}
    url = f"{_base()}{path}"
    try:
        r = requests.get(
            url,
            auth=auth,
            params=params or {},
            headers={"Accept": "application/json"},
            timeout=20,
        )
        if r.status_code == 401:
            return {"status": "unauthorized", "http_status": 401}
        if r.status_code == 429:
            return {"status": "rate_limited", "http_status": 429}
        if r.status_code != 200:
            return {"status": "error", "http_status": r.status_code, "body": r.text[:200]}
        return {"status": "ok", "data": r.json()}
    except Exception as exc:
        return {"status": "error", "error": str(exc)[:120]}


def fetch_sentiment_detail(symbol: str) -> dict[str, Any]:
    sym = stocktwits_symbol(symbol)
    resp = _get(f"/api-middleware/external/sentiment/v2/{sym}/detail")
    if resp.get("status") != "ok":
        return resp
    data = resp.get("data") or {}
    sentiment = (data.get("data") or data).get("sentiment") or {}
    volume = (data.get("data") or data).get("messageVolume") or {}
    snap = sentiment.get("15m") or sentiment.get("1h") or sentiment.get("24h") or {}
    vol = volume.get("15m") or volume.get("1h") or volume.get("24h") or {}
    return {
        "status": "ok",
        "symbol": sym,
        "sentiment_label": snap.get("labelNormalized"),
        "sentiment_score": snap.get("valueNormalized"),
        "message_volume_label": vol.get("labelNormalized"),
        "message_volume_score": vol.get("valueNormalized"),
        "raw": data,
    }


def fetch_symbol_messages(symbol: str) -> dict[str, Any]:
    sym = stocktwits_symbol(symbol)
    resp = _get(f"/api-middleware/external/api/2/streams/symbol/{sym}.json")
    if resp.get("status") != "ok":
        return resp
    payload = resp.get("data") or {}
    messages = payload.get("messages") or []
    bullish = bearish = 0
    for msg in messages[:30]:
        entities = msg.get("entities") or {}
        sent = entities.get("sentiment") or {}
        basic = sent.get("basic") if isinstance(sent, dict) else None
        if basic == "Bullish":
            bullish += 1
        elif basic == "Bearish":
            bearish += 1
    return {
        "status": "ok",
        "symbol": sym,
        "message_count": len(messages),
        "bullish_count": bullish,
        "bearish_count": bearish,
        "messages": messages[:5],
    }


def fetch_social_snapshot(symbol: str) -> dict[str, Any]:
    """Combined sentiment + recent message volume for external factors."""
    if not stocktwits_configured():
        return {
            "status": "unconfigured",
            "note": "Set STOCKTWITS_USERNAME and STOCKTWITS_PASSWORD in .env",
        }

    sentiment = fetch_sentiment_detail(symbol)
    if sentiment.get("status") == "unauthorized":
        return {
            "status": "unauthorized",
            "source": "stocktwits",
            "note": "Stocktwits rejected credentials — confirm API access is enabled for this account.",
        }

    messages = fetch_symbol_messages(symbol)
    if messages.get("status") not in {"ok", "unauthorized"} and sentiment.get("status") != "ok":
        return messages if messages.get("status") != "ok" else sentiment

    msg_count = messages.get("message_count") if messages.get("status") == "ok" else None
    return {
        "status": "ok",
        "source": "stocktwits",
        "symbol": messages.get("symbol") or sentiment.get("symbol") or stocktwits_symbol(symbol),
        "message_count": msg_count,
        "stocktwits_messages": msg_count,
        "bullish_count": messages.get("bullish_count"),
        "bearish_count": messages.get("bearish_count"),
        "sentiment_label": sentiment.get("sentiment_label"),
        "sentiment_score": sentiment.get("sentiment_score"),
        "message_volume_label": sentiment.get("message_volume_label"),
        "message_volume_score": sentiment.get("message_volume_score"),
    }
