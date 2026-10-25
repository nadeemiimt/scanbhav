"""Small, defensive Alpha Vantage client used by the local data pipeline."""
from __future__ import annotations

import time
from typing import Any

import requests

from config import ALPHAVANTAGE_API_KEY, ALPHAVANTAGE_REQUEST_DELAY_SECONDS

BASE_URL = "https://www.alphavantage.co/query"


def _api_key() -> str:
    key = (ALPHAVANTAGE_API_KEY or "").strip()
    if key and key != "replace_with_your_secret_key":
        return key
    try:
        from integrations.keys import get_secret

        return get_secret("alphavantage").strip()
    except Exception:
        return ""


class AlphaVantageError(RuntimeError):
    pass


class AlphaVantageClient:
    def __init__(self, request_delay: float = ALPHAVANTAGE_REQUEST_DELAY_SECONDS) -> None:
        key = _api_key()
        if not key:
            raise AlphaVantageError("Set Alpha Vantage in Settings → API keys (or ALPHAVANTAGE_API_KEY in .env).")
        self.api_key = key
        self.request_delay = request_delay
        self._last_request = 0.0

    def query(self, function: str, **params: str) -> dict[str, Any]:
        elapsed = time.monotonic() - self._last_request
        if self._last_request and elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        response = requests.get(BASE_URL, params={"function": function, "apikey": self.api_key, **params}, timeout=45)
        self._last_request = time.monotonic()
        response.raise_for_status()
        payload = response.json()
        for key in ("Error Message", "Information", "Note"):
            if key in payload:
                raise AlphaVantageError(f"{function}: {payload[key]}")
        if not payload:
            raise AlphaVantageError(f"{function}: Alpha Vantage returned an empty response.")
        return payload
