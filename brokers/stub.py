"""Stub broker — local queue for dev without credentials."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from brokers.base import BrokerAdapter

_STUB_ORDERS: list[dict[str, Any]] = []


class StubBroker(BrokerAdapter):
    broker_id = "stub"

    def status(self) -> dict[str, Any]:
        return {
            "broker": self.broker_id,
            "live": False,
            "configured": True,
            "message": "Orders queued locally. Set BROKER_DEFAULT=groww|zerodha|fyers for live routing.",
            "queued_orders": len(_STUB_ORDERS),
        }

    def place_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        order_id = f"STUB-{uuid.uuid4().hex[:12].upper()}"
        now = datetime.now(timezone.utc).isoformat()
        record = {
            "order_id": order_id,
            "status": "accepted_stub",
            "broker": payload.get("broker") or self.broker_id,
            "symbol": str(payload.get("symbol", "")).upper(),
            "side": payload.get("side"),
            "quantity": payload.get("quantity"),
            "order_type": payload.get("order_type"),
            "limit_price": payload.get("limit_price"),
            "stop_price": payload.get("stop_price"),
            "target_price": payload.get("target_price"),
            "trade_id": payload.get("trade_id"),
            "product": payload.get("product"),
            "created_at": now,
            "message": "Stub order accepted.",
        }
        _STUB_ORDERS.append(record)
        if len(_STUB_ORDERS) > 200:
            del _STUB_ORDERS[:-200]
        return record


    def get_quotes(self, symbols: list[str]) -> dict[str, Any]:
        if not symbols:
            return {"quotes": {}, "errors": []}
        quotes: dict[str, Any] = {}
        errors: list[str] = []
        for sym in symbols:
            app_key = sym.strip().upper()
            price = self._quote_price(sym)
            if price is not None:
                quotes[app_key] = price
            else:
                errors.append(f"{app_key}: no LTP from Yahoo or NSE")
        return {"quotes": quotes, "errors": errors}

    @staticmethod
    def _quote_price(symbol: str) -> Optional[dict[str, Any]]:
        sym = symbol.strip().upper()
        try:
            import yfinance as yf
            from fetch_stock_data import yahoo_symbol

            fast = dict(yf.Ticker(yahoo_symbol(sym)).fast_info or {})
            raw = fast.get("lastPrice") or fast.get("last_price") or fast.get("regularMarketPrice")
            if raw and float(raw) > 0:
                return {"price": float(raw), "source": "yahoo", "stream": "yahoo_fast"}
        except Exception:
            pass
        if sym.endswith(".BSE"):
            return None
        try:
            from fetch_stock_data import fetch_nse_ltp, log_fetch_fallback_success

            price = fetch_nse_ltp(sym)
            log_fetch_fallback_success(
                sym,
                yahoo_error="no Yahoo fast quote",
                source="NSE charting 5m",
                rows=1,
                data_kind="LTP",
            )
            return {"price": price, "source": "nse_charting", "stream": "nse_charting_5m"}
        except Exception as exc:
            from fetch_stock_data import log_fetch_total_failure

            log_fetch_total_failure(sym, data_kind="LTP", detail=f"Yahoo: no fast quote; NSE: {exc}")
            return None


def list_stub_orders() -> list[dict[str, Any]]:
    return list(_STUB_ORDERS)
