"""Small, defensive Alpha Vantage client used by the local data pipeline."""
from __future__ import annotations

import time
from typing import Any

import requests

from config import ALPHAVANTAGE_API_KEY, ALPHAVANTAGE_REQUEST_DELAY_SECONDS

BASE_URL = "https://www.alphavantage.co/query"


class AlphaVantageError(RuntimeError):
    pass


class AlphaVantageClient:
    def __init__(self, request_delay: float = ALPHAVANTAGE_REQUEST_DELAY_SECONDS) -> None:
        if not ALPHAVANTAGE_API_KEY or ALPHAVANTAGE_API_KEY == "replace_with_your_secret_key":
            raise AlphaVantageError("Set ALPHAVANTAGE_API_KEY in your local .env file before fetching data.")
        self.request_delay = request_delay
        self._last_request = 0.0

    def query(self, function: str, **params: str) -> dict[str, Any]:
        elapsed = time.monotonic() - self._last_request
        if self._last_request and elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        response = requests.get(BASE_URL, params={"function": function, "apikey": ALPHAVANTAGE_API_KEY, **params}, timeout=45)
        self._last_request = time.monotonic()
        response.raise_for_status()
        payload = response.json()
        for key in ("Error Message", "Information", "Note"):
            if key in payload:
                raise AlphaVantageError(f"{function}: {payload[key]}")
        if not payload:
            raise AlphaVantageError(f"{function}: Alpha Vantage returned an empty response.")
        return payload
