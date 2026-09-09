"""Detailed autopilot session event log — every attempt, skip, and decision."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from config import BASE_DIR

EVENTS_PATH = BASE_DIR / "data" / "trading" / "session_events.json"

EventLevel = Literal["info", "action", "skip", "warn", "complete", "error"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_events_store() -> dict[str, Any]:
    from trading.json_cache import load_json_cached

    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not EVENTS_PATH.exists():
        return {"events": []}
    return load_json_cached(EVENTS_PATH, default={"events": []})


def _save_events_store(data: dict[str, Any]) -> None:
    from trading.json_cache import invalidate_json_cache
    from trading.json_store import dumps_pretty

    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVENTS_PATH.write_text(dumps_pretty(data), encoding="utf-8")
    invalidate_json_cache(EVENTS_PATH)


def _append_to_session(session_id: str, event: dict[str, Any]) -> None:
    from trading.session_autopilot import _find_session, _load_store, _save_store

    store = _load_store()
    session = _find_session(store, session_id)
    if not session:
        return
    session["event_count"] = int(session.get("event_count") or 0) + 1
    session.pop("events", None)
    _save_store(store)


def log_event(
    session_id: str,
    *,
    event_type: str,
    title: str,
    detail: Optional[dict[str, Any]] = None,
    level: EventLevel = "info",
    symbol: str = "",
    cycle_id: str = "",
) -> dict[str, Any]:
    """Append a structured event to global + session history."""
    from trading.store_lock import LOCK

    with LOCK:
        event = {
            "id": f"evt-{uuid.uuid4().hex[:14]}",
            "at": _now(),
            "session_id": session_id,
            "cycle_id": cycle_id or None,
            "type": event_type,
            "level": level,
            "title": title,
            "symbol": symbol.upper() if symbol else None,
            "detail": detail or {},
        }
        store = _load_events_store()
        store.setdefault("events", []).insert(0, event)
        store["events"] = store["events"][:2500]
        _save_events_store(store)
        _append_to_session(session_id, event)
        return event


def list_session_events(
    session_id: str | None = None,
    *,
    limit: int = 200,
    event_type: str = "",
    cycle_id: str = "",
) -> list[dict[str, Any]]:
    store = _load_events_store()
    rows = store.get("events") or []
    if session_id:
        rows = [r for r in rows if r.get("session_id") == session_id]
    if event_type:
        rows = [r for r in rows if r.get("type") == event_type]
    if cycle_id:
        rows = [r for r in rows if r.get("cycle_id") == cycle_id]
    return rows[:limit]


_RETENTION_HOURS = {"1h": 1, "12h": 12, "1d": 24, "7d": 168}


def purge_session_events(
    *,
    session_id: str | None = None,
    retention: Literal["1h", "12h", "1d", "7d"] = "7d",
) -> dict[str, Any]:
    """Remove session events/cycles older than the retention window."""
    from datetime import timedelta

    hours = _RETENTION_HOURS.get(retention, 168)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    cutoff_iso = cutoff.isoformat()

    def _keep(iso: str | None) -> bool:
        if not iso:
            return True
        try:
            ts = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return ts >= cutoff
        except Exception:
            return True

    store = _load_events_store()
    before = len(store.get("events") or [])
    if session_id:
        store["events"] = [
            e for e in (store.get("events") or [])
            if e.get("session_id") != session_id or _keep(e.get("at"))
        ]
    else:
        store["events"] = [e for e in (store.get("events") or []) if _keep(e.get("at"))]
    after_global = len(store.get("events") or [])
    _save_events_store(store)

    sessions_removed = 0
    cycles_removed = 0
    from trading.session_autopilot import _find_session, _load_store, _save_store

    sess_store = _load_store()
    targets = [session_id] if session_id else [
        s.get("id") for s in (sess_store.get("sessions") or []) if s.get("id")
    ]
    for sid in targets:
        session = _find_session(sess_store, sid)
        if not session:
            continue
        ev_before = len(session.get("events") or [])
        session["events"] = [e for e in (session.get("events") or []) if _keep(e.get("at"))]
        sessions_removed += ev_before - len(session.get("events") or [])
        cy_before = len(session.get("cycles") or [])
        session["cycles"] = [c for c in (session.get("cycles") or []) if _keep(c.get("at"))]
        cycles_removed += cy_before - len(session.get("cycles") or [])
    _save_store(sess_store)

    return {
        "ok": True,
        "retention": retention,
        "cutoff": cutoff_iso,
        "removed_global_events": before - after_global,
        "removed_session_events": sessions_removed,
        "removed_cycles": cycles_removed,
        "remaining_global_events": after_global,
    }


def sanitize_pick_row(row: dict[str, Any]) -> dict[str, Any]:
    """Strip bulky fields; keep audit-relevant scoring data."""
    if not row:
        return {}
    return {
        k: row.get(k)
        for k in (
            "symbol",
            "pick_score",
            "composite_score",
            "stance",
            "price",
            "quantity",
            "notional_inr",
            "expected_profit_inr",
            "expected_return_pct",
            "reasons",
            "fit_reason",
            "skipped",
            "reason",
            "order_id",
            "mode",
            "timing",
            "error",
            "risk_note",
            "plan",
            "entry_timing_now",
            "decision_rationale",
            "return_pct",
            "unrealized_inr",
        )
        if k in row and row.get(k) is not None
    }


def sanitize_pick_result(result: dict[str, Any]) -> dict[str, Any]:
    """Compact agent_picker output for durable session history."""
    if not result:
        return {}
    picks = [sanitize_pick_row(p) for p in (result.get("picks") or [])]
    candidates = [sanitize_pick_row(c) for c in (result.get("candidates") or [])]
    trades = [sanitize_pick_row(t) for t in (result.get("trades") or [])]
    timing_blocked = [sanitize_pick_row(t) for t in (result.get("timing_blocked") or [])]
    budget = result.get("budget") or {}
    held = budget.get("held_symbols")
    if isinstance(held, set):
        held = sorted(held)
    return {
        "mode": result.get("mode"),
        "universe": result.get("universe"),
        "universe_meta": result.get("universe_meta"),
        "error": result.get("error"),
        "scanned_count": result.get("scanned_count"),
        "affordable_candidates": result.get("affordable_candidates"),
        "min_composite": result.get("min_composite"),
        "target_pct": result.get("target_pct"),
        "allocation_strategy": result.get("allocation_strategy"),
        "budget": {
            k: (held if k == "held_symbols" else budget.get(k))
            for k in (
                "remaining_budget_inr",
                "buy_notional_used_inr",
                "max_daily_notional_inr",
                "position_slots",
                "orders_left",
                "open_positions",
                "held_symbols",
                "halted",
            )
            if k in budget
        },
        "picks": picks,
        "candidates": candidates,
        "trades": trades,
        "timing_blocked": timing_blocked,
        "executed": result.get("executed"),
    }


def build_universe_audit(
    *,
    universe: list[str],
    rows: list[dict[str, Any]],
    picks: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    limits: dict[str, Any],
    min_composite: float,
    held_symbols: Optional[set[str]] = None,
    target_pct: float = 1.5,
    desk_symbol: str = "",
) -> list[dict[str, Any]]:
    """Explain why each symbol in the universe was selected, skipped, or rejected."""
    from trading.agent_picker import BULLISH_STANCES, _score_screen_row

    held = held_symbols or set(limits.get("held_symbols") or [])
    selected = {str(p.get("symbol") or "").upper() for p in picks}
    candidate_syms = {str(c.get("symbol") or "").upper() for c in candidates}
    row_by_sym = {str(r.get("symbol") or "").upper(): r for r in rows}
    audit: list[dict[str, Any]] = []

    for sym in universe:
        sym = sym.upper()
        if sym in held:
            audit.append({
                "symbol": sym,
                "decision": "held",
                "reason": "Already in open MIS position — no new buy this cycle",
            })
            continue
        row = row_by_sym.get(sym)
        if not row:
            audit.append({
                "symbol": sym,
                "decision": "rejected",
                "reason": "No scan data — symbol not scored yet",
            })
            continue
        scored = _score_screen_row(row, target_pct=target_pct, desk_symbol=desk_symbol, fast=True)
        composite = float(scored.get("composite_score") or 0)
        stance = str(scored.get("stance") or "")
        if composite < min_composite:
            audit.append({
                "symbol": sym,
                "decision": "rejected",
                "reason": f"Composite {composite:.1f} below min {min_composite}",
                "composite_score": composite,
                "stance": stance,
                "pick_score": scored.get("pick_score"),
                "reasons": scored.get("reasons"),
            })
            continue
        if stance not in BULLISH_STANCES:
            audit.append({
                "symbol": sym,
                "decision": "rejected",
                "reason": f"Stance '{stance}' not bullish enough",
                "composite_score": composite,
                "stance": stance,
                "pick_score": scored.get("pick_score"),
                "reasons": scored.get("reasons"),
            })
            continue
        price = float(scored.get("price") or row.get("price") or 0)
        if price <= 0:
            audit.append({
                "symbol": sym,
                "decision": "rejected",
                "reason": "No valid price for sizing",
                "composite_score": composite,
                "stance": stance,
            })
            continue
        if sym in selected:
            pick = next(p for p in picks if str(p.get("symbol") or "").upper() == sym)
            audit.append({
                "symbol": sym,
                "decision": "selected",
                "reason": pick.get("fit_reason") or "Top ranked by expected profit",
                "composite_score": composite,
                "stance": stance,
                "pick_score": pick.get("pick_score"),
                "expected_profit_inr": pick.get("expected_profit_inr"),
                "notional_inr": pick.get("notional_inr"),
                "quantity": pick.get("quantity"),
                "reasons": pick.get("reasons"),
            })
        elif sym in candidate_syms:
            cand = next(c for c in candidates if str(c.get("symbol") or "").upper() == sym)
            audit.append({
                "symbol": sym,
                "decision": "skipped",
                "reason": "Passed filters but lower rank / budget slots full",
                "composite_score": composite,
                "stance": stance,
                "pick_score": cand.get("pick_score"),
                "expected_profit_inr": cand.get("expected_profit_inr"),
                "reasons": cand.get("reasons"),
            })
        else:
            audit.append({
                "symbol": sym,
                "decision": "rejected",
                "reason": "Did not fit per-order or remaining daily budget",
                "composite_score": composite,
                "stance": stance,
                "pick_score": scored.get("pick_score"),
                "reasons": scored.get("reasons"),
            })
    return audit


def log_cycle_record(
    session_id: str,
    *,
    cycle_id: str,
    pick_mode: str,
    market_open: bool,
    risk_snapshot: dict[str, Any],
    guard: dict[str, Any],
    pick_result: dict[str, Any],
    universe_audit: list[dict[str, Any]],
    rag_context: list[dict[str, Any]],
    cap_reason: str = "",
    notes: list[str] | None = None,
) -> dict[str, Any]:
    """Persist one full scheduler cycle with every decision the system made."""
    record = {
        "id": cycle_id,
        "at": _now(),
        "pick_mode": pick_mode,
        "market_open": market_open,
        "risk_snapshot": {
            k: risk_snapshot.get(k)
            for k in (
                "realized_pnl_inr",
                "unrealized_pnl_inr",
                "halted",
                "halt_reason",
                "buy_notional_used_inr",
                "buy_notional_cap_inr",
                "open_positions_count",
            )
            if k in risk_snapshot
        },
        "guard": {
            "eod": guard.get("eod"),
            "actions": [sanitize_pick_row(a) for a in (guard.get("actions") or [])],
        },
        "pick_result": sanitize_pick_result(pick_result),
        "universe_audit": universe_audit,
        "rag_context": rag_context,
        "cap_reason": cap_reason or None,
        "notes": notes or [],
    }

    log_event(
        session_id,
        event_type="cycle_complete",
        title=f"Cycle {cycle_id[-6:]} — {len(universe_audit)} symbols audited",
        detail={
            "cycle_id": cycle_id,
            "selected": [a for a in universe_audit if a.get("decision") == "selected"],
            "skipped": [a for a in universe_audit if a.get("decision") == "skipped"],
            "rejected": [a for a in universe_audit if a.get("decision") == "rejected"],
            "guard_actions": len(guard.get("actions") or []),
            "trades_attempted": len(pick_result.get("trades") or []),
            "timing_blocked": len(pick_result.get("timing_blocked") or []),
            "realized_pnl_inr": risk_snapshot.get("realized_pnl_inr"),
        },
        level="action",
        cycle_id=cycle_id,
    )

    from trading.session_autopilot import _find_session, _load_store, _save_store
    from trading.store_lock import LOCK

    with LOCK:
        store = _load_store()
        session = _find_session(store, session_id)
        if session:
            session.setdefault("cycles", []).insert(0, record)
            session["cycles"] = session["cycles"][:300]
            _save_store(store)
    return record
