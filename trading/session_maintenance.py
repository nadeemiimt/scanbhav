"""
Trim autopilot session stores — safe while API is running.

- sessions.json: drop embedded trades/events, old stopped sessions, heavy cycles
- session_events.json: retention window + max count + slim bulky audit payloads
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

RetentionLabel = Literal["1h", "12h", "1d", "3d", "7d"]

RETENTION_HOURS: dict[str, int] = {
    "1h": 1,
    "12h": 12,
    "1d": 24,
    "3d": 72,
    "7d": 168,
}

# Detail keys that blow up JSON size (full universe audits, pick payloads).
_HEAVY_DETAIL_KEYS = frozenset({
    "universe_audit",
    "rag_context",
    "pick_result",
    "guard",
    "selected",
    "skipped",
    "rejected",
    "thought_process",
    "lessons",
    "rows",
    "candidates",
    "picks",
    "trades",
})


def _parse_iso(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        ts = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    except Exception:
        return None


def _event_keep(iso: str | None, *, cutoff: datetime) -> bool:
    ts = _parse_iso(iso)
    if ts is None:
        return True
    return ts >= cutoff


def slim_event_detail(event: dict[str, Any]) -> dict[str, Any]:
    """Keep audit metadata, drop megabyte-scale nested arrays."""
    out = dict(event)
    detail = out.get("detail")
    if not isinstance(detail, dict):
        return out

    slim: dict[str, Any] = {}
    for key, val in detail.items():
        if key in _HEAVY_DETAIL_KEYS:
            if isinstance(val, list):
                slim[f"{key}_count"] = len(val)
            elif isinstance(val, dict):
                slim[f"{key}_keys"] = list(val.keys())[:12]
            continue
        if key in {"cycle_id", "realized_pnl_inr", "guard_actions", "trades_attempted", "timing_blocked"}:
            slim[key] = val
            continue
        if isinstance(val, (str, int, float, bool)) or val is None:
            slim[key] = val
        elif isinstance(val, list) and len(val) <= 8:
            slim[key] = val
        elif isinstance(val, dict) and len(json.dumps(val, default=str)) < 400:
            slim[key] = val

    if not slim and detail:
        slim["trimmed"] = True
        for k in ("cycle_id", "symbol", "reason", "message"):
            if k in detail:
                slim[k] = detail[k]
    out["detail"] = slim
    return out


def slim_cycle_record(cycle: dict[str, Any]) -> dict[str, Any]:
    """Trim cycle blobs stored on sessions.json."""
    if not cycle:
        return {}
    keep = {
        k: cycle.get(k)
        for k in (
            "id",
            "at",
            "cycle_id",
            "session_id",
            "pick_mode",
            "market_open",
            "cap_reason",
            "realized_pnl_inr",
        )
        if k in cycle
    }
    guard = cycle.get("guard") or {}
    if guard:
        keep["guard_action_count"] = len(guard.get("actions") or [])
    pick = cycle.get("pick_result") or {}
    if pick:
        keep["trades_attempted"] = len(pick.get("trades") or [])
        keep["picks_count"] = len(pick.get("picks") or [])
    audit = cycle.get("universe_audit") or []
    if audit:
        keep["universe_audit_count"] = len(audit)
    notes = cycle.get("notes") or []
    if notes:
        keep["notes"] = notes[:5]
    return keep


def trim_sessions_json(
    *,
    max_sessions: int = 25,
    max_cycles_per_session: int = 40,
    force_strip_blobs: bool = True,
) -> dict[str, Any]:
    from trading.session_autopilot import SESSION_PATH, _load_store, _save_store

    if not SESSION_PATH.exists():
        return {"skipped": True, "reason": "no_sessions_file"}

    size_before = SESSION_PATH.stat().st_size
    store = _load_store()
    sessions: list[dict[str, Any]] = list(store.get("sessions") or [])
    active_ids = {
        str(x) for x in (store.get("active_session_ids") or [])
        if x
    }
    if store.get("active_session_id"):
        active_ids.add(str(store["active_session_id"]))

    stripped_trades = stripped_events = stripped_cycles = 0
    for session in sessions:
        if session.pop("trades", None) is not None:
            stripped_trades += 1
        if session.pop("events", None) is not None:
            stripped_events += 1
        cycles = session.get("cycles") or []
        if cycles:
            trimmed = [slim_cycle_record(c) for c in cycles[:max_cycles_per_session]]
            stripped_cycles += max(0, len(cycles) - len(trimmed))
            session["cycles"] = trimmed

    def _sort_key(s: dict[str, Any]) -> str:
        return str(s.get("stopped_at") or s.get("started_at") or "")

    active = [s for s in sessions if str(s.get("id") or "") in active_ids]
    stopped = [s for s in sessions if str(s.get("id") or "") not in active_ids]
    stopped.sort(key=_sort_key, reverse=True)
    kept_stopped = stopped[: max(0, max_sessions - len(active))]
    removed_sessions = len(stopped) - len(kept_stopped)
    store["sessions"] = active + kept_stopped

    _save_store(store)
    size_after = SESSION_PATH.stat().st_size
    return {
        "ok": True,
        "bytes_before": size_before,
        "bytes_after": size_after,
        "sessions_before": len(sessions),
        "sessions_after": len(store["sessions"]),
        "removed_stopped_sessions": removed_sessions,
        "stripped_trades_sessions": stripped_trades,
        "stripped_events_sessions": stripped_events,
        "trimmed_cycle_records": stripped_cycles,
        "force_strip_blobs": force_strip_blobs,
    }


def trim_session_events_json(
    *,
    retention: RetentionLabel = "7d",
    max_events: int = 2000,
    slim_details: bool = True,
) -> dict[str, Any]:
    from trading.session_history import EVENTS_PATH, _load_events_store, _save_events_store

    if not EVENTS_PATH.exists():
        return {"skipped": True, "reason": "no_events_file"}

    size_before = EVENTS_PATH.stat().st_size
    hours = RETENTION_HOURS.get(retention, 168)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    store = _load_events_store()
    events: list[dict[str, Any]] = list(store.get("events") or [])
    before = len(events)

    kept = [e for e in events if _event_keep(e.get("at"), cutoff=cutoff)]
    removed_age = before - len(kept)

    if len(kept) > max_events:
        kept = kept[:max_events]
    removed_cap = before - removed_age - len(kept)

    if slim_details:
        kept = [slim_event_detail(e) for e in kept]

    store["events"] = kept
    _save_events_store(store)
    size_after = EVENTS_PATH.stat().st_size

    return {
        "ok": True,
        "bytes_before": size_before,
        "bytes_after": size_after,
        "retention": retention,
        "cutoff": cutoff.isoformat(),
        "max_events": max_events,
        "events_before": before,
        "events_after": len(kept),
        "removed_by_age": removed_age,
        "removed_by_cap": removed_cap,
        "slim_details": slim_details,
    }


def trim_session_stores(
    *,
    retention: RetentionLabel = "7d",
    max_events: int = 2000,
    max_sessions: int = 25,
    max_cycles_per_session: int = 40,
    slim_event_details: bool = True,
) -> dict[str, Any]:
    """One-shot maintenance for sessions.json + session_events.json."""
    sessions_result = trim_sessions_json(
        max_sessions=max_sessions,
        max_cycles_per_session=max_cycles_per_session,
    )
    events_result = trim_session_events_json(
        retention=retention,
        max_events=max_events,
        slim_details=slim_event_details,
    )
    return {
        "ok": True,
        "sessions": sessions_result,
        "events": events_result,
    }
