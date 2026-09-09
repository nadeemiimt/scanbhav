"""Persist broker access tokens (gitignored data file + env override)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from config import BASE_DIR

TOKENS_PATH = BASE_DIR / "data" / "broker_tokens.json"


def _load_all() -> dict[str, Any]:
    if not TOKENS_PATH.exists():
        return {}
    try:
        return json.loads(TOKENS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_all(data: dict[str, Any]) -> None:
    TOKENS_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKENS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_stored_token(broker: str) -> Optional[str]:
    row = _load_all().get(broker.lower()) or {}
    token = row.get("access_token")
    return str(token) if token else None


def save_token(broker: str, access_token: str, **extra: Any) -> dict[str, Any]:
    from datetime import timedelta

    data = _load_all()
    expires = extra.get("expires_at")
    if not expires and broker.lower() in {"zerodha", "fyers"}:
        ist = timezone(timedelta(hours=5, minutes=30))
        tomorrow = datetime.now(ist).replace(hour=6, minute=0, second=0, microsecond=0) + timedelta(days=1)
        expires = tomorrow.astimezone(timezone.utc).isoformat()
    data[broker.lower()] = {
        "access_token": access_token,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": expires,
        **extra,
    }
    _save_all(data)
    return data[broker.lower()]


def token_meta(broker: str) -> dict[str, Any]:
    row = _load_all().get(broker.lower()) or {}
    if not row:
        return {}
    return {
        "has_token": bool(row.get("access_token")),
        "updated_at": row.get("updated_at"),
        "expires_at": row.get("expires_at"),
        "user_id": row.get("user_id"),
    }


def token_health(broker: str) -> dict[str, Any]:
    """Pre-market token validation — Zerodha/FYERS tokens expire daily ~6 AM IST."""
    from datetime import datetime, timedelta, timezone

    meta = token_meta(broker)
    if not meta.get("has_token"):
        return {"ok": False, "reason": "no_token", "broker": broker}

    updated = meta.get("updated_at")
    expires_at = meta.get("expires_at")
    now = datetime.now(timezone.utc)
    ist = timezone(timedelta(hours=5, minutes=30))
    today_ist = datetime.now(ist).date()

    if expires_at:
        try:
            exp = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            if now >= exp:
                return {"ok": False, "reason": "token_expired", "expires_at": expires_at, "broker": broker}
        except Exception:
            pass

    if updated:
        try:
            upd = datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
            upd_ist_date = upd.astimezone(ist).date()
            if broker.lower() in {"zerodha", "fyers"} and upd_ist_date < today_ist:
                return {
                    "ok": False,
                    "reason": "token_stale_daily_oauth",
                    "updated_at": updated,
                    "broker": broker,
                    "message": "Complete OAuth again — Kite/FYERS tokens expire daily.",
                }
        except Exception:
            pass

    return {"ok": True, "broker": broker, **meta}
