"""Phase A — prediction scoreboard + Chroma lessons from closed paper trades."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from config import BASE_DIR
from genai_research import append_insight
from prediction_tracker import list_tracked

SCOREBOARD_PATH = BASE_DIR / "data" / "trading" / "scoreboard.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> dict[str, Any]:
    SCOREBOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not SCOREBOARD_PATH.exists():
        return {"records": [], "summary": {}, "updated_at": _now()}
    try:
        return json.loads(SCOREBOARD_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"records": [], "summary": {}, "updated_at": _now()}


def _save(data: dict[str, Any]) -> dict[str, Any]:
    data["updated_at"] = _now()
    SCOREBOARD_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def _lesson_from_outcome(record: dict[str, Any]) -> dict[str, Any]:
    sym = record.get("symbol", "")
    acc = record.get("accuracy") or {}
    return {
        "stance": record.get("predicted_stance") or "neutral",
        "executive_summary": record.get("lesson_text")
        or (
            f"Scoreboard outcome {sym}: predicted {record.get('predicted_stance')} "
            f"({record.get('predicted_horizon')}) — label={acc.get('label')}, "
            f"return={record.get('return_pct')}%, source={record.get('source')}."
        ),
        "key_bull_points": [],
        "key_bear_points": [],
        "technical_read": record.get("summary") or "",
        "fundamental_read": "",
        "news_catalyst_read": "",
        "macro_risks": [],
        "what_changed_vs_prior": "Auto scoreboard lesson from closed paper/prediction trade.",
        "questions_to_monitor": [],
        "prediction_feedback": record,
        "not_advice_disclaimer": "Educational scoreboard memory — not investment advice.",
    }


def append_chroma_lesson(record: dict[str, Any]) -> dict[str, Any]:
    if record.get("rag_saved"):
        return {"skipped": True, "rag_id": record.get("rag_id")}
    stored = append_insight(
        symbol=str(record.get("symbol") or "UNKNOWN"),
        insight=_lesson_from_outcome(record),
        provider="scoreboard",
        model="auto_lesson",
        as_of=record.get("closed_at") or _now(),
    )
    record["rag_saved"] = True
    record["rag_id"] = stored.get("id")
    return stored


def record_outcome(
    *,
    symbol: str,
    source: str,
    predicted_stance: str,
    predicted_horizon: str = "1d",
    entry_price: float,
    exit_price: float,
    summary: str = "",
    composite_score: Optional[float] = None,
    auto_chroma: bool = True,
) -> dict[str, Any]:
    entry = float(entry_price)
    exit_p = float(exit_price)
    ret = ((exit_p / entry) - 1) * 100 if entry else 0.0
    from prediction_tracker import _score_accuracy

    accuracy = _score_accuracy(predicted_stance, ret)
    record = {
        "id": f"sb-{symbol}-{int(datetime.now(timezone.utc).timestamp())}",
        "symbol": symbol.upper(),
        "source": source,
        "predicted_stance": predicted_stance,
        "predicted_horizon": predicted_horizon,
        "entry_price": round(entry, 4),
        "exit_price": round(exit_p, 4),
        "return_pct": round(ret, 3),
        "accuracy": accuracy,
        "composite_score": composite_score,
        "summary": summary[:500],
        "closed_at": _now(),
        "rag_saved": False,
    }
    record["lesson_text"] = (
        f"Paper trade closed {symbol}: {predicted_stance} call returned {ret:.2f}% "
        f"({accuracy.get('label')}). Entry {entry} → exit {exit_p}."
    )
    data = _load()
    data.setdefault("records", []).insert(0, record)
    data["records"] = data["records"][:500]
    if auto_chroma:
        append_chroma_lesson(record)
    data["summary"] = compute_summary()
    _save(data)
    return record


def sync_from_predictions() -> dict[str, Any]:
    """Import rated predictions into scoreboard if not already present."""
    track = list_tracked()
    data = _load()
    existing_ids = {r.get("prediction_id") for r in data.get("records") or []}
    added = 0
    for item in track.get("items") or []:
        if item.get("status") != "rated" or item.get("id") in existing_ids:
            continue
        record_outcome(
            symbol=item["symbol"],
            source="prediction_tracker",
            predicted_stance=item.get("predicted_stance") or "neutral",
            predicted_horizon=item.get("predicted_horizon") or "1m",
            entry_price=float(item.get("entry_price") or 0),
            exit_price=float(item.get("latest_price") or item.get("entry_price") or 0),
            summary=item.get("summary") or "",
            composite_score=item.get("composite_score"),
            auto_chroma=not item.get("rag_saved"),
        )
        added += 1
    return {"imported": added, "summary": compute_summary()}


def compute_summary() -> dict[str, Any]:
    data = _load()
    records = data.get("records") or []
    if not records:
        return {"total": 0, "hit_rate_pct": None, "by_horizon": {}, "by_stance": {}}

    hits = sum(1 for r in records if (r.get("accuracy") or {}).get("hit"))
    total = len(records)
    by_horizon: dict[str, dict[str, int]] = {}
    by_stance: dict[str, dict[str, int]] = {}
    for r in records:
        h = r.get("predicted_horizon") or "unknown"
        s = r.get("predicted_stance") or "unknown"
        by_horizon.setdefault(h, {"total": 0, "hits": 0})
        by_stance.setdefault(s, {"total": 0, "hits": 0})
        by_horizon[h]["total"] += 1
        by_stance[s]["total"] += 1
        if (r.get("accuracy") or {}).get("hit"):
            by_horizon[h]["hits"] += 1
            by_stance[s]["hits"] += 1

    def _rate(bucket: dict[str, dict[str, int]]) -> dict[str, Any]:
        out = {}
        for k, v in bucket.items():
            out[k] = {
                **v,
                "hit_rate_pct": round(100 * v["hits"] / v["total"], 1) if v["total"] else None,
            }
        return out

    return {
        "total": total,
        "hits": hits,
        "hit_rate_pct": round(100 * hits / total, 1) if total else None,
        "by_horizon": _rate(by_horizon),
        "by_stance": _rate(by_stance),
    }


def scoreboard_payload(limit: int = 50) -> dict[str, Any]:
    data = _load()
    sync_from_predictions()
    data = _load()
    return {
        "summary": compute_summary(),
        "records": (data.get("records") or [])[:limit],
        "updated_at": data.get("updated_at"),
    }
