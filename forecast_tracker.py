"""7-day desk forecasts: store in Chroma, track intraday drift, score on later runs.

Educational scenario bands only — not investment advice or guaranteed forecasts.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from utils.errors import swallow
from utils.logging_config import get_logger
from utils.numbers import fmt_signed_pct, parse_float as _num

logger = get_logger(__name__)

FORECAST_HORIZON_DAYS = 7
KIND_FORECAST = "7d_forecast"
KIND_FORECAST_LEGACY = "15d_forecast"
KIND_OUTCOME = "forecast_outcome"
KIND_DRIFT = "forecast_drift"
FORECAST_JSON_KEY = "forecast_7d"
FORECAST_JSON_KEY_LEGACY = "forecast_15d"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception as exc:
        swallow("Invalid forecast datetime", exc)
        return None


def _direction_from_return(ret_pct: Optional[float]) -> str:
    if ret_pct is None:
        return "sideways"
    if ret_pct > 1.0:
        return "up"
    if ret_pct < -1.0:
        return "down"
    return "sideways"


def session_part_of_day(dt: Optional[datetime] = None) -> str:
    dt = dt or _now()
    hour = dt.hour
    if hour < 12:
        return "Morning"
    if hour < 17:
        return "Afternoon"
    return "Evening"


def _extract_forecast(parsed: dict[str, Any]) -> dict[str, Any]:
    return (
        parsed.get(FORECAST_JSON_KEY)
        or parsed.get(FORECAST_JSON_KEY_LEGACY)
        or parsed
    )


def _rag():
    from genai_research import _safe_embed, insights_collection, parse_stored_document
    return insights_collection, parse_stored_document, _safe_embed


def _forecast_kinds() -> tuple[str, ...]:
    return (KIND_FORECAST, KIND_FORECAST_LEGACY)


def _list_by_kinds(symbol: str, kinds: tuple[str, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for kind in kinds:
        rows.extend(_list_by_kind(symbol, kind))
    rows.sort(key=lambda r: (r.get("metadata") or {}).get("created_at") or "", reverse=True)
    return rows


def build_heuristic_forecast(
    *,
    symbol: str,
    baseline_price: float,
    as_of: str,
    technicals: dict[str, Any],
    ratings: dict[str, Any],
    news_bundle: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Fallback 7-day band when the LLM omits forecast_7d."""
    px = float(baseline_price)
    best_h = ratings.get("best_horizon") or "1w"
    best = ((ratings.get("horizons") or {}).get(best_h) or {})
    horizon_ret = _num(best.get("horizon_return_pct")) or 0.0
    stance = (ratings.get("composite_stance") or "mixed").lower()
    rsi = _num((technicals.get("momentum") or {}).get("rsi_14"))
    atr_pct = _num((technicals.get("volatility") or {}).get("atr_pct")) or 2.0

    drift = max(-5.0, min(5.0, horizon_ret * 0.28))
    if stance in ("bullish", "strong_favorable", "favorable"):
        drift += 1.0
    elif stance in ("bearish", "cautious", "unfavorable", "strong_unfavorable"):
        drift -= 1.0
    if rsi is not None:
        if rsi >= 70:
            drift -= 0.7
        elif rsi <= 30:
            drift += 0.4

    band_half = max(1.2, min(6.0, atr_pct * 1.8))
    expected_return_pct = round(drift, 2)
    target = round(px * (1 + expected_return_pct / 100), 2)
    low = round(px * (1 + (expected_return_pct - band_half) / 100), 2)
    high = round(px * (1 + (expected_return_pct + band_half) / 100), 2)
    direction = _direction_from_return(expected_return_pct)

    hi_news = (news_bundle or {}).get("high_impact_count") or 0
    confidence = 55
    if abs(expected_return_pct) >= 2.5:
        confidence += 6
    if hi_news:
        confidence -= min(10, hi_news * 3)

    expires = (_parse_dt(as_of) or _now()) + timedelta(days=FORECAST_HORIZON_DAYS)
    recorded = _now()
    return {
        "horizon_days": FORECAST_HORIZON_DAYS,
        "baseline_price": round(px, 4),
        "as_of": as_of,
        "recorded_at": recorded.isoformat(),
        "session": session_part_of_day(recorded),
        "direction": direction,
        "target_price": target,
        "price_band_low": low,
        "price_band_high": high,
        "expected_return_pct": expected_return_pct,
        "confidence": max(35, min(85, int(confidence))),
        "key_drivers": [
            f"Composite stance {stance.replace('_', ' ')} on {best_h} horizon",
            f"Recent horizon return {horizon_ret:+.1f}% scaled into 7d band",
        ],
        "risks_to_forecast": [
            "Macro/news shock not in baseline tape",
            "Gap move around earnings or policy",
        ],
        "rationale": (
            f"Heuristic 7-day educational band from horizon grades, RSI, and ATR — "
            f"not a statistical forecast model."
        ),
        "expires_at": expires.date().isoformat(),
        "source": "heuristic",
    }


def normalize_forecast(
    raw: Optional[dict[str, Any]],
    *,
    baseline_price: float,
    as_of: str,
    technicals: dict[str, Any],
    ratings: dict[str, Any],
    news_bundle: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if not raw or not isinstance(raw, dict):
        return build_heuristic_forecast(
            symbol="",
            baseline_price=baseline_price,
            as_of=as_of,
            technicals=technicals,
            ratings=ratings,
            news_bundle=news_bundle,
        )
    base = build_heuristic_forecast(
        symbol="",
        baseline_price=baseline_price,
        as_of=as_of,
        technicals=technicals,
        ratings=ratings,
        news_bundle=news_bundle,
    )
    px = float(baseline_price)
    out = {**base, **{k: v for k, v in raw.items() if v is not None}}
    out["horizon_days"] = FORECAST_HORIZON_DAYS
    out["baseline_price"] = round(px, 4)
    out["as_of"] = as_of
    if not out.get("recorded_at"):
        out["recorded_at"] = _now_iso()
    if not out.get("session"):
        out["session"] = session_part_of_day(_parse_dt(out.get("recorded_at")))
    exp = _num(out.get("expected_return_pct"))
    if exp is None and out.get("target_price"):
        tgt = _num(out["target_price"])
        if tgt:
            exp = ((tgt / px) - 1) * 100
    if exp is not None:
        out["expected_return_pct"] = round(exp, 2)
    out["direction"] = (out.get("direction") or _direction_from_return(exp)).lower()
    if not out.get("target_price"):
        out["target_price"] = round(px * (1 + (exp or 0) / 100), 2)
    if not out.get("price_band_low") or not out.get("price_band_high"):
        half = max(1.2, _num((technicals.get("volatility") or {}).get("atr_pct")) or 2.0) * 1.8
        out["price_band_low"] = round(px * (1 + ((exp or 0) - half) / 100), 2)
        out["price_band_high"] = round(px * (1 + ((exp or 0) + half) / 100), 2)
    expires = out.get("expires_at")
    if not expires:
        expires = ((_parse_dt(as_of) or _now()) + timedelta(days=FORECAST_HORIZON_DAYS)).date().isoformat()
    out["expires_at"] = str(expires)[:10]
    out.setdefault("source", "llm")
    return out


def compute_drift_vs_prior(
    prior_forecast: dict[str, Any],
    new_forecast: dict[str, Any],
    *,
    prior_meta: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Compare new run vs most recent forecast — highlights same-day drift."""
    prev_base = _num(prior_forecast.get("baseline_price")) or 0.0
    new_base = _num(new_forecast.get("baseline_price")) or prev_base or 1.0
    prev_tgt = _num(prior_forecast.get("target_price"))
    new_tgt = _num(new_forecast.get("target_price"))
    prev_exp = _num(prior_forecast.get("expected_return_pct")) or 0.0
    new_exp = _num(new_forecast.get("expected_return_pct")) or 0.0
    prev_dir = (prior_forecast.get("direction") or "sideways").lower()
    new_dir = (new_forecast.get("direction") or "sideways").lower()

    target_drift_pct = round(((new_tgt or 0) - (prev_tgt or 0)) / max(prev_base, 1) * 100, 2) if prev_tgt and new_tgt else None
    exp_drift_pct = round(new_exp - prev_exp, 2)
    base_drift_pct = round(((new_base - prev_base) / max(prev_base, 1)) * 100, 2) if prev_base else None
    direction_changed = prev_dir != new_dir

    prior_dt = _parse_dt((prior_meta or {}).get("created_at") or prior_forecast.get("recorded_at"))
    new_dt = _parse_dt(new_forecast.get("recorded_at"))
    same_day = bool(prior_dt and new_dt and prior_dt.date() == new_dt.date())

    reasons: list[str] = []
    if same_day:
        reasons.append(f"Same-day rerun ({session_part_of_day(new_dt)} vs {session_part_of_day(prior_dt)})")
    if direction_changed:
        reasons.append(f"Direction {prev_dir} → {new_dir}")
    if target_drift_pct is not None and abs(target_drift_pct) >= 0.35:
        reasons.append(f"Target drift {target_drift_pct:+.2f}% vs prior call")
    if base_drift_pct is not None and abs(base_drift_pct) >= 0.15:
        reasons.append(f"Baseline moved {base_drift_pct:+.2f}%")
    if abs(exp_drift_pct) >= 0.35:
        reasons.append(f"Expected move shifted {exp_drift_pct:+.2f}pp")

    highlight = (
        same_day
        or direction_changed
        or (target_drift_pct is not None and abs(target_drift_pct) >= 0.25)
        or abs(exp_drift_pct) >= 0.25
        or (base_drift_pct is not None and abs(base_drift_pct) >= 0.1)
    )
    reason_short = "; ".join(reasons[:3]) if reasons else "Minor refresh — view largely unchanged"

    return {
        "has_prior": True,
        "same_day": same_day,
        "prior_recorded_at": prior_dt.isoformat() if prior_dt else None,
        "prior_session": session_part_of_day(prior_dt) if prior_dt else None,
        "target_drift_pct": target_drift_pct,
        "expected_return_drift_pct": exp_drift_pct,
        "baseline_drift_pct": base_drift_pct,
        "direction_changed": direction_changed,
        "highlight": highlight,
        "reason_short": reason_short,
    }


def build_forward_path(forecast: dict[str, Any]) -> list[dict[str, Any]]:
    """Educational day-by-day path for the next 7 calendar days."""
    start = _parse_dt(forecast.get("recorded_at")) or _parse_dt(forecast.get("as_of")) or _now()
    base = _num(forecast.get("baseline_price")) or 0.0
    low = _num(forecast.get("price_band_low")) or base
    high = _num(forecast.get("price_band_high")) or base
    target = _num(forecast.get("target_price")) or base
    if base <= 0:
        return []
    rows: list[dict[str, Any]] = []
    for day in range(1, FORECAST_HORIZON_DAYS + 1):
        t = day / FORECAST_HORIZON_DAYS
        path_mid = round(base + (target - base) * t, 2)
        path_low = round(base + (low - base) * t, 2)
        path_high = round(base + (high - base) * t, 2)
        dt = start + timedelta(days=day)
        rows.append({
            "row_type": "forward",
            "day_offset": day,
            "date": dt.date().isoformat(),
            "label": dt.strftime("%a %d %b"),
            "path_mid": path_mid,
            "path_low": path_low,
            "path_high": path_high,
            "note": "Scenario path — not a daily guarantee",
        })
    return rows


def _list_by_kind(symbol: str, kind: str) -> list[dict[str, Any]]:
    insights_collection, parse_stored_document, _ = _rag()
    db = insights_collection()
    if db.count() == 0:
        return []
    try:
        raw = db.get(
            where={"$and": [{"symbol": symbol.upper()}, {"kind": kind}]},
            include=["documents", "metadatas"],
        )
    except Exception as exc:
        logger.debug("Chroma kind filter failed for %s/%s, falling back", symbol, kind, exc_info=exc)
        try:
            raw = db.get(where={"symbol": symbol.upper()}, include=["documents", "metadatas"])
        except Exception as inner:
            swallow(f"Chroma list failed for {symbol}/{kind}", inner)
            return []
        rows = []
        for doc, meta in zip(raw.get("documents") or [], raw.get("metadatas") or []):
            if (meta or {}).get("kind") == kind:
                rows.append({"id": meta.get("forecast_id") or meta.get("id"), "text": doc, "metadata": meta or {}})
        rows.sort(key=lambda r: (r["metadata"] or {}).get("created_at") or "", reverse=True)
        return rows

    rows = []
    ids = raw.get("ids") or []
    for doc_id, doc, meta in zip(ids, raw.get("documents") or [], raw.get("metadatas") or []):
        rows.append({"id": doc_id, "text": doc, "metadata": meta or {}})
    rows.sort(key=lambda r: (r["metadata"] or {}).get("created_at") or "", reverse=True)
    return rows


def list_forecast_runs(symbol: str, limit: int = 20) -> list[dict[str, Any]]:
    """All stored forecast runs for tabular display."""
    _, parse_stored_document, _ = _rag()
    runs: list[dict[str, Any]] = []
    for row in _list_by_kinds(symbol.upper(), _forecast_kinds())[:limit]:
        meta = row.get("metadata") or {}
        parsed = parse_stored_document(row.get("text") or "")
        fc = _extract_forecast(parsed)
        drift = parsed.get("drift_vs_prior") or {}
        runs.append({
            "id": row.get("id"),
            "recorded_at": meta.get("created_at") or fc.get("recorded_at"),
            "session": fc.get("session") or session_part_of_day(_parse_dt(meta.get("created_at"))),
            "baseline_price": fc.get("baseline_price"),
            "direction": fc.get("direction"),
            "target_price": fc.get("target_price"),
            "expected_return_pct": fc.get("expected_return_pct"),
            "price_band_low": fc.get("price_band_low"),
            "price_band_high": fc.get("price_band_high"),
            "confidence": fc.get("confidence"),
            "expires_at": fc.get("expires_at"),
            "drift": drift,
            "drift_highlight": bool(drift.get("highlight")),
            "drift_reason": drift.get("reason_short") if drift.get("has_prior") else "First run",
            "provider": meta.get("provider"),
            "model": meta.get("model"),
        })
    return runs


def build_forecast_table(
    *,
    symbol: str,
    latest_forecast: dict[str, Any],
    drift: Optional[dict[str, Any]] = None,
    limit_runs: int = 12,
) -> dict[str, Any]:
    """Combined run log + 7-day forward path for UI."""
    runs = list_forecast_runs(symbol, limit=limit_runs)
    if drift and drift.get("has_prior") and runs:
        runs[0] = {**runs[0], "drift": drift, "drift_highlight": drift.get("highlight"), "drift_reason": drift.get("reason_short")}
    return {
        "horizon_days": FORECAST_HORIZON_DAYS,
        "runs": runs,
        "forward_path": build_forward_path(latest_forecast),
        "latest": latest_forecast,
        "latest_drift": drift or {},
    }


def _scored_parent_ids(symbol: str) -> set[str]:
    outcomes = _list_by_kind(symbol, KIND_OUTCOME)
    return {
        (o.get("metadata") or {}).get("parent_forecast_id") or ""
        for o in outcomes
    } - {""}


def list_pending_forecasts(symbol: str) -> list[dict[str, Any]]:
    scored = _scored_parent_ids(symbol)
    pending = []
    _, parse_stored_document, _ = _rag()
    for row in _list_by_kinds(symbol.upper(), _forecast_kinds()):
        fid = row.get("id") or (row.get("metadata") or {}).get("forecast_id")
        if fid in scored:
            continue
        if (row.get("metadata") or {}).get("accuracy_status") == "scored":
            continue
        forecast = parse_stored_document(row.get("text") or "")
        pending.append({**row, "forecast": _extract_forecast(forecast)})
    return pending


def get_latest_forecast_run(symbol: str) -> Optional[dict[str, Any]]:
    rows = _list_by_kinds(symbol.upper(), _forecast_kinds())
    if not rows:
        return None
    row = rows[0]
    _, parse_stored_document, _ = _rag()
    parsed = parse_stored_document(row.get("text") or "")
    return {
        "id": row.get("id"),
        "metadata": row.get("metadata") or {},
        "forecast": _extract_forecast(parsed),
    }


def append_forecast_drift_record(
    *,
    symbol: str,
    drift: dict[str, Any],
    prior_forecast: dict[str, Any],
    new_forecast: dict[str, Any],
    provider: str,
    model: str,
) -> dict[str, Any]:
    """Persist intraday / rerun drift as its own RAG lesson row."""
    if not drift.get("has_prior"):
        return {}
    insights_collection, _, _safe_embed = _rag()
    drift_id = str(uuid.uuid4())
    created = _now_iso()
    payload = {
        "drift": drift,
        "prior_forecast": prior_forecast,
        "new_forecast": new_forecast,
        "lesson": drift.get("reason_short"),
    }
    document = (
        f"SYMBOL: {symbol.upper()}\n"
        f"KIND: {KIND_DRIFT}\n"
        f"CREATED: {created}\n"
        f"DRIFT: {drift.get('reason_short')}\n"
        f"FULL_JSON:\n{json.dumps(payload, ensure_ascii=False)[:4000]}"
    )
    db = insights_collection()
    db.add(
        ids=[drift_id],
        documents=[document],
        metadatas=[{
            "symbol": symbol.upper(),
            "provider": provider,
            "model": model,
            "created_at": created,
            "kind": KIND_DRIFT,
            "same_day": str(bool(drift.get("same_day"))),
            "highlight": str(bool(drift.get("highlight"))),
        }],
        embeddings=_safe_embed([document]),
    )
    return {"id": drift_id, "created_at": created}


def append_forecast_record(
    *,
    symbol: str,
    forecast: dict[str, Any],
    provider: str,
    model: str,
    as_of: str,
    memo_id: Optional[str] = None,
    context: Optional[dict[str, Any]] = None,
    drift: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Persist a 7-day forecast run with timestamp + optional drift vs prior."""
    insights_collection, _, _safe_embed = _rag()
    forecast_id = str(uuid.uuid4())
    created = _now_iso()
    forecast = {**forecast, "recorded_at": forecast.get("recorded_at") or created}
    payload = {
        FORECAST_JSON_KEY: forecast,
        "drift_vs_prior": drift or {},
        "context_snapshot": context or {},
        "forward_path": build_forward_path(forecast),
        "not_advice_disclaimer": "Educational 7-day scenario band — not investment advice.",
    }
    drift_note = f" Drift: {drift.get('reason_short')}." if drift and drift.get("has_prior") else ""
    narrative = (
        f"7-day forecast for {symbol.upper()} @ {created}: {forecast.get('direction')} to "
        f"{forecast.get('target_price')} ({fmt_signed_pct(forecast.get('expected_return_pct'), digits=1)}%) "
        f"from baseline {forecast.get('baseline_price')} expiring {forecast.get('expires_at')}."
        f"{drift_note}"
    )
    document = (
        f"SYMBOL: {symbol.upper()}\n"
        f"KIND: {KIND_FORECAST}\n"
        f"AS_OF: {as_of}\n"
        f"PROVIDER: {provider} / {model}\n"
        f"CREATED: {created}\n"
        f"FORECAST_ID: {forecast_id}\n"
        f"SUMMARY: {narrative}\n"
        f"FULL_JSON:\n{json.dumps(payload, ensure_ascii=False)[:6000]}"
    )
    db = insights_collection()
    db.add(
        ids=[forecast_id],
        documents=[document],
        metadatas=[{
            "symbol": symbol.upper(),
            "provider": provider,
            "model": model,
            "as_of": as_of or "",
            "created_at": created,
            "kind": KIND_FORECAST,
            "accuracy_status": "pending",
            "forecast_id": forecast_id,
            "expires_at": str(forecast.get("expires_at") or ""),
            "baseline_price": str(forecast.get("baseline_price") or ""),
            "target_price": str(forecast.get("target_price") or ""),
            "memo_id": memo_id or "",
            "session": str(forecast.get("session") or ""),
            "drift_highlight": str(bool((drift or {}).get("highlight"))),
        }],
        embeddings=_safe_embed([document]),
    )
    table = build_forecast_table(symbol=symbol, latest_forecast=forecast, drift=drift)
    return {
        "id": forecast_id,
        "created_at": created,
        "symbol": symbol.upper(),
        "forecast": forecast,
        "drift": drift or {},
        "table": table,
    }


def _score_direction(predicted: str, actual_return_pct: float) -> bool:
    pred = (predicted or "sideways").lower()
    if pred == "up":
        return actual_return_pct > 0.5
    if pred == "down":
        return actual_return_pct < -0.5
    return abs(actual_return_pct) <= 2.0


def _accuracy_label(direction_hit: bool, band_hit: bool, target_error_pct: float) -> str:
    if direction_hit and band_hit and target_error_pct <= 3.0:
        return "accurate"
    if direction_hit or band_hit or target_error_pct <= 5.0:
        return "partially_accurate"
    return "missed"


def explain_mismatch(
    *,
    forecast: dict[str, Any],
    actual_price: float,
    actual_return_pct: float,
    news_bundle: Optional[dict[str, Any]] = None,
    technicals: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    reasons: list[str] = []
    events: list[str] = []
    predicted = (forecast.get("direction") or "sideways").lower()
    actual_dir = _direction_from_return(actual_return_pct)

    if predicted != actual_dir:
        reasons.append(
            f"Direction miss: forecast {predicted}, tape delivered {actual_dir} "
            f"({actual_return_pct:+.2f}% from baseline)."
        )

    target = _num(forecast.get("target_price"))
    if target is not None:
        err = abs(actual_price - target) / max(_num(forecast.get("baseline_price")) or actual_price, 1) * 100
        if err > 5:
            reasons.append(f"Target far from actual ({err:.1f}% error vs target {target:.2f}).")

    headlines = (news_bundle or {}).get("headlines") or []
    hi = [h for h in headlines if (h.get("catalyst_tag") or "").startswith("high") or h.get("catalyst_tag") in {
        "war_geopolitics", "rates_inflation", "regulation", "supply_commodity", "corporate_event", "weather",
    }]
    for h in hi[:4]:
        title = (h.get("title") or "")[:120]
        tag = h.get("catalyst_label") or h.get("catalyst_tag") or "News"
        events.append(f"{tag}: {title}")

    if events:
        reasons.append("Material headlines since forecast may have repriced the name: " + "; ".join(events[:2]))

    ctx = forecast.get("context_snapshot") or {}
    old_stance = ctx.get("composite_stance")
    new_stance = (technicals or {}).get("composite_stance") if isinstance(technicals, dict) else None
    if old_stance and new_stance and old_stance != new_stance:
        reasons.append(f"Composite stance shifted {old_stance} → {new_stance}.")

    if not reasons:
        reasons.append("Move stayed inside noise band — forecast drivers may have been overstated.")

    return {
        "reasons": reasons[:6],
        "likely_events": events[:5],
        "summary": reasons[0] if reasons else "No detailed mismatch summary.",
    }


def score_forecast(
    *,
    forecast: dict[str, Any],
    forecast_meta: dict[str, Any],
    current_price: float,
    as_of: str,
    news_bundle: Optional[dict[str, Any]] = None,
    technicals: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    baseline = _num(forecast.get("baseline_price")) or _num(forecast_meta.get("baseline_price"))
    if not baseline or baseline <= 0:
        baseline = current_price
    actual_return_pct = round(((current_price / baseline) - 1) * 100, 3)
    predicted_dir = (forecast.get("direction") or "sideways").lower()
    direction_hit = _score_direction(predicted_dir, actual_return_pct)
    low = _num(forecast.get("price_band_low"))
    high = _num(forecast.get("price_band_high"))
    band_hit = low is not None and high is not None and low <= current_price <= high
    target = _num(forecast.get("target_price"))
    target_error_pct = round(abs(current_price - target) / baseline * 100, 2) if target else 999.0
    label = _accuracy_label(direction_hit, band_hit, target_error_pct)
    accuracy_pct = 100.0
    if not direction_hit:
        accuracy_pct -= 35
    if not band_hit:
        accuracy_pct -= 25
    accuracy_pct -= min(30, target_error_pct * 3)
    accuracy_pct = max(0, min(100, round(accuracy_pct, 1)))

    mismatch = explain_mismatch(
        forecast=forecast,
        actual_price=current_price,
        actual_return_pct=actual_return_pct,
        news_bundle=news_bundle,
        technicals=technicals,
    )
    created = _parse_dt(forecast_meta.get("created_at"))
    days_elapsed = (_parse_dt(as_of) or _now()) - created if created else timedelta(days=FORECAST_HORIZON_DAYS)
    days_elapsed_n = max(1, days_elapsed.days if created else FORECAST_HORIZON_DAYS)

    return {
        "label": label,
        "accuracy_pct": accuracy_pct,
        "direction_hit": direction_hit,
        "band_hit": band_hit,
        "target_error_pct": target_error_pct,
        "predicted_direction": predicted_dir,
        "actual_direction": _direction_from_return(actual_return_pct),
        "baseline_price": baseline,
        "actual_price": round(current_price, 4),
        "actual_return_pct": actual_return_pct,
        "target_price": target,
        "days_elapsed": days_elapsed_n,
        "maturity": "final" if days_elapsed_n >= FORECAST_HORIZON_DAYS else "interim",
        "mismatch": mismatch,
    }


def append_forecast_outcome(
    *,
    symbol: str,
    forecast: dict[str, Any],
    score: dict[str, Any],
    parent_forecast_id: str,
    provider: str,
    model: str,
    as_of: str,
) -> dict[str, Any]:
    insights_collection, _, _safe_embed = _rag()
    outcome_id = str(uuid.uuid4())
    created = _now_iso()
    lesson = {
        "symbol": symbol.upper(),
        FORECAST_JSON_KEY: forecast,
        "accuracy": score,
        "lesson": (
            f"{symbol.upper()} 7d forecast {score.get('label')}: predicted {score.get('predicted_direction')} "
            f"to {score.get('target_price')}, actual {fmt_signed_pct(score.get('actual_return_pct'))}%. "
            f"{score.get('mismatch', {}).get('summary', '')}"
        ),
        "not_advice_disclaimer": "Forecast accuracy post-mortem for educational RAG memory only.",
    }
    document = (
        f"SYMBOL: {symbol.upper()}\n"
        f"KIND: {KIND_OUTCOME}\n"
        f"AS_OF: {as_of}\n"
        f"PROVIDER: {provider} / {model}\n"
        f"CREATED: {created}\n"
        f"PARENT_FORECAST: {parent_forecast_id}\n"
        f"ACCURACY: {score.get('label')} ({score.get('accuracy_pct')}%)\n"
        f"LESSON: {lesson['lesson']}\n"
        f"FULL_JSON:\n{json.dumps(lesson, ensure_ascii=False)[:6000]}"
    )
    db = insights_collection()
    db.add(
        ids=[outcome_id],
        documents=[document],
        metadatas=[{
            "symbol": symbol.upper(),
            "provider": provider,
            "model": model,
            "as_of": as_of or "",
            "created_at": created,
            "kind": KIND_OUTCOME,
            "parent_forecast_id": parent_forecast_id,
            "accuracy_label": str(score.get("label") or ""),
            "accuracy_pct": str(score.get("accuracy_pct") or ""),
        }],
        embeddings=_safe_embed([document]),
    )
    return {"id": outcome_id, "created_at": created, "lesson": lesson}


def review_pending_forecasts(
    *,
    symbol: str,
    current_price: float,
    as_of: str,
    news_bundle: Optional[dict[str, Any]] = None,
    technicals: Optional[dict[str, Any]] = None,
    ratings: Optional[dict[str, Any]] = None,
    provider: str = "forecast_tracker",
    model: str = "auto_score",
    finalize: bool = True,
) -> dict[str, Any]:
    pending = list_pending_forecasts(symbol)
    reviews: list[dict[str, Any]] = []
    _, parse_stored_document, _ = _rag()
    for row in pending:
        meta = row.get("metadata") or {}
        created = _parse_dt(meta.get("created_at"))
        days_old = (_parse_dt(as_of) or _now()) - created if created else timedelta(days=0)
        forecast = row.get("forecast") or {}
        if not forecast.get("baseline_price"):
            forecast = _extract_forecast(parse_stored_document(row.get("text") or ""))
        score = score_forecast(
            forecast=forecast,
            forecast_meta=meta,
            current_price=current_price,
            as_of=as_of,
            news_bundle=news_bundle,
            technicals={"composite_stance": (ratings or {}).get("composite_stance"), **(technicals or {})},
        )
        score["maturity"] = "final" if days_old.days >= FORECAST_HORIZON_DAYS else "interim"
        outcome = None
        if finalize and days_old.days >= FORECAST_HORIZON_DAYS:
            outcome = append_forecast_outcome(
                symbol=symbol,
                forecast=forecast,
                score=score,
                parent_forecast_id=row.get("id") or meta.get("forecast_id") or "",
                provider=provider,
                model=model,
                as_of=as_of,
            )
        reviews.append({
            "forecast_id": row.get("id"),
            "forecast": forecast,
            "score": score,
            "outcome": outcome,
            "days_old": days_old.days,
        })
    return {
        "symbol": symbol.upper(),
        "reviewed": len(reviews),
        "reviews": reviews,
        "pending_remaining": len(list_pending_forecasts(symbol)),
    }


def retrieve_forecast_lessons(
    query: str,
    *,
    symbol: Optional[str] = None,
    top_k: int = 5,
    include_global: bool = True,
) -> list[dict[str, Any]]:
    insights_collection, parse_stored_document, _safe_embed = _rag()
    db = insights_collection()
    if db.count() == 0:
        return []
    q = f"forecast accuracy drift lesson mismatch {query}"
    try:
        result = db.query(
            query_embeddings=_safe_embed([q]),
            n_results=min(top_k * 4, db.count()),
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:
        swallow(f"Forecast lesson retrieval failed for {symbol or 'global'}", exc)
        return []

    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]
    out = []
    for doc, meta, dist in zip(docs, metas, dists):
        meta = meta or {}
        if meta.get("kind") not in (KIND_OUTCOME, KIND_DRIFT):
            continue
        if symbol and not include_global and meta.get("symbol") != symbol.upper():
            continue
        parsed = parse_stored_document(doc or "")
        out.append({
            "text": doc,
            "lesson": parsed.get("lesson") or parsed.get("executive_summary") or doc[:400],
            "accuracy": parsed.get("accuracy") or {},
            "drift": parsed.get("drift") or {},
            "metadata": meta,
            "distance": round(float(dist), 4) if dist is not None else None,
        })
        if len(out) >= top_k:
            break
    return out


def format_lessons_block(lessons: list[dict[str, Any]]) -> str:
    if not lessons:
        return "(No prior forecast accuracy lessons in RAG yet.)"
    lines = []
    for i, item in enumerate(lessons, start=1):
        acc = item.get("accuracy") or {}
        drift = item.get("drift") or {}
        meta = item.get("metadata") or {}
        lines.append(
            f"[Lesson {i} · {meta.get('symbol')} · {meta.get('created_at')} · "
            f"{acc.get('label', meta.get('accuracy_label', meta.get('kind')))} · "
            f"{drift.get('reason_short') or item.get('lesson', '')[:120]}]\n"
            f"{item.get('lesson') or item.get('text', '')[:900]}"
        )
    return "\n\n".join(lines)


def prepare_forecast_filing(
    *,
    symbol: str,
    forecast: dict[str, Any],
    provider: str,
    model: str,
    as_of: str,
    memo_id: Optional[str] = None,
    context: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Compute drift vs latest RAG forecast, then file the new run."""
    prior = get_latest_forecast_run(symbol)
    drift: dict[str, Any] = {"has_prior": False}
    if prior and prior.get("forecast"):
        drift = compute_drift_vs_prior(
            prior["forecast"],
            forecast,
            prior_meta=prior.get("metadata"),
        )
    stored = append_forecast_record(
        symbol=symbol,
        forecast=forecast,
        provider=provider,
        model=model,
        as_of=as_of,
        memo_id=memo_id,
        context=context,
        drift=drift,
    )
    if drift.get("has_prior") and drift.get("highlight"):
        append_forecast_drift_record(
            symbol=symbol,
            drift=drift,
            prior_forecast=prior["forecast"],
            new_forecast=forecast,
            provider=provider,
            model=model,
        )
    return stored
