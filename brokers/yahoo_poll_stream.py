"""Yahoo / NSE poll LTP stream — fallback when no broker API keys (stub mode)."""
from __future__ import annotations

import threading
import time
from typing import Any, Optional

from brokers.quote_cache import set_ltp
from utils.logging_config import get_logger

logger = get_logger(__name__)


class YahooPollLtpStream:
    def __init__(self, *, interval_seconds: float = 15.0, provider: str = "auto") -> None:
        self.interval_seconds = max(5.0, interval_seconds)
        self.provider = provider
        self._desired: set[str] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_error: Optional[str] = None
        self._polls = 0

    def status(self) -> dict[str, Any]:
        return {
            "broker": "yahoo",
            "transport": "yahoo_poll",
            "running": bool(self._thread and self._thread.is_alive()),
            "interval_seconds": self.interval_seconds,
            "provider": self.provider,
            "desired_symbols": len(self._desired),
            "polls": self._polls,
            "last_error": self._last_error,
        }

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="ltp-yahoo-poll", daemon=True)
        self._thread.start()
        logger.info("Yahoo LTP poll stream started (interval=%ss)", self.interval_seconds)

    def stop(self) -> None:
        self._stop.set()
        self._thread = None

    def set_symbols(self, symbols: list[str]) -> None:
        with self._lock:
            self._desired = {s.strip().upper() for s in symbols if s}

    def _quote_one(self, symbol: str) -> tuple[Optional[float], str]:
        from brokers.stub import StubBroker

        quote = StubBroker._quote_price(symbol)
        if quote and quote.get("price"):
            return float(quote["price"]), str(quote.get("source") or "yahoo")

        from routes.helpers import fetch_prices, rows_from_payload
        from technicals import compute_technicals

        try:
            payload = fetch_prices(symbol, self.provider, force_refresh=True)
            rows = rows_from_payload(payload)
            tech = compute_technicals(rows)
            price = tech.get("price")
            if price and float(price) > 0:
                return float(price), "yahoo_daily"
        except Exception:
            pass
        return None, "none"

    def _loop(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                symbols = sorted(self._desired)
            for sym in symbols[:12]:
                if self._stop.is_set():
                    break
                try:
                    price, source = self._quote_one(sym)
                    self._polls += 1
                    self._last_error = None
                    if price:
                        set_ltp(sym, price, source=source, stream="yahoo_poll")
                except Exception as exc:
                    self._last_error = str(exc)
                    logger.debug("Yahoo poll error (%s): %s", sym, exc)
                self._stop.wait(0.35)
            self._stop.wait(self.interval_seconds)
