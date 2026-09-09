"""Persist Finnhub inbound webhook events locally."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import BASE_DIR

EVENTS_DIR = BASE_DIR / "data" / "finnhub"
EVENTS_PATH = EVENTS_DIR / "webhook_events.jsonl"
MAX_EVENTS = 500


def append_event(payload: dict[str, Any]) -> None:
    EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    row = {
        "received_at": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }
    with EVENTS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    _trim_events()


def _trim_events() -> None:
    if not EVENTS_PATH.exists():
        return
    lines = EVENTS_PATH.read_text(encoding="utf-8").splitlines()
    if len(lines) <= MAX_EVENTS:
        return
    trimmed = lines[-MAX_EVENTS:]
    EVENTS_PATH.write_text("\n".join(trimmed) + "\n", encoding="utf-8")


def recent_events(limit: int = 20) -> list[dict[str, Any]]:
    if not EVENTS_PATH.exists():
        return []
    lines = EVENTS_PATH.read_text(encoding="utf-8").splitlines()
    out: list[dict[str, Any]] = []
    for line in reversed(lines[-limit:]):
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
