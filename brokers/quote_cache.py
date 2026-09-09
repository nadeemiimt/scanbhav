"""Thread-safe in-memory LTP cache fed by broker WebSocket / poll streams."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

_lock = threading.Lock()
_cache: dict[str, dict[str, Any]] = {}
_history: dict[str, list[dict[str, Any]]] = {}
_listeners: list[Callable[[str, dict[str, Any]], None]] = []


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_listener(callback: Callable[[str, dict[str, Any]], None]) -> None:
    with _lock:
        if callback not in _listeners:
            _listeners.append(callback)


def remove_listener(callback: Callable[[str, dict[str, Any]], None]) -> None:
    with _lock:
        if callback in _listeners:
            _listeners.remove(callback)


def set_ltp(
    symbol: str,
    price: float,
    *,
    source: str = "stream",
    stream: str = "websocket",
    **extra: Any,
) -> None:
    sym = symbol.strip().upper()
    if not sym or price <= 0:
        return
    row = {
        "price": float(price),
        "source": source,
        "stream": stream,
        "updated_at": _now_iso(),
        **extra,
    }
    with _lock:
        _cache[sym] = row
        hist = _history.setdefault(sym, [])
        hist.append({"price": float(price), "ts": time.time()})
        _history[sym] = hist[-40:]
        listeners = list(_listeners)
    for cb in listeners:
        try:
            cb(sym, row)
        except Exception:
            pass


def get_ltp(symbol: str, *, max_age_seconds: float = 30.0) -> Optional[dict[str, Any]]:
    sym = symbol.strip().upper()
    with _lock:
        row = _cache.get(sym)
    if not row:
        return None
    try:
        ts = datetime.fromisoformat(str(row.get("updated_at", "")).replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        if age > max_age_seconds:
            return None
    except Exception:
        pass
    return dict(row)


def get_prices(symbols: list[str], *, max_age_seconds: float = 30.0) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for sym in symbols:
        row = get_ltp(sym, max_age_seconds=max_age_seconds)
        if row:
            out[sym.strip().upper()] = row
    return out


def snapshot(*, max_age_seconds: float = 120.0) -> dict[str, Any]:
    with _lock:
        rows = dict(_cache)
    fresh = 0
    now = time.time()
    for row in rows.values():
        try:
            ts = datetime.fromisoformat(str(row.get("updated_at", "")).replace("Z", "+00:00")).timestamp()
            if now - ts <= max_age_seconds:
                fresh += 1
        except Exception:
            pass
    return {
        "symbols": len(rows),
        "fresh": fresh,
        "quotes": rows,
    }


def velocity(symbol: str, *, window_seconds: float = 5.0) -> Optional[float]:
    """Percent price change over recent tick window (for momentum / lead signals)."""
    sym = symbol.strip().upper()
    now = time.time()
    with _lock:
        hist = list(_history.get(sym) or [])
    if len(hist) < 2:
        return None
    recent = [h for h in hist if now - float(h.get("ts") or 0) <= window_seconds]
    if len(recent) < 2:
        recent = hist[-2:]
    p0 = float(recent[0].get("price") or 0)
    p1 = float(recent[-1].get("price") or 0)
    if p0 <= 0:
        return None
    return round((p1 / p0 - 1) * 100, 4)


def tick_age_seconds(symbol: str) -> Optional[float]:
    """How stale our last tick is — proxy for feed delay."""
    sym = symbol.strip().upper()
    with _lock:
        hist = _history.get(sym) or []
    if not hist:
        row = _cache.get(sym)
        if not row:
            return None
        try:
            ts = datetime.fromisoformat(str(row.get("updated_at", "")).replace("Z", "+00:00")).timestamp()
            return round(time.time() - ts, 2)
        except Exception:
            return None
    return round(time.time() - float(hist[-1].get("ts") or 0), 2)


def clear() -> None:
    with _lock:
        _cache.clear()
        _history.clear()
