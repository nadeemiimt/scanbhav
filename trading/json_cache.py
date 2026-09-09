"""In-memory JSON file cache — avoids re-parsing large trading stores every request."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_CACHE: dict[str, dict[str, Any]] = {}


def load_json_cached(path: Path, *, default: dict[str, Any] | None = None) -> dict[str, Any]:
    fallback = default if default is not None else {}
    path = Path(path)
    if not path.exists():
        return dict(fallback)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return dict(fallback)

    key = str(path.resolve())
    row = _CACHE.get(key)
    if row and row.get("mtime") == mtime and row.get("data") is not None:
        return row["data"]

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(fallback)

    if not isinstance(data, dict):
        data = dict(fallback)
    _CACHE[key] = {"mtime": mtime, "data": data}
    return data


def invalidate_json_cache(path: Path) -> None:
    key = str(Path(path).resolve())
    _CACHE.pop(key, None)


def clear_json_cache() -> None:
    _CACHE.clear()
