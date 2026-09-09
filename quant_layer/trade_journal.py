"""Agent 9 — trade journal: LLM conviction vs realized outcomes."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from config import BASE_DIR

JOURNAL_PATH = BASE_DIR / "data" / "quant_cache" / "trade_journal.json"


def _load() -> dict[str, Any]:
    if not JOURNAL_PATH.exists():
        return {"entries": []}
    try:
        return json.loads(JOURNAL_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"entries": []}


def _save(data: dict[str, Any]) -> None:
    JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    JOURNAL_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def log_signal(
    *,
    symbol: str,
    conviction_score: float,
    validation_score: float,
    triggers: list[str],
    rationale: str,
    session_id: Optional[str] = None,
    source: str = "quant_pipeline",
) -> dict[str, Any]:
    data = _load()
    entry = {
        "id": f"j-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{symbol[:8]}",
        "ts": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol.upper(),
        "conviction_score": conviction_score,
        "validation_score": validation_score,
        "triggers": triggers,
        "rationale": rationale[:500],
        "session_id": session_id,
        "source": source,
        "outcome_pnl_inr": None,
        "outcome": None,
    }
    data.setdefault("entries", []).append(entry)
    if len(data["entries"]) > 2000:
        data["entries"] = data["entries"][-2000:]
    _save(data)
    return entry


def record_outcome(symbol: str, *, pnl_inr: float, outcome: str, session_id: Optional[str] = None) -> int:
    data = _load()
    updated = 0
    sym = symbol.upper()
    for entry in reversed(data.get("entries") or []):
        if entry.get("outcome") is not None:
            continue
        if entry.get("symbol") != sym:
            continue
        if session_id and entry.get("session_id") not in (None, session_id):
            continue
        entry["outcome_pnl_inr"] = pnl_inr
        entry["outcome"] = outcome
        entry["closed_at"] = datetime.now(timezone.utc).isoformat()
        updated += 1
        break
    if updated:
        _save(data)
    return updated


def journal_stats(min_entries: int = 10) -> dict[str, Any]:
    data = _load()
    closed = [e for e in (data.get("entries") or []) if e.get("outcome") is not None]
    if len(closed) < min_entries:
        return {"n_closed": len(closed), "ready": False, "min_entries": min_entries}
    wins = [e for e in closed if float(e.get("outcome_pnl_inr") or 0) > 0]
    buckets: dict[str, list[float]] = {}
    for e in closed:
        bucket = "high" if float(e.get("conviction_score") or 0) >= 7 else (
            "mid" if float(e.get("conviction_score") or 0) >= 5 else "low"
        )
        buckets.setdefault(bucket, []).append(float(e.get("outcome_pnl_inr") or 0))
    calibration = {
        k: {"n": len(v), "avg_pnl": sum(v) / len(v) if v else 0, "win_rate": sum(1 for x in v if x > 0) / len(v)}
        for k, v in buckets.items()
    }
    return {
        "n_closed": len(closed),
        "ready": True,
        "win_rate": len(wins) / len(closed),
        "conviction_calibration": calibration,
    }
