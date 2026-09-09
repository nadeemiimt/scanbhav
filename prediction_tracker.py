"""Live prediction tracker: pin up to 5 analyses and score them later.

Stores snapshots locally, refreshes mark-to-market accuracy, and appends rated
outcomes into Chroma (stock_insights) for future GenAI / RAG context.
Educational only — not investment advice.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from config import BASE_DIR
from genai_research import append_insight

TRACK_PATH = BASE_DIR / "data" / "predictions" / "live_track.json"
MAX_TRACKED = 5


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure() -> dict[str, Any]:
    TRACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not TRACK_PATH.exists():
        payload = {"items": [], "updated_at": _now()}
        TRACK_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload
    try:
        return json.loads(TRACK_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"items": [], "updated_at": _now()}


def _save(payload: dict[str, Any]) -> dict[str, Any]:
    payload["updated_at"] = _now()
    TRACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    TRACK_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def list_tracked() -> dict[str, Any]:
    data = _ensure()
    return {
        "items": data.get("items") or [],
        "count": len(data.get("items") or []),
        "max": MAX_TRACKED,
        "updated_at": data.get("updated_at"),
        "path": str(TRACK_PATH),
    }


def add_prediction(
    *,
    symbol: str,
    name: str = "",
    entry_price: float,
    as_of: str = "",
    predicted_stance: str,
    predicted_horizon: str = "1m",
    composite_score: Optional[float] = None,
    conviction_score: Optional[float] = None,
    summary: str = "",
) -> dict[str, Any]:
    data = _ensure()
    items: list[dict[str, Any]] = list(data.get("items") or [])
    sym = symbol.upper().strip()
    # Replace existing open track for same symbol
    items = [i for i in items if not (i.get("symbol") == sym and i.get("status") == "open")]
    if len([i for i in items if i.get("status") == "open"]) >= MAX_TRACKED:
        raise ValueError(f"Already tracking {MAX_TRACKED} open predictions. Rate/close one first.")

    item = {
        "id": str(uuid.uuid4()),
        "symbol": sym,
        "name": name or sym,
        "status": "open",
        "created_at": _now(),
        "as_of": as_of or "",
        "entry_price": round(float(entry_price), 4),
        "latest_price": round(float(entry_price), 4),
        "return_pct": 0.0,
        "predicted_stance": (predicted_stance or "neutral").lower(),
        "predicted_horizon": predicted_horizon or "1m",
        "composite_score": composite_score,
        "conviction_score": conviction_score,
        "summary": (summary or "")[:500],
        "accuracy": None,
        "user_rating": None,
        "user_notes": "",
        "rated_at": None,
        "rag_saved": False,
        "rag_id": None,
    }
    items.insert(0, item)
    # Keep history but prefer open ones first; cap total list length
    opens = [i for i in items if i.get("status") == "open"][:MAX_TRACKED]
    closed = [i for i in items if i.get("status") != "open"][:20]
    data["items"] = opens + closed
    _save(data)
    return item


def remove_prediction(prediction_id: str) -> dict[str, Any]:
    data = _ensure()
    before = len(data.get("items") or [])
    data["items"] = [i for i in (data.get("items") or []) if i.get("id") != prediction_id]
    _save(data)
    return {"removed": before - len(data["items"]), "id": prediction_id}


def refresh_prices(price_map: dict[str, float]) -> dict[str, Any]:
    """Update latest_price/return_pct and provisional accuracy for open tracks."""
    data = _ensure()
    updated = 0
    normalized = {str(k).upper(): float(v) for k, v in price_map.items() if v}
    for item in data.get("items") or []:
        if item.get("status") != "open":
            continue
        sym = str(item.get("symbol") or "").upper()
        px = normalized.get(sym)
        if px is None:
            continue
        entry = float(item.get("entry_price") or 0)
        if entry <= 0:
            continue
        ret = ((float(px) / entry) - 1) * 100
        item["latest_price"] = round(float(px), 4)
        item["return_pct"] = round(ret, 3)
        item["accuracy"] = _score_accuracy(item.get("predicted_stance"), ret)
        item["last_refreshed_at"] = _now()
        updated += 1
    _save(data)
    return list_tracked() | {"refreshed": updated}


def fetch_mark_prices(symbols: list[str], *, provider: str = "auto") -> dict[str, float]:
    """Latest marks for open predictions — LTP cache, broker quotes, then fresh EOD."""
    from brokers.config import load_broker_env
    from brokers.quote_cache import get_prices
    from brokers.service import get_live_quotes
    from routes.helpers import fetch_prices, rows_from_payload
    from technicals import compute_technicals

    syms = list(dict.fromkeys(str(s).upper().strip() for s in symbols if s))
    price_map: dict[str, float] = {}

    for sym, row in (get_prices(syms, max_age_seconds=900) or {}).items():
        price_map[sym.upper()] = float(row["price"])

    missing = [s for s in syms if s not in price_map]
    if missing:
        env = load_broker_env()
        try:
            bq = get_live_quotes(env.default_broker or "stub", missing)
            for sym, row in (bq.get("quotes") or {}).items():
                px = row.get("price")
                if px:
                    price_map[str(sym).upper()] = float(px)
        except Exception:
            pass

    missing = [s for s in syms if s not in price_map]
    for sym in missing:
        try:
            payload = fetch_prices(sym, provider, force_refresh=True)
            tech = compute_technicals(rows_from_payload(payload))
            px = tech.get("price")
            if px:
                price_map[sym] = float(px)
        except Exception:
            continue
    return price_map


def _score_accuracy(stance: Optional[str], return_pct: float) -> dict[str, Any]:
    st = (stance or "neutral").lower()
    bullish = st in {"bullish", "constructive", "strong_favorable", "favorable"}
    bearish = st in {"bearish", "cautious", "unfavorable", "strong_unfavorable"}
    if bullish:
        hit = return_pct > 0.5
        label = "working" if hit else ("flat" if abs(return_pct) <= 0.5 else "missing")
    elif bearish:
        hit = return_pct < -0.5
        label = "working" if hit else ("flat" if abs(return_pct) <= 0.5 else "missing")
    else:
        hit = abs(return_pct) <= 2.0
        label = "working" if hit else "missing"
    return {
        "label": label,
        "hit": bool(hit),
        "return_pct": round(return_pct, 3),
        "rule": "bullish→up / bearish→down / neutral→quiet range (educational heuristic)",
    }


def rate_prediction(
    *,
    prediction_id: str,
    rating: int,
    notes: str = "",
    outcome_label: Optional[str] = None,
) -> dict[str, Any]:
    """User rates prediction 1–5; closes track and appends outcome to Chroma RAG."""
    if rating < 1 or rating > 5:
        raise ValueError("rating must be 1–5")
    data = _ensure()
    item = next((i for i in (data.get("items") or []) if i.get("id") == prediction_id), None)
    if not item:
        raise ValueError("prediction not found")

    accuracy = item.get("accuracy") or _score_accuracy(
        item.get("predicted_stance"), float(item.get("return_pct") or 0)
    )
    if outcome_label:
        accuracy = {**accuracy, "label": outcome_label}

    item["user_rating"] = int(rating)
    item["user_notes"] = (notes or "")[:800]
    item["rated_at"] = _now()
    item["status"] = "rated"
    item["accuracy"] = accuracy

    insight = {
        "stance": item.get("predicted_stance"),
        "executive_summary": (
            f"Live prediction review for {item.get('symbol')}: entry {item.get('entry_price')} → "
            f"{item.get('latest_price')} ({item.get('return_pct')}%). "
            f"Predicted {item.get('predicted_stance')} on {item.get('predicted_horizon')}. "
            f"Accuracy label={accuracy.get('label')}. User rating={rating}/5. "
            f"Notes: {notes or 'n/a'}."
        ),
        "key_bull_points": [],
        "key_bear_points": [],
        "technical_read": item.get("summary") or "",
        "fundamental_read": "",
        "news_catalyst_read": "",
        "macro_risks": [],
        "what_changed_vs_prior": "User-rated live prediction outcome for RAG memory.",
        "questions_to_monitor": [],
        "prediction_feedback": {
            "prediction_id": item.get("id"),
            "entry_price": item.get("entry_price"),
            "latest_price": item.get("latest_price"),
            "return_pct": item.get("return_pct"),
            "accuracy": accuracy,
            "user_rating": rating,
            "user_notes": notes,
            "composite_score": item.get("composite_score"),
            "conviction_score": item.get("conviction_score"),
        },
        "not_advice_disclaimer": "Educational prediction tracking only — not investment advice.",
    }
    stored = append_insight(
        symbol=item["symbol"],
        insight=insight,
        provider="prediction_tracker",
        model="user_rated_outcome",
        as_of=item.get("as_of") or item.get("created_at"),
    )
    # Tag kind in document via insight fields; metadata kind stays genai path —
    # also store tracker marker inside summary for retrieval.
    item["rag_saved"] = True
    item["rag_id"] = stored.get("id")
    _save(data)
    return {"item": item, "rag": stored}
