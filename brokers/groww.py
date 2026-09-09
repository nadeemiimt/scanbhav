"""Groww Trade API adapter — orders + LTP via growwapi SDK."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from brokers.base import BrokerAdapter
from brokers.config import load_broker_env
from brokers.groww_auth import groww_credentials_configured, resolve_groww_access_token
from brokers.mapping import groww_order_params
from brokers.sdk_loader import groww_api, sdk_available
from brokers.symbols import groww_ltp_key
from brokers.holdings_normalize import normalize_groww
from brokers.positions_normalize import normalize_groww_positions
from brokers.token_store import token_meta


class GrowwBroker(BrokerAdapter):
    broker_id = "groww"

    def __init__(self) -> None:
        self._env = load_broker_env()

    def _token(self) -> str:
        return resolve_groww_access_token()

    def _client(self):
        token = self._token()
        if not token:
            raise RuntimeError(
                "Groww token missing. Set GROWW_API_KEY + GROWW_API_SECRET, GROWW_ACCESS_TOKEN, "
                "or POST /api/broker/auth/groww/token."
            )
        return groww_api(token)

    def _configured(self) -> bool:
        return groww_credentials_configured()

    def status(self) -> dict[str, Any]:
        meta = token_meta("groww")
        configured = self._configured()
        return {
            "broker": self.broker_id,
            "live": configured and sdk_available("groww"),
            "configured": configured,
            "sdk_installed": sdk_available("groww"),
            "static_ip_required": True,
            "static_ip": self._env.static_ip_note or None,
            "token": meta,
            "message": (
                "Groww Trade API ready — data + LTP available; orders only when explicitly enabled."
                if configured
                else "Set GROWW_API_KEY + GROWW_API_SECRET (or GROWW_ACCESS_TOKEN)."
            ),
        }

    def place_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        groww = self._client()
        params = groww_order_params(payload, groww)
        response = groww.place_order(**params)
        order_id = (
            response.get("order_id")
            or response.get("groww_order_id")
            or response.get("data", {}).get("order_id")
            if isinstance(response, dict)
            else str(response)
        )
        return {
            "order_id": str(order_id),
            "status": "accepted",
            "broker": self.broker_id,
            "symbol": str(payload.get("symbol", "")).upper(),
            "side": payload.get("side"),
            "quantity": payload.get("quantity"),
            "order_type": payload.get("order_type"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "message": "Groww order submitted.",
            "raw": response if isinstance(response, dict) else {"response": response},
        }

    def get_quotes(self, symbols: list[str]) -> dict[str, Any]:
        if not symbols:
            return {"quotes": {}, "errors": []}
        groww = self._client()
        keys = tuple(groww_ltp_key(s) for s in symbols)
        quotes: dict[str, Any] = {}
        errors: list[str] = []
        try:
            ltp_map = groww.get_ltp(segment=groww.SEGMENT_CASH, exchange_trading_symbols=keys)
            if not isinstance(ltp_map, dict):
                return {"quotes": {}, "errors": ["Unexpected Groww LTP response."]}
            for sym in symbols:
                app_key = sym.strip().upper()
                gkey = groww_ltp_key(sym)
                price = ltp_map.get(gkey)
                if price is not None:
                    quotes[app_key] = {"price": float(price), "source": "groww", "groww_key": gkey}
                else:
                    errors.append(f"{app_key}: not in Groww LTP map")
        except Exception as exc:
            errors.append(str(exc))
        return {"quotes": quotes, "errors": errors}

    def get_holdings(self) -> dict[str, Any]:
        try:
            groww = self._client()
            raw = groww.get_holdings_for_user()
            rows = normalize_groww(raw, self.broker_id)
            return {"holdings": rows, "errors": []}
        except Exception as exc:
            return {"holdings": [], "errors": [str(exc)]}

    def get_positions(self, *, product: str | None = None) -> dict[str, Any]:
        try:
            groww = self._client()
            raw = groww.get_positions_for_user(segment=groww.SEGMENT_CASH)
            positions = normalize_groww_positions(raw, self.broker_id)
            if product:
                positions = [p for p in positions if p.get("product") == product.lower()]
            return {"positions": positions, "errors": []}
        except Exception as exc:
            return {"positions": [], "errors": [str(exc)]}

    def get_order_status(self, order_id: str) -> dict[str, Any]:
        try:
            groww = self._client()
            raw = groww.get_order_status(order_id=order_id)
            status = str((raw or {}).get("order_status") or (raw or {}).get("status") or "").lower()
            return {
                "order_id": order_id,
                "status": status,
                "filled_quantity": int((raw or {}).get("filled_quantity") or 0),
                "average_price": float((raw or {}).get("average_price") or 0),
                "raw": raw,
            }
        except Exception as exc:
            return {"order_id": order_id, "status": "error", "errors": [str(exc)]}

    def check_margin(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            groww = self._client()
            params = groww_order_params(payload, groww)
            raw = groww.get_order_margin_details(orders=[params])
            available_pack = groww.get_available_margin_details()
            required = float((raw or {}).get("total_margin") or (raw or {}).get("margin") or 0)
            available = float((available_pack or {}).get("available_margin") or (available_pack or {}).get("available") or 0)
            return {
                "sufficient": available >= required if required > 0 else True,
                "required_inr": required,
                "available_inr": available,
                "broker": self.broker_id,
            }
        except Exception as exc:
            return {"sufficient": True, "skipped": True, "reason": str(exc)}
