"""Zerodha KiteTicker WebSocket LTP stream."""
from __future__ import annotations

import threading
from typing import Any, Optional

from brokers.config import load_broker_env, resolve_access_token
from brokers.quote_cache import set_ltp
from brokers.sdk_loader import kite_ticker, sdk_available
from brokers.zerodha_instruments import tokens_for_symbols
from utils.logging_config import get_logger

logger = get_logger(__name__)


class ZerodhaLtpStream:
    def __init__(self) -> None:
        self._kws: Any = None
        self._lock = threading.Lock()
        self._desired: set[str] = set()
        self._token_to_symbol: dict[int, str] = {}
        self._subscribed: set[int] = set()
        self._running = False
        self._last_error: Optional[str] = None

    def status(self) -> dict[str, Any]:
        return {
            "broker": "zerodha",
            "transport": "websocket",
            "running": self._running,
            "connected": bool(self._kws and self._kws.is_connected()),
            "subscribed_symbols": len(self._subscribed),
            "desired_symbols": len(self._desired),
            "last_error": self._last_error,
        }

    def start(self) -> None:
        if self._running:
            return
        if not sdk_available("zerodha"):
            self._last_error = "kiteconnect not installed"
            return
        env = load_broker_env()
        api_key = env.zerodha_api_key
        token = resolve_access_token("zerodha", env)
        if not api_key or not token:
            self._last_error = "Zerodha OAuth token missing"
            return

        self._kws = kite_ticker(api_key, token)
        self._kws.on_ticks = self._on_ticks
        self._kws.on_connect = self._on_connect
        self._kws.on_close = self._on_close
        self._kws.on_error = self._on_error
        self._kws.on_reconnect = self._on_reconnect
        self._kws.on_order_update = self._on_order_update
        try:
            self._kws.connect(threaded=True)
            self._running = True
            self._last_error = None
            logger.info("Zerodha KiteTicker WebSocket started")
        except Exception as exc:
            self._last_error = str(exc)
            logger.warning("Zerodha stream start failed: %s", exc)

    def stop(self) -> None:
        self._running = False
        if self._kws:
            try:
                self._kws.close()
            except Exception:
                pass
        self._kws = None
        self._subscribed.clear()

    def set_symbols(self, symbols: list[str]) -> None:
        with self._lock:
            self._desired = {s.strip().upper() for s in symbols if s}
        self._sync_subscriptions()

    def _on_connect(self, _ws: Any, _response: Any) -> None:
        logger.info("KiteTicker connected")
        self._sync_subscriptions()

    def _on_reconnect(self, _ws: Any, attempts: int) -> None:
        logger.info("KiteTicker reconnect attempt %s", attempts)
        self._sync_subscriptions()

    def _on_close(self, _ws: Any, code: int, reason: str) -> None:
        logger.info("KiteTicker closed: %s %s", code, reason)

    def _on_error(self, _ws: Any, code: int, reason: str) -> None:
        self._last_error = f"{code}: {reason}"
        logger.warning("KiteTicker error: %s %s", code, reason)

    def _on_order_update(self, _ws: Any, data: dict[str, Any]) -> None:
        from trading.order_book import append_event, update_pending

        append_event({"type": "order_update", "broker": "zerodha", "data": data})
        oid = str(data.get("order_id") or "")
        if oid:
            update_pending(oid, broker_update=data, status=str(data.get("status") or "").lower())

    def _on_ticks(self, _ws: Any, ticks: list[dict[str, Any]]) -> None:
        for tick in ticks or []:
            tok = tick.get("instrument_token")
            price = tick.get("last_price")
            if tok is None or price is None:
                continue
            sym = self._token_to_symbol.get(int(tok))
            if not sym:
                continue
            set_ltp(
                sym,
                float(price),
                source="zerodha",
                stream="websocket",
                instrument_token=int(tok),
            )

    def _sync_subscriptions(self) -> None:
        if not self._kws:
            return
        with self._lock:
            desired = set(self._desired)

        token_map, missing = tokens_for_symbols(sorted(desired))
        if missing:
            logger.debug("KiteTicker missing instrument tokens: %s", missing[:5])

        self._token_to_symbol = dict(token_map)
        new_tokens = set(token_map.keys())
        to_add = new_tokens - self._subscribed
        to_remove = self._subscribed - new_tokens

        try:
            if to_remove:
                self._kws.unsubscribe(list(to_remove))
                self._subscribed -= to_remove
            if to_add:
                self._kws.subscribe(list(to_add))
                self._kws.set_mode(self._kws.MODE_LTP, list(to_add))
                self._subscribed |= to_add
        except Exception as exc:
            self._last_error = str(exc)
            logger.warning("KiteTicker subscription sync failed: %s", exc)
