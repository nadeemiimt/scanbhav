"""Fast LTP-triggered position guard — sub-minute stop/target enforcement."""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

from utils.logging_config import get_logger

logger = get_logger(__name__)

_listener_registered = False
_lock = threading.Lock()
_last_run: dict[str, float] = {}
_open_syms_cache: tuple[float, set[str]] = (0.0, set())


def _open_position_symbols() -> set[str]:
    global _open_syms_cache
    now = time.time()
    cached_at, cached = _open_syms_cache
    if now - cached_at < 2.0 and cached:
        return cached
    from trading.paper_ledger import open_positions

    syms = {str(p.get("symbol") or "").upper() for p in open_positions("mis")}
    syms.discard("")
    _open_syms_cache = (now, syms)
    return syms


def _make_quote_fn(primary_sym: str, primary_price: float) -> Callable[[str], float]:
    def quote_fn(sym: str) -> float:
        s = sym.upper()
        if s == primary_sym.upper():
            return primary_price
        try:
            from brokers.quote_cache import get_ltp

            row = get_ltp(s, max_age_seconds=90.0)
            if row and float(row.get("price") or 0) > 0:
                return float(row["price"])
        except Exception:
            pass
        try:
            from trading.scheduler import _quote_symbol

            return float(_quote_symbol(s))
        except Exception:
            return primary_price

    return quote_fn


def _on_ltp_tick(symbol: str, row: dict[str, Any]) -> None:
    from trading.config_store import load_trading_config

    cfg = load_trading_config()
    ap = cfg.get("autopilot") or {}
    if not ap.get("ltp_guard_enabled", True):
        return
    if not ap.get("enabled") and not ap.get("session_active"):
        try:
            from trading.session_autopilot import _active_sessions, _load_store

            if not _active_sessions(_load_store()):
                return
        except Exception:
            return

    sym = symbol.upper()
    open_syms = _open_position_symbols()
    if sym not in open_syms:
        return

    debounce = float(ap.get("ltp_guard_debounce_seconds") or 3.0)
    now = time.time()
    with _lock:
        if now - _last_run.get(sym, 0) < debounce:
            return
        _last_run[sym] = now

    price = float(row.get("price") or 0)
    if price <= 0:
        return

    try:
        from trading.position_guard import monitor_open_positions

        result = monitor_open_positions(
            _make_quote_fn(sym, price),
            symbols={sym},
        )
        actions = result.get("actions") or []
        if actions:
            logger.info("LTP guard %s: %s", sym, [a.get("reason") for a in actions])
            _open_syms_cache = (0.0, set())
    except Exception as exc:
        logger.debug("LTP guard tick failed for %s: %s", sym, exc)


def start_ltp_position_guard() -> None:
    """Register quote-cache listener for fast exit checks on price ticks."""
    global _listener_registered
    if _listener_registered:
        return
    from brokers.quote_cache import add_listener

    add_listener(_on_ltp_tick)
    _listener_registered = True
    logger.info("LTP position guard listener registered (debounced exits on tick)")


def stop_ltp_position_guard() -> None:
    global _listener_registered
    if not _listener_registered:
        return
    from brokers.quote_cache import remove_listener

    remove_listener(_on_ltp_tick)
    _listener_registered = False


def ltp_guard_status() -> dict[str, Any]:
    return {
        "registered": _listener_registered,
        "symbols_recently_checked": len(_last_run),
    }
