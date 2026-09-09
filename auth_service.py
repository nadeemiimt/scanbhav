"""OAuth2 login helpers and JWT session tokens."""
from __future__ import annotations

import secrets
import time
from typing import Any, Optional
from urllib.parse import urlencode

import jwt
import requests

from config import setting
from utils.logging_config import get_logger

logger = get_logger(__name__)

AUTH_JWT_SECRET = setting("AUTH_JWT_SECRET", "dev-change-me-scan-bhav")
AUTH_JWT_TTL_SECONDS = int(setting("AUTH_JWT_TTL_SECONDS", str(7 * 24 * 3600)))
FRONTEND_URL = setting("FRONTEND_URL", "http://localhost:5173").rstrip("/")
AUTH_CALLBACK_BASE = setting("AUTH_CALLBACK_BASE", "http://127.0.0.1:8000").rstrip("/")
AUTH_ALLOW_DEV = setting("AUTH_ALLOW_DEV", "true").lower() in ("1", "true", "yes")

# Ephemeral OAuth state (process-local; fine for single-user local desk).
_PENDING_STATE: dict[str, tuple[str, float]] = {}
_STATE_TTL = 600


def _provider_defs() -> dict[str, dict[str, Any]]:
    return {
        "google": {
            "label": "Google",
            "icon": "google",
            "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
            "scopes": ["openid", "email", "profile"],
            "client_id": setting("GOOGLE_CLIENT_ID", ""),
            "client_secret": setting("GOOGLE_CLIENT_SECRET", ""),
        },
        "yahoo": {
            "label": "Yahoo",
            "icon": "yahoo",
            "authorize_url": "https://api.login.yahoo.com/oauth2/request_auth",
            "token_url": "https://api.login.yahoo.com/oauth2/get_token",
            "userinfo_url": "https://api.login.yahoo.com/openid/v1/userinfo",
            "scopes": ["openid", "email", "profile"],
            "client_id": setting("YAHOO_CLIENT_ID", ""),
            "client_secret": setting("YAHOO_CLIENT_SECRET", ""),
        },
        "github": {
            "label": "GitHub",
            "icon": "github",
            "authorize_url": "https://github.com/login/oauth/authorize",
            "token_url": "https://github.com/login/oauth/access_token",
            "userinfo_url": "https://api.github.com/user",
            "email_url": "https://api.github.com/user/emails",
            "scopes": ["read:user", "user:email"],
            "client_id": setting("GITHUB_CLIENT_ID", ""),
            "client_secret": setting("GITHUB_CLIENT_SECRET", ""),
        },
        "microsoft": {
            "label": "Microsoft",
            "icon": "microsoft",
            "authorize_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
            "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            "userinfo_url": "https://graph.microsoft.com/v1.0/me",
            "scopes": ["openid", "profile", "email", "User.Read"],
            "client_id": setting("MICROSOFT_CLIENT_ID", ""),
            "client_secret": setting("MICROSOFT_CLIENT_SECRET", ""),
        },
    }


def list_providers() -> list[dict[str, Any]]:
    out = []
    for pid, cfg in _provider_defs().items():
        configured = bool(cfg.get("client_id") and cfg.get("client_secret"))
        out.append({
            "id": pid,
            "label": cfg["label"],
            "icon": cfg.get("icon", pid),
            "configured": configured,
        })
    return out


def provider_configured(provider_id: str) -> bool:
    cfg = _provider_defs().get(provider_id)
    return bool(cfg and cfg.get("client_id") and cfg.get("client_secret"))


def _purge_state() -> None:
    now = time.time()
    stale = [k for k, (_, exp) in _PENDING_STATE.items() if exp < now]
    for k in stale:
        _PENDING_STATE.pop(k, None)


def create_oauth_state(provider_id: str) -> str:
    _purge_state()
    state = secrets.token_urlsafe(24)
    _PENDING_STATE[state] = (provider_id, time.time() + _STATE_TTL)
    return state


def pop_oauth_state(state: str) -> Optional[str]:
    _purge_state()
    entry = _PENDING_STATE.pop(state, None)
    return entry[0] if entry else None


def build_authorize_url(provider_id: str) -> str:
    cfg = _provider_defs()[provider_id]
    state = create_oauth_state(provider_id)
    redirect_uri = f"{AUTH_CALLBACK_BASE}/api/auth/callback/{provider_id}"
    params = {
        "client_id": cfg["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(cfg["scopes"]),
        "state": state,
    }
    if provider_id == "google":
        params["access_type"] = "online"
        params["prompt"] = "select_account"
    return f"{cfg['authorize_url']}?{urlencode(params)}"


def _exchange_code(provider_id: str, code: str) -> dict[str, Any]:
    cfg = _provider_defs()[provider_id]
    redirect_uri = f"{AUTH_CALLBACK_BASE}/api/auth/callback/{provider_id}"
    data = {
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    headers = {"Accept": "application/json"}
    if provider_id == "github":
        headers["Accept"] = "application/json"
    resp = requests.post(cfg["token_url"], data=data, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _fetch_user(provider_id: str, token_payload: dict[str, Any]) -> dict[str, Any]:
    cfg = _provider_defs()[provider_id]
    access = token_payload.get("access_token")
    if not access:
        raise ValueError("OAuth token response missing access_token")

    headers = {"Authorization": f"Bearer {access}", "Accept": "application/json"}
    if provider_id == "github":
        headers["Accept"] = "application/vnd.github+json"

    resp = requests.get(cfg["userinfo_url"], headers=headers, timeout=20)
    resp.raise_for_status()
    raw = resp.json()

    if provider_id == "google":
        return {
            "sub": raw.get("sub") or raw.get("id"),
            "email": raw.get("email"),
            "name": raw.get("name") or raw.get("email"),
            "picture": raw.get("picture"),
        }
    if provider_id == "yahoo":
        return {
            "sub": raw.get("sub"),
            "email": raw.get("email"),
            "name": raw.get("name") or raw.get("nickname") or raw.get("email"),
            "picture": raw.get("picture"),
        }
    if provider_id == "github":
        email = raw.get("email")
        if not email and cfg.get("email_url"):
            er = requests.get(cfg["email_url"], headers=headers, timeout=20)
            if er.ok:
                emails = er.json()
                primary = next((e for e in emails if e.get("primary")), None)
                email = (primary or (emails[0] if emails else {})).get("email")
        return {
            "sub": str(raw.get("id")),
            "email": email,
            "name": raw.get("name") or raw.get("login"),
            "picture": raw.get("avatar_url"),
        }
    if provider_id == "microsoft":
        return {
            "sub": raw.get("id"),
            "email": raw.get("mail") or raw.get("userPrincipalName"),
            "name": raw.get("displayName"),
            "picture": None,
        }
    raise ValueError(f"Unknown provider {provider_id}")


def complete_oauth(provider_id: str, code: str) -> dict[str, Any]:
    tokens = _exchange_code(provider_id, code)
    profile = _fetch_user(provider_id, tokens)
    if not profile.get("email"):
        raise ValueError(f"{provider_id} did not return an email address")
    user = {
        "id": f"{provider_id}:{profile['sub']}",
        "provider": provider_id,
        "email": profile["email"].lower(),
        "name": profile.get("name") or profile["email"],
        "picture": profile.get("picture"),
    }
    user["token"] = create_access_token(user)
    return user


def create_access_token(user: dict[str, Any]) -> str:
    now = int(time.time())
    payload = {
        "sub": user["id"],
        "email": user["email"],
        "name": user.get("name"),
        "picture": user.get("picture"),
        "provider": user.get("provider", "dev"),
        "iat": now,
        "exp": now + AUTH_JWT_TTL_SECONDS,
    }
    return jwt.encode(payload, AUTH_JWT_SECRET, algorithm="HS256")


def decode_access_token(token: str) -> Optional[dict[str, Any]]:
    try:
        return jwt.decode(token, AUTH_JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        logger.debug("Invalid auth token: %s", exc)
        return None


def user_from_claims(claims: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": claims.get("sub"),
        "email": claims.get("email"),
        "name": claims.get("name"),
        "picture": claims.get("picture"),
        "provider": claims.get("provider"),
    }


def dev_login(email: str, name: str = "") -> dict[str, Any]:
    if not AUTH_ALLOW_DEV:
        raise PermissionError("Dev login disabled")
    email = email.strip().lower()
    if "@" not in email:
        raise ValueError("Valid email required")
    user = {
        "id": f"dev:{email}",
        "provider": "dev",
        "email": email,
        "name": name.strip() or email.split("@")[0],
        "picture": None,
    }
    user["token"] = create_access_token(user)
    return user
