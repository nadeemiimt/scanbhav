"""Pending live orders — broker order_id until fill confirmed."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from config import BASE_DIR

BOOK_PATH = BASE_DIR / "data" / "trading" / "order_book.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> dict[str, Any]:
    BOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not BOOK_PATH.exists():
        return {"pending": [], "events": []}
    try:
        return json.loads(BOOK_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"pending": [], "events": []}


def _save(data: dict[str, Any]) -> None:
    BOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    BOOK_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def record_pending(
    *,
    broker_order_id: str,
    payload: dict[str, Any],
    estimated_price: float,
    source: str,
) -> dict[str, Any]:
    data = _load()
    row = {
        "id": str(uuid.uuid4()),
        "broker_order_id": str(broker_order_id),
        "status": "pending",
        "payload": payload,
        "estimated_price": round(float(estimated_price), 4),
        "source": source,
        "created_at": _now(),
        "updated_at": _now(),
    }
    data.setdefault("pending", []).append(row)
    _save(data)
    return row


def list_pending() -> list[dict[str, Any]]:
    return [p for p in (_load().get("pending") or []) if p.get("status") == "pending"]


def update_pending(broker_order_id: str, **fields: Any) -> Optional[dict[str, Any]]:
    data = _load()
    for row in data.get("pending") or []:
        if str(row.get("broker_order_id")) == str(broker_order_id):
            row.update(fields)
            row["updated_at"] = _now()
            _save(data)
            return row
    return None


def append_event(event: dict[str, Any]) -> None:
    data = _load()
    events = data.setdefault("events", [])
    events.append({**event, "ts": _now()})
    data["events"] = events[-500:]
    _save(data)


def recent_events(limit: int = 30) -> list[dict[str, Any]]:
    return list(reversed((_load().get("events") or [])[-limit:]))
