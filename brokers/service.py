"""Broker registry + unified service entrypoint."""
from __future__ import annotations

from typing import Any

from brokers.base import BrokerAdapter
from brokers.config import BROKER_LABELS, SUPPORTED_BROKERS, load_broker_env
from brokers.fyers import FyersBroker
from brokers.gateway import forward_order, forward_quotes, gateway_enabled
from brokers.groww import GrowwBroker
from brokers.stub import StubBroker
from brokers.zerodha import ZerodhaBroker

_ADAPTERS: dict[str, BrokerAdapter] = {
    "stub": StubBroker(),
    "zerodha": ZerodhaBroker(),
    "groww": GrowwBroker(),
    "fyers": FyersBroker(),
}


def get_adapter(broker_id: str | None = None) -> BrokerAdapter:
    env = load_broker_env()
    key = (broker_id or env.default_broker or "stub").lower()
    if key not in _ADAPTERS:
        raise ValueError(f"Unknown broker: {key}. Supported: {', '.join(SUPPORTED_BROKERS)}")
    return _ADAPTERS[key]


def broker_status_overview() -> dict[str, Any]:
    env = load_broker_env()
    adapters = {bid: _ADAPTERS[bid].status() for bid in SUPPORTED_BROKERS if bid in _ADAPTERS}
    return {
        "mode": env.default_broker,
        "live": any(a.get("live") for a in adapters.values()),
        "supported_brokers": list(SUPPORTED_BROKERS),
        "broker_labels": BROKER_LABELS,
        "default_broker": env.default_broker,
        "gateway": {
            "enabled": gateway_enabled(),
            "url": env.gateway_url or None,
            "deployment_mode": env.deployment_mode,
            "static_ip": env.static_ip_note or None,
            "note": (
                "Local app forwards broker API calls to gateway host with whitelisted static IP."
                if gateway_enabled()
                else (
                    "Run this backend on a static-IP VM (BROKER_DEPLOYMENT_MODE=gateway_host) "
                    "or set BROKER_GATEWAY_URL from your laptop."
                    if env.deployment_mode != "direct"
                    else "Direct mode — outbound IP must match broker whitelist."
                )
            ),
        },
        "adapters": adapters,
        "message": _status_message(env, adapters),
    }


def _status_message(env, adapters: dict[str, dict[str, Any]]) -> str:
    active = adapters.get(env.default_broker, {})
    if gateway_enabled():
        return f"Broker ops routed via gateway → {env.default_broker}."
    if env.default_broker == "stub":
        return "Stub mode — orders queued locally."
    if active.get("configured"):
        return f"{env.default_broker} credentials loaded; SDK wiring pending or live."
    return f"Set {env.default_broker.upper()} credentials on static-IP gateway host."


def _place_order_direct(payload: dict[str, Any]) -> dict[str, Any]:
    broker_id = (payload.get("broker") or load_broker_env().default_broker or "stub").lower()
    adapter = get_adapter(broker_id)
    try:
        from trading.config_store import is_live_execution, load_trading_config

        cfg = load_trading_config()
        if is_live_execution(cfg) and cfg.get("live_armed"):
            if broker_id == "stub" or not adapter.status().get("configured"):
                raise RuntimeError(f"Live armed but {broker_id} is not configured.")
        elif broker_id != "stub" and not adapter.status().get("configured"):
            stub = StubBroker().place_order({**payload, "broker": broker_id})
            stub["message"] = f"{broker_id} not configured on gateway — stub queued."
            return stub
        return adapter.place_order(payload)
    except NotImplementedError:
        stub = StubBroker().place_order(payload)
        stub["message"] = f"{broker_id} SDK not wired yet — order queued as stub."
        stub["broker_sdk_pending"] = True
        return stub


def place_order(payload: dict[str, Any]) -> dict[str, Any]:
    broker_id = (payload.get("broker") or load_broker_env().default_broker or "stub").lower()
    if gateway_enabled() and broker_id != "stub":
        payload = {**payload, "broker": broker_id}
        return forward_order(payload)
    return _place_order_direct(payload)


def _get_live_quotes_direct(broker_id: str, symbols: list[str]) -> dict[str, Any]:
    if not symbols:
        return {"quotes": {}, "errors": []}
    bid = (broker_id or load_broker_env().default_broker or "stub").lower()
    adapter = get_adapter(bid)
    try:
        return adapter.get_quotes(symbols)
    except NotImplementedError:
        return {"quotes": {}, "errors": [f"{bid} live quotes not implemented yet."]}


def _quotes_from_cache(symbols: list[str], *, max_age_seconds: float = 30.0) -> dict[str, Any]:
    from brokers.quote_cache import get_prices

    cached = get_prices(symbols, max_age_seconds=max_age_seconds)
    quotes = {
        sym: {
            "price": row["price"],
            "source": row.get("source", "stream"),
            "stream": row.get("stream", "cache"),
            "updated_at": row.get("updated_at"),
        }
        for sym, row in cached.items()
    }
    return {"quotes": quotes, "errors": [], "from_cache": True}


def get_live_quotes(broker_id: str, symbols: list[str]) -> dict[str, Any]:
    if not symbols:
        return {"quotes": {}, "errors": []}
    bid = (broker_id or load_broker_env().default_broker or "stub").lower()

    # Prefer WebSocket / poll cache when stream is active (direct mode only).
    if not gateway_enabled():
        try:
            from trading.config_store import load_trading_config

            ap = load_trading_config().get("autopilot") or {}
            if ap.get("ltp_stream_enabled", True):
                cached = _quotes_from_cache(symbols)
                missing = [s for s in symbols if s.strip().upper() not in cached["quotes"]]
                if not missing:
                    return cached
                if cached["quotes"]:
                    rest = _get_live_quotes_direct(bid, missing)
                    cached["quotes"].update(rest.get("quotes") or {})
                    cached["errors"] = rest.get("errors") or []
                    cached["from_cache"] = True
                    return cached
        except Exception:
            pass

    if gateway_enabled() and bid != "stub":
        try:
            return forward_quotes(bid, symbols)
        except RuntimeError as exc:
            return {"quotes": {}, "errors": [str(exc)]}
    return _get_live_quotes_direct(bid, symbols)


def get_positions(broker_id: str, *, product: str | None = None) -> dict[str, Any]:
    bid = (broker_id or load_broker_env().default_broker or "stub").lower()
    if bid == "stub":
        return {"positions": [], "errors": ["stub has no live positions"]}
    return get_adapter(bid).get_positions(product=product)


def get_order_status(broker_id: str, order_id: str) -> dict[str, Any]:
    bid = (broker_id or load_broker_env().default_broker or "stub").lower()
    return get_adapter(bid).get_order_status(order_id)


def check_margin(broker_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    bid = (broker_id or load_broker_env().default_broker or "stub").lower()
    if bid == "stub":
        return {"sufficient": True, "skipped": True, "reason": "stub"}
    return get_adapter(bid).check_margin(payload)
