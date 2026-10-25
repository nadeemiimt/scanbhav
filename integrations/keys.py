"""Per-install API keys saved from the UI. Values are never returned in full."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import BASE_DIR

STORE = BASE_DIR / "data" / "user_secrets.json"


def _load() -> dict[str, Any]:
    if not STORE.exists():
        return {"keys": {}, "connectors": {}}
    try:
        data = json.loads(STORE.read_text(encoding="utf-8"))
    except Exception:
        return {"keys": {}, "connectors": {}}
    data.setdefault("keys", {})
    data.setdefault("connectors", {})
    return data


def _save(data: dict[str, Any]) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def mask_secret(value: str) -> str:
    raw = str(value or "")
    if not raw:
        return ""
    if len(raw) <= 4:
        return "••••"
    return f"••••{raw[-4:]}"


def get_secret(provider_id: str) -> str:
    return str((_load().get("keys") or {}).get(provider_id) or "").strip()


def set_secret(provider_id: str, api_key: str) -> dict[str, Any]:
    data = _load()
    key = str(api_key or "").strip()
    if key:
        data["keys"][provider_id] = key
    else:
        data["keys"].pop(provider_id, None)
    _save(data)
    return {"id": provider_id, "configured": bool(key), "hint": mask_secret(key)}


def public_key_status() -> dict[str, Any]:
    keys = _load().get("keys") or {}
    return {
        pid: {"configured": True, "hint": mask_secret(str(val))}
        for pid, val in keys.items()
        if str(val or "").strip()
    }


def get_connector(connector_id: str) -> dict[str, Any]:
    row = (_load().get("connectors") or {}).get(connector_id) or {}
    return dict(row)


def list_connectors() -> list[dict[str, Any]]:
    out = []
    for cid, row in (_load().get("connectors") or {}).items():
        item = dict(row)
        item["id"] = cid
        if item.get("api_key"):
            item["hint"] = mask_secret(str(item.get("api_key")))
            item["configured"] = True
            item.pop("api_key", None)
        out.append(item)
    return out


def save_connector(connector_id: str, body: dict[str, Any]) -> dict[str, Any]:
    data = _load()
    prev = dict((data.get("connectors") or {}).get(connector_id) or {})
    key = str(body.get("api_key") or "").strip()
    row = {
        "label": str(body.get("label") or prev.get("label") or connector_id),
        "base_url": str(body.get("base_url") or prev.get("base_url") or "").rstrip("/"),
        "path_template": str(body.get("path_template") or prev.get("path_template") or "/quote?symbol={symbol}"),
        "header_name": str(body.get("header_name") or prev.get("header_name") or "Authorization"),
        "header_prefix": str(body.get("header_prefix") or prev.get("header_prefix") or "Bearer"),
        "api_key": key or prev.get("api_key") or "",
    }
    if body.get("clear_key"):
        row["api_key"] = ""
    data.setdefault("connectors", {})[connector_id] = row
    _save(data)
    public = dict(row)
    public.pop("api_key", None)
    public["id"] = connector_id
    public["configured"] = bool(row.get("api_key"))
    public["hint"] = mask_secret(str(row.get("api_key") or ""))
    return public
