"""Broker adapter configuration (env-driven, provider-agnostic)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from config import setting


@dataclass(frozen=True)
class BrokerEnv:
    """Runtime broker settings loaded from environment."""

    default_broker: str
    gateway_url: str
    gateway_secret: str
    static_ip_note: str
    deployment_mode: str  # local | gateway_host | direct

    # Zerodha Kite Connect
    zerodha_api_key: str
    zerodha_api_secret: str
    zerodha_access_token: str

    # Groww Trade API
    groww_api_key: str
    groww_api_secret: str
    groww_access_token: str

    # FYERS API v3
    fyers_app_id: str
    fyers_secret: str
    fyers_access_token: str


def resolve_access_token(broker: str, env: BrokerEnv | None = None) -> str:
    """Env var wins, then data/broker_tokens.json."""
    from brokers.token_store import get_stored_token

    env = env or load_broker_env()
    broker = broker.lower()
    if broker == "zerodha":
        return env.zerodha_access_token or get_stored_token("zerodha") or ""
    if broker == "groww":
        return env.groww_access_token or get_stored_token("groww") or ""
    if broker == "fyers":
        return env.fyers_access_token or get_stored_token("fyers") or ""
    return ""


def load_broker_env() -> BrokerEnv:
    return BrokerEnv(
        default_broker=setting("BROKER_DEFAULT", "stub").lower(),
        gateway_url=setting("BROKER_GATEWAY_URL", "").strip().rstrip("/"),
        gateway_secret=setting("BROKER_GATEWAY_SECRET", ""),
        static_ip_note=setting("BROKER_STATIC_IP", "").strip(),
        deployment_mode=setting("BROKER_DEPLOYMENT_MODE", "local").lower(),
        zerodha_api_key=setting("ZERODHA_API_KEY", ""),
        zerodha_api_secret=setting("ZERODHA_API_SECRET", ""),
        zerodha_access_token=setting("ZERODHA_ACCESS_TOKEN", ""),
        groww_api_key=setting("GROWW_API_KEY", ""),
        groww_api_secret=setting("GROWW_API_SECRET", ""),
        groww_access_token=setting("GROWW_ACCESS_TOKEN", ""),
        fyers_app_id=setting("FYERS_APP_ID", ""),
        fyers_secret=setting("FYERS_SECRET", ""),
        fyers_access_token=setting("FYERS_ACCESS_TOKEN", ""),
    )


SUPPORTED_BROKERS = ("stub", "zerodha", "groww", "fyers")

BROKER_LABELS = {
    "stub": "Stub (local queue)",
    "zerodha": "Zerodha Kite Connect",
    "groww": "Groww Trade API",
    "fyers": "FYERS API v3",
}

BROKER_STATIC_IP_REQUIRED = {
    "zerodha": False,  # OAuth redirect; API from any IP once token obtained (check current Kite docs)
    "groww": True,
    "fyers": False,  # OAuth; verify current FYERS policy
}
