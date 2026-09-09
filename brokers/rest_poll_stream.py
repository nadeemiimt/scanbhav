"""REST LTP poll loop for brokers without WebSocket (Groww, FYERS, stub fallback)."""
from __future__ import annotations

import threading
import time
from typing import Any, Optional

from brokers.quote_cache import set_ltp
from brokers.service import _get_live_quotes_direct
from utils.logging_config import get_logger

logger = get_logger(__name__)


class RestPollLtpStream:
    def __init__(self, broker_id: str, *, interval_seconds: float = 3.0) -> None:
        self.broker_id = broker_id.lower()
        self.interval_seconds = max(1.0, interval_seconds)
        self._desired: set[str] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_error: Optional[str] = None
        self._polls = 0

    def status(self) -> dict[str, Any]:
        return {
            "broker": self.broker_id,
            "transport": "rest_poll",
            "running": bool(self._thread and self._thread.is_alive()),
            "interval_seconds": self.interval_seconds,
            "desired_symbols": len(self._desired),
            "polls": self._polls,
            "last_error": self._last_error,
        }

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name=f"ltp-poll-{self.broker_id}", daemon=True)
        self._thread.start()
        logger.info("REST LTP poll stream started for %s", self.broker_id)

    def stop(self) -> None:
        self._stop.set()
        self._thread = None

    def set_symbols(self, symbols: list[str]) -> None:
        with self._lock:
            self._desired = {s.strip().upper() for s in symbols if s}

    def _loop(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                symbols = sorted(self._desired)
            if symbols:
                try:
                    batch = symbols[:48]
                    result = _get_live_quotes_direct(self.broker_id, batch)
                    self._polls += 1
                    self._last_error = None
                    for sym, row in (result.get("quotes") or {}).items():
                        price = row.get("price")
                        if price:
                            set_ltp(
                                sym,
                                float(price),
                                source=self.broker_id,
                                stream="rest_poll",
                            )
                    errs = result.get("errors") or []
                    if errs:
                        self._last_error = "; ".join(str(e) for e in errs[:2])
                except Exception as exc:
                    self._last_error = str(exc)
                    logger.debug("REST poll error (%s): %s", self.broker_id, exc)
            self._stop.wait(self.interval_seconds)
