"""Try a saved data API without storing the response beyond a one-line check."""
from __future__ import annotations

from typing import Any
from urllib.parse import quote

import requests

from integrations.keys import get_connector, get_secret


def _yahoo_symbol(symbol: str) -> str:
    sym = symbol.strip().upper()
    if sym.endswith(".NSE"):
        return sym.replace(".NSE", ".NS")
    if sym.endswith(".NS") or sym.endswith(".BO"):
        return sym
    return f"{sym}.NS"


def test_builtin(provider_id: str, symbol: str = "RELIANCE.NSE") -> dict[str, Any]:
    key = get_secret(provider_id)
    if provider_id in {"alphavantage", "finnhub"} and not key:
        return {"ok": False, "reason": "Save an API key first."}
    yahoo = _yahoo_symbol(symbol)
    try:
        if provider_id == "alphavantage":
            url = (
                "https://www.alphavantage.co/query?function=GLOBAL_QUOTE"
                f"&symbol={quote(yahoo)}&apikey={quote(key)}"
            )
            payload = requests.get(url, timeout=12).json()
            quote_row = payload.get("Global Quote") or {}
            price = quote_row.get("05. price")
            if not price:
                note = payload.get("Note") or payload.get("Information") or "No quote returned."
                return {"ok": False, "reason": str(note)[:180]}
            return {"ok": True, "symbol": yahoo, "price": price, "source": "alphavantage"}
        if provider_id == "finnhub":
            url = f"https://finnhub.io/api/v1/quote?symbol={quote(yahoo)}&token={quote(key)}"
            payload = requests.get(url, timeout=12).json()
            price = payload.get("c")
            if not price:
                return {"ok": False, "reason": str(payload)[:180]}
            return {"ok": True, "symbol": yahoo, "price": price, "source": "finnhub"}
    except Exception as exc:
        return {"ok": False, "reason": str(exc)[:180]}
    return {"ok": False, "reason": f"Unknown provider {provider_id}"}


def test_custom(connector_id: str, symbol: str = "RELIANCE.NSE") -> dict[str, Any]:
    row = get_connector(connector_id)
    base = str(row.get("base_url") or "")
    path = str(row.get("path_template") or "")
    if not base or not path:
        return {"ok": False, "reason": "Set a base URL and a path template."}
    url = base + path.replace("{symbol}", quote(symbol.strip().upper()))
    headers = {}
    key = str(row.get("api_key") or "")
    if key:
        name = str(row.get("header_name") or "Authorization")
        prefix = str(row.get("header_prefix") or "").strip()
        headers[name] = f"{prefix} {key}".strip() if prefix else key
    try:
        response = requests.get(url, headers=headers, timeout=12)
        return {
            "ok": response.ok,
            "status": response.status_code,
            "reason": "" if response.ok else response.text[:160],
            "source": connector_id,
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)[:180]}
