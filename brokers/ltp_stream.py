"""Broker LTP stream manager — WebSocket (Zerodha), REST poll (Groww/FYERS), Yahoo fallback (stub)."""
from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, Optional

from brokers.config import load_broker_env
from brokers.gateway import gateway_enabled
from brokers.quote_cache import add_listener, remove_listener, snapshot
from brokers.rest_poll_stream import RestPollLtpStream
from brokers.yahoo_poll_stream import YahooPollLtpStream
from brokers.zerodha_stream import ZerodhaLtpStream
from utils.logging_config import get_logger

logger = get_logger(__name__)

_manager: Optional["LtpStreamManager"] = None
_ws_clients: set[Any] = set()
_ws_lock = threading.Lock()
_ephemeral_lock = threading.Lock()
_ephemeral_symbols: set[str] = set()


class LtpStreamManager:
    def __init__(self) -> None:
        self._zerodha = ZerodhaLtpStream()
        self._poll: Optional[RestPollLtpStream] = None
        self._yahoo: Optional[YahooPollLtpStream] = None
        self._broker_id = "stub"
        self._enabled = True
        self._sync_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._listener = self._broadcast_tick

    def start(self) -> None:
        if gateway_enabled():
            logger.info("LTP stream skipped — broker gateway mode uses remote REST quotes")
            return
        from trading.config_store import load_trading_config

        cfg = load_trading_config()
        ap = cfg.get("autopilot") or {}
        if ap.get("ltp_stream_enabled") is False:
            logger.info("LTP stream disabled in trading config")
            return

        env = load_broker_env()
        self._broker_id = str(cfg.get("default_broker") or env.default_broker or "stub").lower()
        self._enabled = True

        if self._broker_id == "zerodha":
            try:
                from brokers.zerodha_instruments import refresh_instrument_map

                refresh_instrument_map(force=False)
            except Exception as exc:
                logger.warning("Instrument map preload failed: %s", exc)
            self._zerodha.start()
        elif self._broker_id in {"groww", "fyers"}:
            interval = float(ap.get("ltp_poll_seconds") or 3)
            self._poll = RestPollLtpStream(self._broker_id, interval_seconds=interval)
            self._poll.start()
        else:
            interval = float(ap.get("ltp_yahoo_poll_seconds") or ap.get("ltp_poll_seconds") or 15)
            self._yahoo = YahooPollLtpStream(interval_seconds=interval)
            self._yahoo.start()
            logger.info("Yahoo LTP poll fallback (stub — no broker keys yet)")

        add_listener(self._listener)
        self._stop.clear()
        self._sync_thread = threading.Thread(target=self._sync_loop, name="ltp-sync", daemon=True)
        self._sync_thread.start()
        self.sync_now()
        logger.info("LTP stream manager started (broker=%s)", self._broker_id)
        try:
            from trading.ltp_position_guard import start_ltp_position_guard

            start_ltp_position_guard()
        except Exception as exc:
            logger.warning("LTP position guard failed to start: %s", exc)

    def stop(self) -> None:
        self._stop.set()
        try:
            from trading.ltp_position_guard import stop_ltp_position_guard

            stop_ltp_position_guard()
        except Exception:
            pass
        remove_listener(self._listener)
        self._zerodha.stop()
        if self._poll:
            self._poll.stop()
        if self._yahoo:
            self._yahoo.stop()
        with _ws_lock:
            _ws_clients.clear()

    def sync_now(self) -> list[str]:
        symbols = _desired_symbols()
        if self._broker_id == "zerodha":
            self._zerodha.set_symbols(symbols)
        elif self._poll:
            self._poll.set_symbols(symbols)
        elif self._yahoo:
            self._yahoo.set_symbols(symbols)
        return symbols

    def status(self) -> dict[str, Any]:
        cache = snapshot(max_age_seconds=60)
        transport = "none"
        stream_status: dict[str, Any] = {"broker": self._broker_id}
        if self._broker_id == "zerodha":
            transport = "websocket"
            stream_status = self._zerodha.status()
        elif self._poll:
            transport = "rest_poll"
            stream_status = self._poll.status()
        elif self._yahoo:
            transport = "yahoo_poll"
            stream_status = self._yahoo.status()

        symbols = _desired_symbols()
        return {
            "enabled": self._enabled and not gateway_enabled(),
            "running": transport != "none",
            "gateway_mode": gateway_enabled(),
            "broker": self._broker_id,
            "transport": transport,
            "stream": stream_status,
            "cache": {
                "symbols": cache.get("symbols", 0),
                "fresh_60s": cache.get("fresh", 0),
            },
            "subscribed": symbols[:24],
            "note": (
                "Zerodha = KiteTicker WebSocket. Groww/FYERS = fast REST poll. "
                "Stub (no API keys) = Yahoo/NSE poll pushed over the same WebSocket."
            ),
        }

    def _sync_loop(self) -> None:
        while not self._stop.wait(15):
            try:
                self.sync_now()
            except Exception as exc:
                logger.debug("LTP symbol sync error: %s", exc)

    def _broadcast_tick(self, symbol: str, row: dict[str, Any]) -> None:
        msg = json.dumps({"type": "ltp", "symbol": symbol, **row})
        dead = []
        with _ws_lock:
            clients = list(_ws_clients)
        for ws in clients:
            try:
                loop = getattr(ws, "_loop", None)
                if loop and loop.is_running():
                    asyncio.run_coroutine_threadsafe(ws.send_text(msg), loop)
                else:
                    dead.append(ws)
            except Exception:
                dead.append(ws)
        if dead:
            with _ws_lock:
                for ws in dead:
                    _ws_clients.discard(ws)


def _desired_symbols() -> list[str]:
    from trading.config_store import load_trading_config
    from trading.paper_ledger import open_positions

    cfg = load_trading_config()
    syms: list[str] = []
    for s in cfg.get("watchlist") or []:
        if s:
            syms.append(str(s).upper())
    ap = cfg.get("autopilot") or {}
    active = str(ap.get("active_symbol") or "").upper()
    if active:
        syms.append(active)
    for pos in open_positions("mis"):
        sym = str(pos.get("symbol") or "").upper()
        if sym:
            syms.append(sym)
    try:
        from trading.morning_scan import load_morning_scan

        ms = load_morning_scan() or {}
        for row in (ms.get("top_bullish") or [])[:12]:
            sym = str(row.get("symbol") or "").upper()
            if sym:
                syms.append(sym)
    except Exception:
        pass
    with _ephemeral_lock:
        syms.extend(sorted(_ephemeral_symbols))
    return list(dict.fromkeys(syms))


def add_stream_symbols(symbols: list[str]) -> list[str]:
    """Desk / WebSocket clients register symbols to watch (e.g. current chart symbol)."""
    with _ephemeral_lock:
        for s in symbols or []:
            sym = str(s).strip().upper()
            if sym:
                _ephemeral_symbols.add(sym)
    mgr = get_manager()
    if mgr._enabled:
        return mgr.sync_now()
    return _desired_symbols()


def get_manager() -> LtpStreamManager:
    global _manager
    if _manager is None:
        _manager = LtpStreamManager()
    return _manager


def start_ltp_stream() -> None:
    get_manager().start()


def stop_ltp_stream() -> None:
    if _manager:
        _manager.stop()


def ltp_stream_status() -> dict[str, Any]:
    if _manager is None:
        return {
            "enabled": False,
            "running": False,
            "gateway_mode": gateway_enabled(),
            "broker": load_broker_env().default_broker,
            "transport": "none",
            "cache": {"symbols": 0, "fresh_60s": 0},
        }
    return _manager.status()


def register_ws_client(ws: Any, loop: asyncio.AbstractEventLoop) -> None:
    ws._loop = loop  # type: ignore[attr-defined]
    with _ws_lock:
        _ws_clients.add(ws)


def unregister_ws_client(ws: Any) -> None:
    with _ws_lock:
        _ws_clients.discard(ws)
