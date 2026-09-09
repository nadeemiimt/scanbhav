"""HTTP client — forward broker calls to a remote gateway on a static IP."""
from __future__ import annotations

import json
from typing import Any, Optional
from urllib import error, request

from brokers.config import load_broker_env


def _post_json(url: str, payload: dict[str, Any], secret: str, timeout: float = 30.0) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["X-Broker-Gateway-Secret"] = secret
    req = request.Request(url, data=body, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Broker gateway HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Broker gateway unreachable: {exc.reason}") from exc


def gateway_enabled() -> bool:
    return bool(load_broker_env().gateway_url)


def forward_order(payload: dict[str, Any]) -> dict[str, Any]:
    env = load_broker_env()
    if not env.gateway_url:
        raise RuntimeError("BROKER_GATEWAY_URL not set.")
    url = f"{env.gateway_url}/api/broker/gateway/order"
    return _post_json(url, payload, env.gateway_secret)


def forward_quotes(broker: str, symbols: list[str]) -> dict[str, Any]:
    env = load_broker_env()
    if not env.gateway_url:
        raise RuntimeError("BROKER_GATEWAY_URL not set.")
    url = f"{env.gateway_url}/api/broker/gateway/quotes"
    return _post_json(url, {"broker": broker, "symbols": symbols}, env.gateway_secret)


def verify_gateway_secret(incoming: Optional[str]) -> bool:
    env = load_broker_env()
    if not env.gateway_secret:
        # Dev-only: allow if secret not configured on gateway host
        return env.deployment_mode == "gateway_host"
    return bool(incoming) and incoming == env.gateway_secret
