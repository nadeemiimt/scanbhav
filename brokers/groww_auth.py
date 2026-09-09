"""Groww access-token resolution for data APIs (no order placement)."""
from __future__ import annotations

from typing import Optional

from brokers.config import load_broker_env
from brokers.sdk_loader import sdk_available
from brokers.token_store import get_stored_token, save_token

_cached_token: Optional[str] = None


def groww_credentials_configured() -> bool:
    """True when Groww API key+secret or an access token is available."""
    env = load_broker_env()
    if env.groww_access_token or get_stored_token("groww"):
        return True
    return bool(env.groww_api_key and env.groww_api_secret)


def groww_data_available() -> bool:
    return groww_credentials_configured() and sdk_available("groww")


def resolve_groww_access_token(*, force_refresh: bool = False) -> str:
    """Return a Groww access token, minting one from API key+secret when needed."""
    global _cached_token

    env = load_broker_env()
    if not force_refresh:
        if env.groww_access_token:
            return env.groww_access_token
        stored = get_stored_token("groww")
        if stored:
            return stored
        if _cached_token:
            return _cached_token

    if env.groww_api_key and env.groww_api_secret:
        from growwapi import GrowwAPI

        token = GrowwAPI.get_access_token(
            api_key=env.groww_api_key,
            secret=env.groww_api_secret,
        )
        if isinstance(token, dict):
            token = str(token.get("token") or token.get("access_token") or "")
        token = str(token).strip()
        if not token:
            raise RuntimeError("Groww token exchange returned an empty access token.")
        save_token("groww", token)
        _cached_token = token
        return token

    return ""
