"""Zerodha Kite Connect adapter — orders + LTP via kiteconnect SDK."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from brokers.base import BrokerAdapter
from brokers.config import load_broker_env, resolve_access_token
from brokers.mapping import kite_order_params
from brokers.sdk_loader import kite_connect, sdk_available
from brokers.symbols import kite_instrument
from brokers.holdings_normalize import normalize_kite_equity, normalize_kite_mf
from brokers.positions_normalize import normalize_kite_positions
from brokers.token_store import token_meta


class ZerodhaBroker(BrokerAdapter):
    broker_id = "zerodha"

    def __init__(self) -> None:
        self._env = load_broker_env()

    def _token(self) -> str:
        return resolve_access_token("zerodha", self._env)

    def _client(self):
        if not self._env.zerodha_api_key:
            raise RuntimeError("Set ZERODHA_API_KEY in .env.")
        token = self._token()
        if not token:
            raise RuntimeError(
                "Kite access token missing. GET /api/broker/auth/zerodha/login-url then complete OAuth."
            )
        kite = kite_connect(self._env.zerodha_api_key)
        kite.set_access_token(token)
        return kite

    def _configured(self) -> bool:
        return bool(self._env.zerodha_api_key and self._env.zerodha_api_secret and self._token())

    def status(self) -> dict[str, Any]:
        meta = token_meta("zerodha")
        configured = self._configured()
        return {
            "broker": self.broker_id,
            "live": configured and sdk_available("zerodha"),
            "configured": configured,
            "sdk_installed": sdk_available("zerodha"),
            "static_ip_required": False,
            "token": meta,
            "message": (
                "Kite Connect ready — live LTP and orders enabled."
                if configured and sdk_available("zerodha")
                else "Complete Kite OAuth via /api/broker/auth/zerodha/login-url"
            ),
        }

    def place_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        kite = self._client()
        params = kite_order_params(payload, kite)
        order_id = kite.place_order(**params)
        return {
            "order_id": str(order_id),
            "status": "accepted",
            "broker": self.broker_id,
            "symbol": str(payload.get("symbol", "")).upper(),
            "side": payload.get("side"),
            "quantity": payload.get("quantity"),
            "order_type": payload.get("order_type"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "message": f"Kite order placed: {order_id}",
            "raw": {"order_id": order_id},
        }

    def get_quotes(self, symbols: list[str]) -> dict[str, Any]:
        if not symbols:
            return {"quotes": {}, "errors": []}
        kite = self._client()
        instruments = [kite_instrument(s) for s in symbols]
        quotes: dict[str, Any] = {}
        errors: list[str] = []
        try:
            ltp = kite.ltp(instruments)
            for sym in symbols:
                key = sym.strip().upper()
                inst = kite_instrument(sym)
                row = ltp.get(inst) or {}
                price = row.get("last_price")
                if price is not None:
                    quotes[key] = {
                        "price": float(price),
                        "source": "zerodha",
                        "instrument": inst,
                    }
                else:
                    errors.append(f"{key}: no LTP in Kite response")
        except Exception as exc:
            errors.append(str(exc))
        return {"quotes": quotes, "errors": errors}

    def get_holdings(self) -> dict[str, Any]:
        errors: list[str] = []
        try:
            kite = self._client()
            equity_raw = kite.holdings() or []
            mf_raw = kite.mf_holdings() or []
            rows = normalize_kite_equity(equity_raw, self.broker_id) + normalize_kite_mf(mf_raw, self.broker_id)
            return {"holdings": rows, "errors": errors}
        except Exception as exc:
            return {"holdings": [], "errors": [str(exc)]}

    def get_positions(self, *, product: str | None = None) -> dict[str, Any]:
        try:
            kite = self._client()
            raw = kite.positions() or {}
            positions = normalize_kite_positions(raw, self.broker_id)
            if product:
                positions = [p for p in positions if p.get("product") == product.lower()]
            return {"positions": positions, "errors": []}
        except Exception as exc:
            return {"positions": [], "errors": [str(exc)]}

    def get_order_status(self, order_id: str) -> dict[str, Any]:
        try:
            kite = self._client()
            history = kite.order_history(order_id) or []
            if not history:
                return {"order_id": order_id, "status": "unknown", "errors": ["No order history"]}
            latest = history[-1] if isinstance(history, list) else history
            status = str(latest.get("status") or "").lower()
            filled = int(latest.get("filled_quantity") or 0)
            avg = float(latest.get("average_price") or 0)
            return {
                "order_id": order_id,
                "status": status,
                "filled_quantity": filled,
                "average_price": avg,
                "pending_quantity": int(latest.get("pending_quantity") or 0),
                "raw": latest,
            }
        except Exception as exc:
            return {"order_id": order_id, "status": "error", "errors": [str(exc)]}

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        try:
            kite = self._client()
            kite.cancel_order(variety=kite.VARIETY_REGULAR, order_id=order_id)
            return {"order_id": order_id, "cancelled": True}
        except Exception as exc:
            return {"order_id": order_id, "cancelled": False, "errors": [str(exc)]}

    def check_margin(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            kite = self._client()
            params = kite_order_params(payload, kite)
            est = kite.order_margins([params])
            row = est[0] if isinstance(est, list) and est else est
            required = float((row or {}).get("total") or (row or {}).get("margin") or 0)
            margins = kite.margins() or {}
            eq = margins.get("equity") or margins
            available = float(eq.get("available", {}).get("live_balance") or eq.get("net") or 0)
            return {
                "sufficient": available >= required if required > 0 else True,
                "required_inr": required,
                "available_inr": available,
                "broker": self.broker_id,
            }
        except Exception as exc:
            return {"sufficient": True, "skipped": True, "reason": str(exc)}
