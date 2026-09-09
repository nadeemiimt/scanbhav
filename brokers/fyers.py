"""FYERS API v3 adapter — orders + quotes via fyers-apiv3 SDK."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from brokers.base import BrokerAdapter
from brokers.config import load_broker_env, resolve_access_token
from brokers.mapping import fyers_order_payload
from brokers.sdk_loader import fyers_model, sdk_available
from brokers.symbols import fyers_symbol
from brokers.holdings_normalize import normalize_fyers
from brokers.positions_normalize import normalize_fyers_positions
from brokers.token_store import token_meta


class FyersBroker(BrokerAdapter):
    broker_id = "fyers"

    def __init__(self) -> None:
        self._env = load_broker_env()

    def _token(self) -> str:
        return resolve_access_token("fyers", self._env)

    def _client(self):
        app_id = self._env.fyers_app_id
        token = self._token()
        if not app_id or not token:
            raise RuntimeError(
                "FYERS credentials missing. Set FYERS_APP_ID + token via OAuth "
                "(/api/broker/auth/fyers/login-url)."
            )
        return fyers_model(token=token, is_async=False, client_id=app_id, log_path="")

    def _configured(self) -> bool:
        return bool(self._env.fyers_app_id and self._env.fyers_secret and self._token())

    def status(self) -> dict[str, Any]:
        meta = token_meta("fyers")
        configured = self._configured()
        return {
            "broker": self.broker_id,
            "live": configured and sdk_available("fyers"),
            "configured": configured,
            "sdk_installed": sdk_available("fyers"),
            "static_ip_required": False,
            "token": meta,
            "message": (
                "FYERS API ready — live quotes and orders enabled."
                if configured
                else "Complete FYERS OAuth via /api/broker/auth/fyers/login-url"
            ),
        }

    def place_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        fyers = self._client()
        data = fyers_order_payload(payload)
        response = fyers.place_order(data)
        if isinstance(response, dict) and response.get("s") != "ok":
            raise RuntimeError(response.get("message") or str(response))
        order_id = None
        if isinstance(response, dict):
            order_id = response.get("id") or response.get("order_id") or response.get("data", {}).get("id")
        return {
            "order_id": str(order_id or "FYERS-UNKNOWN"),
            "status": "accepted",
            "broker": self.broker_id,
            "symbol": str(payload.get("symbol", "")).upper(),
            "side": payload.get("side"),
            "quantity": payload.get("quantity"),
            "order_type": payload.get("order_type"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "message": "FYERS order submitted.",
            "raw": response,
        }

    def get_quotes(self, symbols: list[str]) -> dict[str, Any]:
        if not symbols:
            return {"quotes": {}, "errors": []}
        fyers = self._client()
        fyers_syms = ",".join(fyers_symbol(s) for s in symbols)
        quotes: dict[str, Any] = {}
        errors: list[str] = []
        try:
            response = fyers.quotes({"symbols": fyers_syms})
            if response.get("s") != "ok":
                return {"quotes": {}, "errors": [response.get("message") or str(response)]}
            data = response.get("d") or []
            by_fyers = {row.get("n"): row for row in data if isinstance(row, dict)}
            for sym in symbols:
                app_key = sym.strip().upper()
                fsym = fyers_symbol(sym)
                row = by_fyers.get(fsym) or {}
                v = row.get("v") or {}
                price = v.get("lp") or v.get("cmd", {}).get("lp")
                if price is not None:
                    quotes[app_key] = {
                        "price": float(price),
                        "source": "fyers",
                        "change_pct": v.get("chp"),
                    }
                else:
                    errors.append(f"{app_key}: no quote in FYERS response")
        except Exception as exc:
            errors.append(str(exc))
        return {"quotes": quotes, "errors": errors}

    def get_holdings(self) -> dict[str, Any]:
        try:
            fyers = self._client()
            raw = fyers.holdings()
            if isinstance(raw, dict) and raw.get("s") not in (None, "ok"):
                return {"holdings": [], "errors": [raw.get("message") or str(raw)]}
            rows = normalize_fyers(raw if isinstance(raw, dict) else {"d": raw}, self.broker_id)
            return {"holdings": rows, "errors": []}
        except Exception as exc:
            return {"holdings": [], "errors": [str(exc)]}

    def get_positions(self, *, product: str | None = None) -> dict[str, Any]:
        try:
            fyers = self._client()
            raw = fyers.positions()
            positions = normalize_fyers_positions(raw, self.broker_id)
            if product:
                positions = [p for p in positions if p.get("product") == product.lower()]
            return {"positions": positions, "errors": []}
        except Exception as exc:
            return {"positions": [], "errors": [str(exc)]}

    def get_order_status(self, order_id: str) -> dict[str, Any]:
        try:
            fyers = self._client()
            raw = fyers.orderbook()
            rows = (raw or {}).get("orderBook") or (raw or {}).get("d") or []
            if isinstance(rows, dict):
                rows = rows.get("orderBook") or []
            match = next((r for r in rows if str(r.get("id")) == str(order_id)), None)
            if not match:
                return {"order_id": order_id, "status": "unknown", "errors": ["Order not in book"]}
            status = str(match.get("status") or "").lower()
            return {
                "order_id": order_id,
                "status": status,
                "filled_quantity": int(match.get("filledQty") or 0),
                "average_price": float(match.get("tradedPrice") or match.get("limitPrice") or 0),
                "raw": match,
            }
        except Exception as exc:
            return {"order_id": order_id, "status": "error", "errors": [str(exc)]}

    def check_margin(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            fyers = self._client()
            funds = fyers.funds()
            data = (funds or {}).get("fund_limit") or (funds or {}).get("d") or []
            available = 0.0
            if isinstance(data, list):
                for row in data:
                    if str(row.get("title") or "").lower() in {"total balance", "available balance"}:
                        available = float(row.get("equityAmount") or row.get("available") or 0)
            notional = float(payload.get("limit_price") or 0) * int(payload.get("quantity") or 0)
            return {
                "sufficient": available >= notional * 0.25 if notional else True,
                "available_inr": available,
                "required_inr": notional * 0.25 if notional else 0,
                "broker": self.broker_id,
                "estimate": True,
            }
        except Exception as exc:
            return {"sufficient": True, "skipped": True, "reason": str(exc)}
