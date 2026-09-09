"""Persist partial screener progress so interrupted runs can resume."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from config import BASE_DIR

CHECKPOINT_PATH = BASE_DIR / "data" / "screen_cache" / "checkpoint.json"
META_PATH = BASE_DIR / "data" / "screen_cache" / "checkpoint_meta.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slim_checkpoint_result(row: dict[str, Any]) -> dict[str, Any]:
    """Drop bulky bars/technicals/extended — ratings are enough to resume ranking."""
    return {
        "symbol": row.get("symbol"),
        "bucket": row.get("bucket"),
        "price": row.get("price"),
        "as_of": row.get("as_of"),
        "ratings": row.get("ratings"),
    }


def _meta_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    req = payload.get("request") or {}
    scored = int(payload.get("scored") or len(payload.get("results") or []))
    total = int(payload.get("universe_size") or req.get("limit") or 500)
    return {
        "available": scored > 0 and scored < total,
        "scored": scored,
        "failed": int(payload.get("failed") or len(payload.get("errors") or [])),
        "universe_size": total,
        "started_at": payload.get("started_at"),
        "updated_at": payload.get("updated_at"),
        "horizon": req.get("horizon"),
        "request": req,
    }


def _write_meta(payload: dict[str, Any]) -> None:
    META_PATH.parent.mkdir(parents=True, exist_ok=True)
    META_PATH.write_text(
        json.dumps(_meta_from_payload(payload), separators=(",", ":")),
        encoding="utf-8",
    )


def load_checkpoint_meta() -> Optional[dict[str, Any]]:
    if not META_PATH.exists():
        return None
    try:
        return json.loads(META_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_checkpoint() -> Optional[dict[str, Any]]:
    if not CHECKPOINT_PATH.exists():
        return None
    try:
        return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def clear_checkpoint() -> None:
    if CHECKPOINT_PATH.exists():
        CHECKPOINT_PATH.unlink(missing_ok=True)
    if META_PATH.exists():
        META_PATH.unlink(missing_ok=True)


def save_checkpoint(
    *,
    request: dict[str, Any],
    results: list[dict[str, Any]],
    error_map: dict[str, str],
    universe_size: int,
    started_at: str,
) -> None:
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    slim_results = [_slim_checkpoint_result(r) for r in results]
    payload = {
        "version": 2,
        "started_at": started_at,
        "updated_at": _now(),
        "request": request,
        "universe_size": universe_size,
        "scored": len(slim_results),
        "failed": len(error_map),
        "results": slim_results,
        "errors": [{"symbol": sym, "error": msg} for sym, msg in error_map.items()],
    }
    CHECKPOINT_PATH.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    _write_meta(payload)


def slim_existing_checkpoint() -> dict[str, Any]:
    """One-shot maintenance: strip bulky fields and refresh meta (safe to call repeatedly)."""
    ck = load_checkpoint()
    if not ck:
        if META_PATH.exists():
            META_PATH.unlink(missing_ok=True)
        return {"slimmed": False, "reason": "no_checkpoint"}
    before = CHECKPOINT_PATH.stat().st_size if CHECKPOINT_PATH.exists() else 0
    slim_results = [_slim_checkpoint_result(r) for r in (ck.get("results") or [])]
    ck["version"] = 2
    ck["results"] = slim_results
    ck["scored"] = len(slim_results)
    ck["updated_at"] = _now()
    CHECKPOINT_PATH.write_text(json.dumps(ck, separators=(",", ":")), encoding="utf-8")
    _write_meta(ck)
    after = CHECKPOINT_PATH.stat().st_size
    return {
        "slimmed": True,
        "scored": len(slim_results),
        "bytes_before": before,
        "bytes_after": after,
    }


def ensure_checkpoint_meta() -> Optional[dict[str, Any]]:
    meta = load_checkpoint_meta()
    if meta is not None:
        return meta
    if not CHECKPOINT_PATH.exists():
        return None
    slim_existing_checkpoint()
    return load_checkpoint_meta()


def checkpoint_summary() -> dict[str, Any]:
    meta = load_checkpoint_meta()
    if meta is None:
        meta = ensure_checkpoint_meta()
    if not meta:
        return {"available": False}
    return dict(meta)


def checkpoint_request_matches(request: dict[str, Any], ck: dict[str, Any]) -> bool:
    saved = ck.get("request") or {}
    keys = ("limit", "horizon", "bucket", "provider", "batch_strategy")
    return all(saved.get(k) == request.get(k) for k in keys)
