"""Abstract broker adapter — one implementation per provider."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class BrokerAdapter(ABC):
    broker_id: str

    @abstractmethod
    def status(self) -> dict[str, Any]:
        """Connection / credential readiness."""

    @abstractmethod
    def place_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Submit order; return normalized order record."""

    def get_quotes(self, symbols: list[str]) -> dict[str, Any]:
        """Batch LTP/quote map keyed by symbol. Override when live feed available."""
        return {"quotes": {}, "errors": [f"{self.broker_id} live quotes not wired yet."]}

    def get_holdings(self) -> dict[str, Any]:
        """Equity + MF holdings from broker API. Override per provider."""
        return {"holdings": [], "errors": [f"{self.broker_id} holdings not configured."]}

    def get_positions(self, *, product: str | None = None) -> dict[str, Any]:
        """Intraday/day/net positions. Override per provider."""
        return {"positions": [], "errors": [f"{self.broker_id} positions not wired yet."]}

    def get_order_status(self, order_id: str) -> dict[str, Any]:
        return {"order_id": order_id, "status": "unknown", "errors": [f"{self.broker_id} order status not wired."]}

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        return {"order_id": order_id, "cancelled": False, "errors": [f"{self.broker_id} cancel not wired."]}

    def check_margin(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Pre-trade margin estimate. Override per provider."""
        return {"sufficient": True, "skipped": True, "reason": "margin_check_not_wired"}

    def normalize_symbol(self, symbol: str) -> str:
        """Map app symbol (RELIANCE.NSE) to broker instrument id."""
        upper = symbol.upper().strip()
        if upper.endswith(".NSE"):
            return upper.replace(".NSE", "")
        if upper.endswith(".BSE"):
            return upper.replace(".BSE", "")
        return upper.split(".")[0]
