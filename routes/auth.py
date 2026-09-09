"""OAuth login routes — Google, Yahoo, GitHub, Microsoft."""
from __future__ import annotations

from typing import Any, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from auth_service import (
    AUTH_ALLOW_DEV,
    FRONTEND_URL,
    build_authorize_url,
    complete_oauth,
    decode_access_token,
    dev_login,
    list_providers,
    pop_oauth_state,
    provider_configured,
    user_from_claims,
)
from utils.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["auth"])


class DevLoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    name: str = Field(default="", max_length=120)


def _bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def _redirect_with_token(token: str) -> RedirectResponse:
    # Hash fragment keeps token off server logs; SPA reads it on load.
    url = f"{FRONTEND_URL}/#auth_token={token}"
    return RedirectResponse(url=url, status_code=302)


@router.get("/api/auth/providers")
def auth_providers() -> dict[str, Any]:
    providers = list_providers()
    return {
        "providers": providers,
        "dev_login_enabled": AUTH_ALLOW_DEV,
        "any_configured": any(p["configured"] for p in providers),
    }


@router.get("/api/auth/me")
def auth_me(authorization: Optional[str] = Header(default=None)) -> dict[str, Any]:
    token = _bearer_token(authorization)
    if not token:
        return {"authenticated": False, "user": None}
    claims = decode_access_token(token)
    if not claims:
        return {"authenticated": False, "user": None}
    return {"authenticated": True, "user": user_from_claims(claims)}


@router.get("/api/auth/login/{provider_id}")
def auth_login(provider_id: str) -> RedirectResponse:
    if not provider_configured(provider_id):
        raise HTTPException(
            status_code=503,
            detail=f"Provider '{provider_id}' is not configured. Add client id/secret to .env",
        )
    try:
        url = build_authorize_url(provider_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown provider") from exc
    return RedirectResponse(url=url, status_code=302)


@router.get("/api/auth/callback/{provider_id}")
def auth_callback(
    provider_id: str,
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
) -> RedirectResponse:
    if error:
        q = urlencode({"auth_error": error})
        return RedirectResponse(url=f"{FRONTEND_URL}/?{q}", status_code=302)
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing OAuth code or state")
    expected = pop_oauth_state(state)
    if expected != provider_id:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")
    try:
        user = complete_oauth(provider_id, code)
    except Exception as exc:
        logger.warning("OAuth callback failed for %s: %s", provider_id, exc)
        q = urlencode({"auth_error": str(exc)})
        return RedirectResponse(url=f"{FRONTEND_URL}/?{q}", status_code=302)
    return _redirect_with_token(user["token"])


@router.post("/api/auth/dev-login")
def auth_dev_login(body: DevLoginRequest) -> dict[str, Any]:
    try:
        user = dev_login(body.email, body.name)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"user": {k: v for k, v in user.items() if k != "token"}, "token": user["token"]}
