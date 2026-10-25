"""
Nifty 500 light LTP watch — small thread pool + round-robin batches into quote_cache.

JS-style pattern: one coordinator thread schedules work; workers do blocking I/O only.
Agent reads merged LTP + velocity from cache (no per-cycle full-universe fetch).
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from brokers.quote_cache import get_ltp, set_ltp, velocity
from utils.logging_config import get_logger

logger = get_logger(__name__)

_stop = threading.Event()
_coordinator: Optional[threading.Thread] = None
_pool: Optional[ThreadPoolExecutor] = None
_lock = threading.Lock()
_cursor = 0
_symbols: list[str] = []
_stats: dict[str, Any] = {
    "quotes_ok": 0,
    "quotes_fail": 0,
    "last_tick_at": None,
    "last_error": None,
}


def universe_ltp_watch_cfg() -> dict[str, Any]:
    from trading.config_store import load_trading_config

    ap = load_trading_config().get("autopilot") or {}
    return {
        "enabled": bool(ap.get("universe_ltp_watch_enabled", True)),
        "workers": max(2, min(16, int(ap.get("universe_ltp_workers") or 8))),
        "batch_per_tick": max(4, min(64, int(ap.get("universe_ltp_batch_per_tick") or 16))),
        "tick_seconds": max(0.5, float(ap.get("universe_ltp_tick_seconds") or 2.0)),
        "max_age_seconds": float(ap.get("universe_ltp_max_age_seconds") or 90),
        "quote_delay_seconds": max(0.0, float(ap.get("universe_ltp_quote_delay_seconds") or 0.1)),
        "agent_use": bool(ap.get("agent_use_universe_ltp", True)),
        "fast_enrich_when_watch": bool(ap.get("agent_cycle_fast_enrich_when_ltp_watch", True)),
    }


def _load_universe_symbols() -> list[str]:
    from universe import universe_symbols

    out: list[str] = []
    for raw in universe_symbols():
        sym = str(raw or "").strip().upper()
        if not sym:
            continue
        out.append(sym if sym.endswith(".NSE") else f"{sym}.NSE")
    return list(dict.fromkeys(out))


def _fetch_light_ltp(symbol: str) -> tuple[Optional[float], str]:
    sym = symbol.strip().upper()
    from trading.config_store import load_trading_config

    cfg = load_trading_config()
    broker = str(cfg.get("default_broker") or "stub").lower()
    from brokers.gateway import gateway_enabled

    if broker != "stub" and not gateway_enabled():
        try:
            from brokers.service import _get_live_quotes_direct

            result = _get_live_quotes_direct(broker, [sym])
            row = (result.get("quotes") or {}).get(sym) or {}
            price = row.get("price")
            if price and float(price) > 0:
                return float(price), str(row.get("source") or broker)
        except Exception:
            pass

    from brokers.stub import StubBroker

    quote = StubBroker._quote_price(sym)
    if quote and quote.get("price"):
        return float(quote["price"]), str(quote.get("source") or "yahoo")
    return None, "none"


def _quote_one(symbol: str) -> None:
    cfg = universe_ltp_watch_cfg()
    if _stop.is_set():
        return
    if cfg["quote_delay_seconds"] > 0:
        time.sleep(cfg["quote_delay_seconds"])
    try:
        price, source = _fetch_light_ltp(symbol)
        with _lock:
            if price and price > 0:
                set_ltp(symbol, price, source=source, stream="universe_watch")
                _stats["quotes_ok"] = int(_stats.get("quotes_ok") or 0) + 1
                _stats["last_error"] = None
            else:
                _stats["quotes_fail"] = int(_stats.get("quotes_fail") or 0) + 1
    except Exception as exc:
        with _lock:
            _stats["quotes_fail"] = int(_stats.get("quotes_fail") or 0) + 1
            _stats["last_error"] = str(exc)[:160]


def _coordinator_loop() -> None:
    global _cursor, _symbols
    while not _stop.is_set():
        cfg = universe_ltp_watch_cfg()
        if not cfg["enabled"]:
            _stop.wait(5.0)
            continue
        if not _symbols:
            _symbols = _load_universe_symbols()
            logger.info("Universe LTP watch loaded %s symbols", len(_symbols))
        batch_n = cfg["batch_per_tick"]
        batch: list[str] = []
        with _lock:
            n = len(_symbols)
            if n:
                for _ in range(min(batch_n, n)):
                    batch.append(_symbols[_cursor % n])
                    _cursor += 1
        if batch and _pool:
            for sym in batch:
                if _stop.is_set():
                    break
                _pool.submit(_quote_one, sym)
        with _lock:
            _stats["last_tick_at"] = time.time()
            _stats["universe_size"] = len(_symbols)
            _stats["cursor"] = _cursor
        _stop.wait(cfg["tick_seconds"])


def start_universe_ltp_watch() -> None:
    global _coordinator, _pool, _cursor, _symbols
    cfg = universe_ltp_watch_cfg()
    if not cfg["enabled"]:
        return
    if _coordinator and _coordinator.is_alive():
        return
    _stop.clear()
    _symbols = _load_universe_symbols()
    _cursor = 0
    _pool = ThreadPoolExecutor(max_workers=cfg["workers"], thread_name_prefix="univ-ltp")
    _coordinator = threading.Thread(target=_coordinator_loop, name="univ-ltp-coord", daemon=True)
    _coordinator.start()
    logger.info(
        "Universe LTP watch started (workers=%s batch/tick=%s symbols=%s)",
        cfg["workers"],
        cfg["batch_per_tick"],
        len(_symbols),
    )


def stop_universe_ltp_watch() -> None:
    global _coordinator, _pool
    _stop.set()
    if _pool:
        _pool.shutdown(wait=False)
        _pool = None
    _coordinator = None


def universe_ltp_watch_status() -> dict[str, Any]:
    from brokers.quote_cache import snapshot

    cfg = universe_ltp_watch_cfg()
    cache = snapshot(max_age_seconds=cfg["max_age_seconds"])
    with _lock:
        st = dict(_stats)
        running = bool(_coordinator and _coordinator.is_alive())
    return {
        "enabled": cfg["enabled"],
        "running": running,
        "workers": cfg["workers"],
        "batch_per_tick": cfg["batch_per_tick"],
        "tick_seconds": cfg["tick_seconds"],
        "universe_size": st.get("universe_size") or len(_symbols),
        "quotes_ok": st.get("quotes_ok") or 0,
        "quotes_fail": st.get("quotes_fail") or 0,
        "cursor": st.get("cursor") or 0,
        "last_tick_at": st.get("last_tick_at"),
        "last_error": st.get("last_error"),
        "cache_fresh": cache.get("fresh"),
        "cache_symbols": cache.get("symbols"),
        "agent_use": cfg["agent_use"],
    }


def hydrate_rows_from_universe_watch(
    rows: list[dict[str, Any]],
    *,
    max_age_seconds: float | None = None,
) -> list[dict[str, Any]]:
    """Merge live LTP + short-term velocity into agent candidate rows."""
    cfg = universe_ltp_watch_cfg()
    if not cfg["agent_use"]:
        return rows
    age = max_age_seconds if max_age_seconds is not None else cfg["max_age_seconds"]
    out: list[dict[str, Any]] = []
    for row in rows:
        sym = str(row.get("symbol") or "").upper()
        if not sym:
            out.append(row)
            continue
        merged = dict(row)
        ltp = get_ltp(sym, max_age_seconds=age)
        if ltp and ltp.get("price"):
            merged["price"] = float(ltp["price"])
            merged["ltp_source"] = ltp.get("source")
            merged["ltp_stream"] = ltp.get("stream")
            merged["ltp_updated_at"] = ltp.get("updated_at")
            merged["ltp_fresh"] = True
        vel = velocity(sym)
        if vel is not None:
            merged["ltp_velocity_pct"] = vel
        out.append(merged)
    return out


def combined_universe_rows_for_agent(
    base_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Base scan rows with watch LTP overlaid; preserves ranking fields from morning scan."""
    return hydrate_rows_from_universe_watch(base_rows)
