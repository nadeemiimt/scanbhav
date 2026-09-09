"""Resolve Zerodha instrument_token from app symbols (cached daily)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import BASE_DIR
from brokers.symbols import kite_instrument

CACHE_PATH = BASE_DIR / "data" / "broker" / "zerodha_instruments.json"


def _today_ist() -> str:
    from datetime import timedelta

    return datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d")


def _load_cache() -> dict[str, Any]:
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(payload: dict[str, Any]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def refresh_instrument_map(*, force: bool = False) -> dict[str, int]:
    """Download NSE+BSE equity instrument tokens from Kite."""
    cached = _load_cache()
    if not force and cached.get("trade_date_ist") == _today_ist() and cached.get("map"):
        return {str(k): int(v) for k, v in (cached.get("map") or {}).items()}

    from brokers.config import load_broker_env, resolve_access_token
    from brokers.sdk_loader import kite_connect

    env = load_broker_env()
    token = resolve_access_token("zerodha", env)
    if not env.zerodha_api_key or not token:
        raise RuntimeError("Zerodha credentials missing for instrument download.")

    kite = kite_connect(env.zerodha_api_key)
    kite.set_access_token(token)

    inst_map: dict[str, int] = {}
    for exchange in ("NSE", "BSE"):
        rows = kite.instruments(exchange) or []
        for row in rows:
            if not isinstance(row, dict):
                continue
            if str(row.get("instrument_type", "")).upper() != "EQ":
                continue
            tradingsymbol = str(row.get("tradingsymbol") or "").upper()
            tok = row.get("instrument_token")
            if tradingsymbol and tok:
                inst_map[f"{exchange}:{tradingsymbol}"] = int(tok)

    payload = {
        "trade_date_ist": _today_ist(),
        "count": len(inst_map),
        "map": inst_map,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_cache(payload)
    return inst_map


def instrument_map(*, force_refresh: bool = False) -> dict[str, int]:
    cached = _load_cache()
    if not force_refresh and cached.get("trade_date_ist") == _today_ist() and cached.get("map"):
        return {str(k): int(v) for k, v in (cached.get("map") or {}).items()}
    try:
        return refresh_instrument_map(force=force_refresh)
    except Exception:
        if cached.get("map"):
            return {str(k): int(v) for k, v in cached["map"].items()}
        return {}


def tokens_for_symbols(symbols: list[str]) -> tuple[dict[int, str], list[str]]:
    """
    Returns (token -> app_symbol, missing_symbols).
    App symbols are uppercase e.g. RELIANCE.NSE.
    """
    imap = instrument_map()
    token_to_symbol: dict[int, str] = {}
    missing: list[str] = []
    for sym in symbols:
        key = sym.strip().upper()
        inst = kite_instrument(key)
        tok = imap.get(inst)
        if tok:
            token_to_symbol[int(tok)] = key
        else:
            missing.append(key)
    return token_to_symbol, missing
