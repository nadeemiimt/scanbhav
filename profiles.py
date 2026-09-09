"""Email-validated multi-profile portfolio storage for the Personal Advisor."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from config import BASE_DIR

PROFILES_DIR = BASE_DIR / "data" / "profiles"
EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$")


def normalize_email(email: str) -> str:
    cleaned = (email or "").strip().lower()
    if not cleaned or len(cleaned) > 254 or not EMAIL_RE.match(cleaned):
        raise ValueError("Enter a valid email address (e.g. you@example.com).")
    local, _, domain = cleaned.partition("@")
    if not local or not domain or "." not in domain:
        raise ValueError("Enter a valid email address (e.g. you@example.com).")
    return cleaned


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _email_dir(email: str) -> Path:
    safe = re.sub(r"[^a-z0-9._@+-]", "_", normalize_email(email))
    path = PROFILES_DIR / safe
    path.mkdir(parents=True, exist_ok=True)
    return path


def _index_path(email: str) -> Path:
    return _email_dir(email) / "index.json"


def _profile_path(email: str, profile_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9-]{36}", profile_id):
        raise ValueError("Invalid profile id.")
    return _email_dir(email) / f"{profile_id}.json"


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def list_profiles(email: str) -> list[dict[str, Any]]:
    email = normalize_email(email)
    index = _read_json(_index_path(email), {"email": email, "profiles": []})
    return index.get("profiles") or []


def create_profile(email: str, name: str, risk_tolerance: str = "moderate") -> dict[str, Any]:
    email = normalize_email(email)
    label = (name or "").strip() or "My portfolio"
    if len(label) > 80:
        raise ValueError("Profile name must be 80 characters or fewer.")
    risk = (risk_tolerance or "moderate").strip().lower()
    if risk not in {"conservative", "moderate", "aggressive"}:
        raise ValueError("risk_tolerance must be conservative, moderate, or aggressive.")

    profile_id = str(uuid.uuid4())
    profile = {
        "id": profile_id,
        "email": email,
        "name": label,
        "risk_tolerance": risk,
        "created_at": _now(),
        "updated_at": _now(),
        "holdings": [],
        "ingest_log": [],
        "last_advice": None,
    }
    _write_json(_profile_path(email, profile_id), profile)

    index = _read_json(_index_path(email), {"email": email, "profiles": []})
    index["profiles"] = [
        item for item in (index.get("profiles") or []) if item.get("id") != profile_id
    ]
    index["profiles"].append({
        "id": profile_id,
        "name": label,
        "risk_tolerance": risk,
        "created_at": profile["created_at"],
        "updated_at": profile["updated_at"],
        "holding_count": 0,
    })
    index["email"] = email
    _write_json(_index_path(email), index)
    return profile


def get_profile(email: str, profile_id: str) -> dict[str, Any]:
    email = normalize_email(email)
    path = _profile_path(email, profile_id)
    if not path.exists():
        raise FileNotFoundError(f"No profile {profile_id} for {email}.")
    profile = _read_json(path, None)
    if not profile or profile.get("email") != email:
        raise FileNotFoundError(f"No profile {profile_id} for {email}.")
    return profile


def save_profile(profile: dict[str, Any]) -> dict[str, Any]:
    email = normalize_email(profile["email"])
    profile_id = profile["id"]
    profile["updated_at"] = _now()
    _write_json(_profile_path(email, profile_id), profile)

    index = _read_json(_index_path(email), {"email": email, "profiles": []})
    summaries = []
    found = False
    for item in index.get("profiles") or []:
        if item.get("id") == profile_id:
            summaries.append({
                "id": profile_id,
                "name": profile.get("name"),
                "risk_tolerance": profile.get("risk_tolerance"),
                "created_at": profile.get("created_at"),
                "updated_at": profile["updated_at"],
                "holding_count": len(profile.get("holdings") or []),
            })
            found = True
        else:
            summaries.append(item)
    if not found:
        summaries.append({
            "id": profile_id,
            "name": profile.get("name"),
            "risk_tolerance": profile.get("risk_tolerance"),
            "created_at": profile.get("created_at"),
            "updated_at": profile["updated_at"],
            "holding_count": len(profile.get("holdings") or []),
        })
    index["profiles"] = summaries
    _write_json(_index_path(email), index)
    return profile


def delete_profile(email: str, profile_id: str) -> None:
    email = normalize_email(email)
    path = _profile_path(email, profile_id)
    if path.exists():
        path.unlink()
    index = _read_json(_index_path(email), {"email": email, "profiles": []})
    index["profiles"] = [item for item in (index.get("profiles") or []) if item.get("id") != profile_id]
    _write_json(_index_path(email), index)


def _holding_key(item: dict[str, Any]) -> str:
    asset_type = (item.get("asset_type") or "stock").strip().lower()
    symbol = (item.get("symbol") or item.get("name") or "").strip().upper()
    return f"{asset_type}:{symbol}"


def merge_holdings(profile: dict[str, Any], holdings: list[dict[str, Any]], source: str) -> dict[str, Any]:
    """Upsert holdings by asset_type+symbol/name; keep prior fields when new ones are blank."""
    existing = { _holding_key(item): item for item in (profile.get("holdings") or []) if _holding_key(item) != "stock:" }
    for raw in holdings:
        cleaned = normalize_holding(raw)
        if not cleaned:
            continue
        key = _holding_key(cleaned)
        prior = existing.get(key, {})
        merged = {**prior, **{k: v for k, v in cleaned.items() if v is not None and v != ""}}
        merged["updated_at"] = _now()
        existing[key] = merged

    profile["holdings"] = list(existing.values())
    log = profile.get("ingest_log") or []
    log.append({
        "at": _now(),
        "source": source,
        "count": len(holdings),
    })
    profile["ingest_log"] = log[-50:]
    return save_profile(profile)


def normalize_holding(raw: dict[str, Any]) -> Optional[dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    asset_type = str(raw.get("asset_type") or raw.get("type") or "stock").strip().lower()
    if asset_type in {"mf", "mutual fund", "mutual_funds", "fund"}:
        asset_type = "mutual_fund"
    if asset_type not in {"stock", "mutual_fund"}:
        asset_type = "stock"

    symbol = str(raw.get("symbol") or raw.get("ticker") or "").strip().upper() or None
    name = str(raw.get("name") or raw.get("scheme") or raw.get("fund_name") or "").strip() or None
    if not symbol and not name:
        return None

    def num(value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        text = str(value).replace(",", "").replace("₹", "").replace("%", "").strip()
        try:
            return float(text)
        except ValueError:
            return None

    return {
        "id": str(raw.get("id") or uuid.uuid4()),
        "asset_type": asset_type,
        "symbol": symbol,
        "name": name or symbol,
        "quantity": num(raw.get("quantity") or raw.get("units") or raw.get("shares")),
        "avg_cost": num(raw.get("avg_cost") or raw.get("average_cost") or raw.get("avg_price") or raw.get("nav_cost")),
        "invested_value": num(raw.get("invested_value") or raw.get("invested") or raw.get("cost_value")),
        "current_value": num(raw.get("current_value") or raw.get("market_value")),
        "current_price": num(raw.get("current_price") or raw.get("ltp") or raw.get("nav")),
        "currency": str(raw.get("currency") or "INR").upper(),
        "notes": str(raw.get("notes") or "").strip() or None,
    }
