"""OAuth / login URL helpers for Zerodha Kite and FYERS."""
from __future__ import annotations

from typing import Any

from config import setting
from brokers.sdk_loader import fyers_session, kite_connect
from brokers.token_store import save_token


def kite_login_url() -> dict[str, Any]:
    api_key = setting("ZERODHA_API_KEY", "")
    if not api_key:
        raise RuntimeError("Set ZERODHA_API_KEY in .env first.")
    kite = kite_connect(api_key)
    return {
        "broker": "zerodha",
        "login_url": kite.login_url(),
        "redirect_hint": setting("KITE_REDIRECT_URL", f"{setting('AUTH_CALLBACK_BASE', 'http://127.0.0.1:8000')}/api/broker/auth/zerodha/callback"),
    }


def kite_exchange_token(request_token: str) -> dict[str, Any]:
    api_key = setting("ZERODHA_API_KEY", "")
    api_secret = setting("ZERODHA_API_SECRET", "")
    if not api_key or not api_secret:
        raise RuntimeError("Set ZERODHA_API_KEY and ZERODHA_API_SECRET in .env.")
    kite = kite_connect(api_key)
    session = kite.generate_session(request_token, api_secret=api_secret)
    access_token = session["access_token"]
    save_token("zerodha", access_token, user_id=session.get("user_id"))
    return {
        "broker": "zerodha",
        "access_token_set": True,
        "user_id": session.get("user_id"),
        "message": "Kite session saved. Set ZERODHA_ACCESS_TOKEN or rely on data/broker_tokens.json.",
    }


def fyers_login_url() -> dict[str, Any]:
    app_id = setting("FYERS_APP_ID", "")
    secret = setting("FYERS_SECRET", "")
    redirect_uri = setting("FYERS_REDIRECT_URI", f"{setting('AUTH_CALLBACK_BASE', 'http://127.0.0.1:8000')}/api/broker/auth/fyers/callback")
    if not app_id or not secret:
        raise RuntimeError("Set FYERS_APP_ID and FYERS_SECRET in .env first.")
    session = fyers_session(
        client_id=app_id,
        secret_key=secret,
        redirect_uri=redirect_uri,
        response_type="code",
        grant_type="authorization_code",
        state="scanbhav",
    )
    return {
        "broker": "fyers",
        "login_url": session.generate_authcode(),
        "redirect_uri": redirect_uri,
    }


def fyers_exchange_token(auth_code: str) -> dict[str, Any]:
    app_id = setting("FYERS_APP_ID", "")
    secret = setting("FYERS_SECRET", "")
    redirect_uri = setting("FYERS_REDIRECT_URI", f"{setting('AUTH_CALLBACK_BASE', 'http://127.0.0.1:8000')}/api/broker/auth/fyers/callback")
    if not app_id or not secret:
        raise RuntimeError("Set FYERS_APP_ID and FYERS_SECRET in .env.")
    session = fyers_session(
        client_id=app_id,
        secret_key=secret,
        redirect_uri=redirect_uri,
        response_type="code",
        grant_type="authorization_code",
        state="scanbhav",
    )
    session.set_token(auth_code)
    response = session.generate_token()
    if response.get("s") != "ok":
        raise RuntimeError(response.get("message") or str(response))
    access_token = response["access_token"]
    save_token("fyers", access_token)
    return {
        "broker": "fyers",
        "access_token_set": True,
        "message": "FYERS session saved to data/broker_tokens.json.",
    }


def groww_set_token(access_token: str) -> dict[str, Any]:
    if not access_token.strip():
        raise RuntimeError("Groww access token is empty.")
    save_token("groww", access_token.strip())
    return {
        "broker": "groww",
        "access_token_set": True,
        "message": "Groww token saved. Generate from Groww Trade API dashboard.",
    }
