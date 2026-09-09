"""All-day autopilot session — curated stock list or agent auto-pick."""
from __future__ import annotations

import json
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal, Optional

from config import BASE_DIR
from trading.config_store import load_trading_config, save_trading_config
from trading.market_hours import is_trading_window, nse_session_info
from trading.paper_ledger import daily_stats, ledger_summary, open_positions
from trading.pick_learning import log_session_trade, retrieve_pick_lessons
from trading.position_guard import monitor_open_positions
from trading.risk import get_risk_snapshot

SESSION_PATH = BASE_DIR / "data" / "trading" / "sessions.json"
PickMode = Literal["curated_list", "agent_auto"]


def _session_quote_fn():
    from trading.scheduler import _quote_symbol

    def _quote(sym: str) -> float:
        try:
            px = float(_quote_symbol(sym, "auto"))
            return px if px > 0 else 0.0
        except Exception:
            return 0.0

    return _quote


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_store() -> dict[str, Any]:
    from trading.json_cache import load_json_cached

    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not SESSION_PATH.exists():
        return {"active_session_id": None, "sessions": []}
    return load_json_cached(SESSION_PATH, default={"active_session_id": None, "sessions": []})


def _save_store(data: dict[str, Any]) -> None:
    from trading.json_cache import invalidate_json_cache
    from trading.json_store import dumps_pretty

    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    SESSION_PATH.write_text(dumps_pretty(data), encoding="utf-8")
    invalidate_json_cache(SESSION_PATH)


def compact_sessions_store(*, max_bytes: int = 2_000_000) -> dict[str, Any]:
    """Backward-compatible wrapper — full trim via session_maintenance."""
    from trading.session_maintenance import trim_session_stores

    return trim_session_stores(max_sessions=25, max_events=2000)


def _find_session(data: dict[str, Any], session_id: str) -> Optional[dict[str, Any]]:
    for row in data.get("sessions") or []:
        if row.get("id") == session_id:
            return row
    return None


def _migrate_active_ids(data: dict[str, Any]) -> None:
    """Back-compat: single active_session_id → active_session_ids list."""
    if "active_session_ids" not in data:
        sid = data.get("active_session_id")
        data["active_session_ids"] = [sid] if sid else []


def _active_sessions(data: dict[str, Any]) -> list[dict[str, Any]]:
    _migrate_active_ids(data)
    out: list[dict[str, Any]] = []
    for sid in data.get("active_session_ids") or []:
        row = _find_session(data, str(sid))
        if row and row.get("status") == "active":
            out.append(row)
    if not out and data.get("active_session_id"):
        row = _find_session(data, str(data["active_session_id"]))
        if row and row.get("status") == "active":
            out.append(row)
    return out


def get_active_session_id() -> Optional[str]:
    """Primary active session id (first desk)."""
    ids = get_active_session_ids()
    return ids[0] if ids else None


def get_active_session_ids() -> list[str]:
    data = _load_store()
    return [str(s.get("id") or "") for s in _active_sessions(data) if s.get("id")]


def _session_realized_pnl(session_id: str) -> float:
    from trading.pick_learning import list_session_trades

    return round(
        sum(
            float(t.get("pnl_inr") or 0)
            for t in list_session_trades(session_id, limit=500)
            if t.get("side") == "sell" and t.get("pnl_inr") is not None
        ),
        2,
    )


def _session_buy_notional(session_id: str) -> float:
    from trading.pick_learning import list_session_trades

    return round(
        sum(
            float(t.get("notional_inr") or (t.get("price") or 0) * (t.get("quantity") or 0))
            for t in list_session_trades(session_id, limit=500)
            if str(t.get("side") or "").lower() == "buy"
        ),
        2,
    )


def _session_open_symbols(session_id: str) -> set[str]:
    from trading.pick_learning import list_session_trades

    net: dict[str, int] = {}
    for t in list_session_trades(session_id, limit=500):
        sym = str(t.get("symbol") or "").upper()
        qty = int(t.get("quantity") or 0)
        if not sym or qty <= 0:
            continue
        if str(t.get("side") or "").lower() == "buy":
            net[sym] = net.get(sym, 0) + qty
        elif str(t.get("side") or "").lower() == "sell":
            net[sym] = net.get(sym, 0) - qty
    return {s for s, q in net.items() if q > 0}


def _deactivate_session(data: dict[str, Any], session_id: str) -> list[str]:
    """Remove session from active list; return remaining active ids."""
    _migrate_active_ids(data)
    ids = [str(i) for i in (data.get("active_session_ids") or []) if str(i) != session_id]
    data["active_session_ids"] = ids
    data["active_session_id"] = ids[0] if ids else None
    return ids


def _patch_session(session_id: str, **fields: Any) -> None:
    """Update specific session fields without clobbering concurrent writes."""
    from trading.store_lock import LOCK

    with LOCK:
        store = _load_store()
        session = _find_session(store, session_id)
        if not session:
            return
        session.update(fields)
        _save_store(store)


def _hydrate_session(session: dict[str, Any]) -> dict[str, Any]:
    """Merge live trade/event counts when sessions.json is stale."""
    from trading.pick_learning import list_session_trades
    from trading.session_history import list_session_events

    sid = str(session.get("id") or "")
    if not sid:
        return session
    trades = list_session_trades(sid, limit=500)
    events = list_session_events(sid, limit=500)
    cycle_events = list_session_events(sid, limit=500, event_type="cycle_complete")
    out = dict(session)
    out["trade_count"] = len(trades)
    out["event_count"] = len(events)
    out["cycle_count"] = len(cycle_events) or len(session.get("cycles") or [])
    sell_pnl = sum(float(t.get("pnl_inr") or 0) for t in trades if t.get("side") == "sell" and t.get("pnl_inr") is not None)
    # Per-session P&L only — never use global day ledger in dual desk (each desk has its own budget).
    out["realized_pnl_inr"] = round(sell_pnl, 2)
    buy_notional = sum(
        float(t.get("notional_inr") or (t.get("price") or 0) * (t.get("quantity") or 0))
        for t in trades
        if str(t.get("side") or "").lower() == "buy"
    )
    out["buy_notional_inr"] = round(buy_notional, 2) if buy_notional else 0.0
    from trading.paper_ledger import open_positions
    from trading.risk import compute_unrealized_pnl

    open_pos = open_positions("mis", session_id=sid)
    out["open_position_count"] = len(open_pos)
    unrealized = compute_unrealized_pnl(_session_quote_fn(), session_id=sid)
    out["unrealized_pnl_inr"] = unrealized
    out["net_pnl_inr"] = round(float(out["realized_pnl_inr"]) + unrealized, 2)
    return out


def _orphan_desk_pnl(active_ids: set[str]) -> dict[str, Any]:
    """P&L on open MIS positions not tied to any active desk session."""
    from trading.paper_ledger import open_positions

    quote_fn = _session_quote_fn()
    positions = [
        p for p in open_positions("mis")
        if str(p.get("session_id") or "") not in active_ids
    ]
    if not positions:
        return {
            "position_count": 0,
            "realized_pnl_inr": 0.0,
            "unrealized_pnl_inr": 0.0,
            "net_pnl_inr": 0.0,
            "symbols": [],
            "positions": [],
        }
    total = 0.0
    symbols: list[str] = []
    detail: list[dict[str, Any]] = []
    for pos in positions:
        qty = int(pos.get("quantity") or 0)
        entry = float(pos.get("avg_price") or pos.get("avg_entry") or 0)
        if qty <= 0 or entry <= 0:
            continue
        sym = str(pos.get("symbol") or "")
        mark = entry
        try:
            px = float(quote_fn(sym))
            if px > 0:
                mark = px
        except Exception:
            pass
        unreal = round((mark - entry) * qty, 2)
        total += unreal
        if sym:
            symbols.append(sym)
        detail.append({
            "symbol": sym,
            "quantity": qty,
            "session_id": str(pos.get("session_id") or ""),
            "avg_price": round(entry, 2),
            "unrealized_pnl_inr": unreal,
        })
    unrealized = round(total, 2)
    return {
        "position_count": len(positions),
        "realized_pnl_inr": 0.0,
        "unrealized_pnl_inr": unrealized,
        "net_pnl_inr": unrealized,
        "symbols": symbols,
        "positions": detail,
    }


def list_orphan_positions(*, active_session_ids: set[str] | None = None) -> list[dict[str, Any]]:
    """Open MIS legs outside active desk sessions."""
    from trading.paper_ledger import open_positions

    active = {str(s) for s in (active_session_ids or []) if s}
    return [
        p for p in open_positions("mis")
        if str(p.get("session_id") or "") not in active
    ]


def square_orphan_positions(
    *,
    active_session_ids: set[str] | None = None,
    reason: str = "pre_restart_square",
) -> dict[str, Any]:
    """Square off MIS positions not tied to any active desk."""
    from trading.paper_ledger import close_orphan_mis_positions

    active = {str(s) for s in (active_session_ids or []) if s}
    return close_orphan_mis_positions(active_session_ids=active, reason=reason)


def ensure_flat_before_restart(
    *,
    active_session_ids: set[str] | None = None,
    auto_square: bool = True,
) -> dict[str, Any]:
    """
    Block or auto-square open MIS positions from prior/stopped desks before starting/restarting.
    Active desk legs are never touched.
    """
    active = {str(s) for s in (active_session_ids or []) if s}
    orphan = list_orphan_positions(active_session_ids=active)
    if not orphan:
        return {"ok": True, "squared": 0, "closed": []}

    orphan_pnl = _orphan_desk_pnl(active)
    if not auto_square:
        syms = ", ".join(sorted({str(p.get("symbol") or "") for p in orphan if p.get("symbol")}))
        return {
            "ok": False,
            "error": (
                f"Square all legacy positions before restart ({len(orphan)} open: {syms}). "
                "Use Square orphans or stop sessions with flatten enabled."
            ),
            "orphan_pnl": orphan_pnl,
            "orphan_count": len(orphan),
        }

    result = square_orphan_positions(active_session_ids=active, reason="pre_restart_square")
    return {
        "ok": True,
        "squared": int(result.get("count") or 0),
        "closed": result.get("closed") or [],
        "orphan_pnl_before": orphan_pnl,
    }


def cross_desk_held_symbols(session_id: str) -> set[str]:
    """Symbols held by other active desks — agent should not duplicate exposure."""
    data = _load_store()
    held: set[str] = set()
    for row in _active_sessions(data):
        sid = str(row.get("id") or "")
        if not sid or sid == session_id:
            continue
        held |= _session_open_symbols(sid)
    return held


def _resolve_display_session(data: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Best session row for UI — active first, else most recent."""
    active = _active_session(data)
    if active:
        return _hydrate_session(active)
    sessions = data.get("sessions") or []
    for row in sessions:
        if row.get("status") in {"stopped", "completed"}:
            return _hydrate_session(row)
    if sessions:
        return _hydrate_session(sessions[0])
    return None


def _sync_config_with_store(data: dict[str, Any]) -> None:
    """Keep config.autopilot aligned with sessions.json."""
    active_list = _active_sessions(data)
    cfg = load_trading_config()
    ap = cfg.get("autopilot") or {}
    if active_list:
        ids = [s["id"] for s in active_list]
        patch: dict[str, Any] = {
            "session_active": True,
            "session_id": ids[0],
            "active_session_ids": ids,
            "dual_mode": len(active_list) > 1,
        }
        if len(active_list) > 1:
            patch["pick_mode"] = "dual_desk"
        elif len(active_list) == 1:
            patch["pick_mode"] = active_list[0].get("pick_mode")
        if ap.get("session_id") != ids[0] or not ap.get("session_active"):
            save_trading_config({"autopilot": patch})
    elif ap.get("session_active") or ap.get("session_id"):
        patch: dict[str, Any] = {
            "session_active": False,
            "session_id": None,
            "active_session_ids": [],
            "dual_mode": False,
        }
        prefs = ap.get("dual_desk_preferences")
        if prefs:
            patch["dual_desk_preferences"] = prefs
            if (prefs.get("curated") or {}).get("symbols"):
                patch["curated_symbols"] = prefs["curated"]["symbols"]
            patch["pick_mode"] = "dual_desk"
        save_trading_config({"autopilot": patch})


def _active_session(data: dict[str, Any]) -> Optional[dict[str, Any]]:
    sessions = _active_sessions(data)
    return sessions[0] if sessions else None


def start_session(
    *,
    pick_mode: PickMode,
    symbols: Optional[list[str]] = None,
    max_spend_inr: float = 200_000,
    max_profit_inr: float = 30_000,
    max_loss_inr: float = 15_000,
    max_concurrent_picks: int = 3,
    persist_trading_config: bool = True,
    auto_square_orphans: bool = True,
) -> dict[str, Any]:
    curated_raw = [s for s in (symbols or []) if s and str(s).strip()]
    try:
        from trading.symbol_validate import CURATED_SYMBOLS_MAX, normalize_symbol_list

        curated = normalize_symbol_list(
            curated_raw,
            max_count=CURATED_SYMBOLS_MAX,
            min_count=1 if pick_mode == "curated_list" else 0,
        )
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    if pick_mode == "curated_list" and not curated:
        return {"ok": False, "error": f"Select 1–{CURATED_SYMBOLS_MAX} stocks for curated-list mode."}

    data = _load_store()
    _migrate_active_ids(data)
    active_list = _active_sessions(data)
    if active_list:
        modes = {str(s.get("pick_mode") or "") for s in active_list}
        if pick_mode in modes:
            return {
                "ok": False,
                "error": f"A {pick_mode.replace('_', ' ')} session is already running. Stop it first or use dual desk.",
            }
        if len(active_list) >= 2:
            return {"ok": False, "error": "Maximum 2 desks (one AI auto + one curated list). Stop one first."}

    active_ids = {str(s.get("id") or "") for s in active_list}
    flat = ensure_flat_before_restart(active_session_ids=active_ids, auto_square=auto_square_orphans)
    if not flat.get("ok"):
        return {
            "ok": False,
            "error": flat.get("error"),
            "orphan_pnl": flat.get("orphan_pnl"),
            "orphan_count": flat.get("orphan_count"),
        }

    # Clear stale config from a prior session that did not shut down cleanly.
    cfg = load_trading_config()
    ap = cfg.get("autopilot") or {}
    if ap.get("session_active") and ap.get("session_id"):
        stale = _find_session(data, str(ap.get("session_id")))
        if stale and stale.get("status") == "active" and stale.get("id") != data.get("active_session_id"):
            stale["status"] = "stopped"
            stale["stopped_at"] = _now()
            stale["completion_reason"] = "replaced_by_new_session"
            data["active_session_id"] = None
            _save_store(data)

    session_id = f"sess-{uuid.uuid4().hex[:12]}"
    session = {
        "id": session_id,
        "status": "active",
        "pick_mode": pick_mode,
        "curated_symbols": curated,
        "max_concurrent_picks": max(1, min(10, int(max_concurrent_picks))),
        "caps": {
            "max_daily_notional_inr": float(max_spend_inr),
            "max_profit_inr": float(max_profit_inr),
            "max_intraday_loss_inr": float(max_loss_inr),
        },
        "started_at": _now(),
        "stopped_at": None,
        "completed_at": None,
        "completion_reason": None,
        "realized_pnl_inr": 0.0,
        "trades": [],
        "cycles": [],
        "events": [],
    }
    data.setdefault("sessions", []).insert(0, session)
    data["sessions"] = data["sessions"][:100]
    _migrate_active_ids(data)
    data.setdefault("active_session_ids", [])
    if session_id not in data["active_session_ids"]:
        data["active_session_ids"].append(session_id)
    data["active_session_id"] = data["active_session_ids"][0]
    _save_store(data)

    is_dual = len(data["active_session_ids"]) > 1
    combined_spend = float(max_spend_inr)
    if is_dual:
        combined_spend = sum(
            float(_find_session(data, sid).get("caps", {}).get("max_daily_notional_inr") or 0)
            for sid in data["active_session_ids"]
            if _find_session(data, sid)
        )
        combined_loss = sum(
            float(_find_session(data, sid).get("caps", {}).get("max_intraday_loss_inr") or 0)
            for sid in data["active_session_ids"]
            if _find_session(data, sid)
        )
        combined_profit = sum(
            float(_find_session(data, sid).get("caps", {}).get("max_profit_inr") or 0)
            for sid in data["active_session_ids"]
            if _find_session(data, sid)
        )
    else:
        combined_loss = float(max_loss_inr)
        combined_profit = float(max_profit_inr)

    risk_patch: dict[str, Any] = {
        "max_daily_notional_inr": combined_spend,
        "max_profit_inr": max(float(max_profit_inr), combined_profit if is_dual else float(max_profit_inr)),
        "max_intraday_loss_inr": combined_loss if is_dual else float(max_loss_inr),
        "max_open_positions": session["max_concurrent_picks"] * len(data["active_session_ids"]),
    }
    cfg = load_trading_config()
    if int((cfg.get("risk") or {}).get("max_orders_per_day") or 5) < 30:
        risk_patch["max_orders_per_day"] = 30

    if persist_trading_config:
        prev_ap = cfg.get("autopilot") or {}
        autopilot_patch: dict[str, Any] = {
            "enabled": True,
            "session_active": True,
            "dual_mode": is_dual,
            "pick_mode": "dual_desk" if is_dual else pick_mode,
            "max_concurrent_picks": session["max_concurrent_picks"],
            "session_id": session_id,
            "active_session_ids": list(data["active_session_ids"]),
            "paper_autopilot": True,
        }
        if pick_mode == "curated_list":
            autopilot_patch["curated_symbols"] = curated
            save_trading_config({
                "risk": risk_patch,
                "autopilot": autopilot_patch,
                "watchlist": curated,
            })
        else:
            # Agent desk — keep user's curated list / watchlist intact.
            autopilot_patch["curated_symbols"] = prev_ap.get("curated_symbols") or cfg.get("watchlist") or []
            save_trading_config({
                "risk": risk_patch,
                "autopilot": autopilot_patch,
            })

    from trading.session_history import log_event

    log_event(
        session_id,
        event_type="session_start",
        title=f"Session started — {pick_mode.replace('_', ' ')}",
        detail={
            "pick_mode": pick_mode,
            "curated_symbols": curated,
            "max_concurrent_picks": session["max_concurrent_picks"],
            "caps": session["caps"],
            "dual_desk": is_dual,
        },
        level="action",
    )

    from trading.mac_sleep_guard import sleep_guard_status, start_mac_sleep_guard

    sleep_guard = sleep_guard_status()
    if not sleep_guard.get("active"):
        sleep_guard = start_mac_sleep_guard(session_id=session_id, reason="session_start")
        if sleep_guard.get("started"):
            log_event(
                session_id,
                event_type="mac_sleep_guard",
                title=f"Mac sleep disabled until {sleep_guard.get('wake_until_ist')} IST",
                detail=sleep_guard,
                level="action",
            )

    return {"ok": True, "session": session, "mac_sleep_guard": sleep_guard, "dual_mode": is_dual, "pre_restart_square": flat}


def start_dual_session(
    *,
    agent_max_spend_inr: float = 1_000_000,
    agent_max_profit_inr: float = 100_000,
    agent_max_loss_inr: float = 15_000,
    agent_max_concurrent_picks: int = 5,
    curated_symbols: Optional[list[str]] = None,
    curated_max_spend_inr: float = 1_000_000,
    curated_max_profit_inr: float = 100_000,
    curated_max_loss_inr: float = 15_000,
    curated_max_concurrent_picks: int = 5,
    auto_square_orphans: bool = True,
) -> dict[str, Any]:
    """Start AI auto-pick desk + curated-list desk in parallel (separate budgets)."""
    data = _load_store()
    if _active_sessions(data):
        return {"ok": False, "error": "Stop existing session(s) before starting dual desk."}

    flat = ensure_flat_before_restart(active_session_ids=set(), auto_square=auto_square_orphans)
    if not flat.get("ok"):
        return {
            "ok": False,
            "error": flat.get("error"),
            "orphan_pnl": flat.get("orphan_pnl"),
            "orphan_count": flat.get("orphan_count"),
        }

    dual_prefs = {
        "agent": {
            "max_spend_inr": float(agent_max_spend_inr),
            "max_profit_inr": float(agent_max_profit_inr),
            "max_loss_inr": float(agent_max_loss_inr),
            "max_concurrent_picks": int(agent_max_concurrent_picks),
        },
        "curated": {
            "symbols": list(curated_symbols or []),
            "max_spend_inr": float(curated_max_spend_inr),
            "max_profit_inr": float(curated_max_profit_inr),
            "max_loss_inr": float(curated_max_loss_inr),
            "max_concurrent_picks": int(curated_max_concurrent_picks),
        },
    }

    agent = start_session(
        pick_mode="agent_auto",
        max_spend_inr=agent_max_spend_inr,
        max_profit_inr=agent_max_profit_inr,
        max_loss_inr=agent_max_loss_inr,
        max_concurrent_picks=agent_max_concurrent_picks,
        persist_trading_config=False,
        auto_square_orphans=False,
    )
    if not agent.get("ok"):
        return agent

    curated = start_session(
        pick_mode="curated_list",
        symbols=curated_symbols,
        max_spend_inr=curated_max_spend_inr,
        max_profit_inr=curated_max_profit_inr,
        max_loss_inr=curated_max_loss_inr,
        max_concurrent_picks=curated_max_concurrent_picks,
        persist_trading_config=False,
        auto_square_orphans=False,
    )
    if not curated.get("ok"):
        stop_session(session_id=agent["session"]["id"], reason="dual_start_failed")
        return curated

    store = _load_store()
    ids = store.get("active_session_ids") or []
    combined_spend = agent_max_spend_inr + curated_max_spend_inr
    combined_loss = float(agent_max_loss_inr) + float(curated_max_loss_inr)
    combined_profit = float(agent_max_profit_inr) + float(curated_max_profit_inr)
    curated_syms = list((curated.get("session") or {}).get("curated_symbols") or [])
    cfg = load_trading_config()
    save_trading_config({
        "risk": {
            "max_daily_notional_inr": combined_spend,
            "max_open_positions": int(agent_max_concurrent_picks) + int(curated_max_concurrent_picks),
            "max_orders_per_day": max(30, int((cfg.get("risk") or {}).get("max_orders_per_day") or 5)),
            "max_intraday_loss_inr": combined_loss,
            "max_profit_inr": max(float((cfg.get("risk") or {}).get("max_profit_inr") or 0), combined_profit),
        },
        "autopilot": {
            "enabled": True,
            "session_active": True,
            "dual_mode": True,
            "pick_mode": "dual_desk",
            "active_session_ids": ids,
            "session_id": ids[0] if ids else agent["session"]["id"],
            "curated_symbols": curated_syms,
            "dual_desk_preferences": dual_prefs,
            "paper_autopilot": True,
        },
        "watchlist": curated_syms,
    })
    return {
        "ok": True,
        "dual_mode": True,
        "sessions": [agent["session"], curated["session"]],
        "agent_session": agent["session"],
        "curated_session": curated["session"],
        "combined_budget_inr": combined_spend,
        "dual_desk_preferences": dual_prefs,
    }


def _sync_session_from_stores(session_id: str) -> None:
    """Update session summary counts — trades/events live in pick_log + session_events.json."""
    from trading.pick_learning import list_session_trades
    from trading.session_history import list_session_events

    store = _load_store()
    session = _find_session(store, session_id)
    if not session:
        return
    session["trade_count"] = len(list_session_trades(session_id, limit=500))
    session["cycle_count"] = len(list_session_events(session_id, event_type="cycle_complete", limit=500))
    session.pop("trades", None)
    session.pop("events", None)
    _save_store(store)


def stop_session(*, session_id: Optional[str] = None, reason: str = "user_stop") -> dict[str, Any]:
    data = _load_store()
    _migrate_active_ids(data)
    active_list = _active_sessions(data)
    if not active_list:
        cfg = load_trading_config()
        ap = cfg.get("autopilot") or {}
        patch: dict[str, Any] = {
            "session_active": False,
            "session_id": None,
            "active_session_ids": [],
            "dual_mode": False,
        }
        prefs = ap.get("dual_desk_preferences")
        if prefs:
            patch["dual_desk_preferences"] = prefs
            if (prefs.get("curated") or {}).get("symbols"):
                patch["curated_symbols"] = prefs["curated"]["symbols"]
            patch["pick_mode"] = "dual_desk"
        save_trading_config({"autopilot": patch})
        return {"ok": True, "stopped": False, "message": "No active session."}

    if session_id is None and len(active_list) > 1:
        stopped_sessions = []
        for row in list(active_list):
            result = stop_session(session_id=row["id"], reason=reason)
            if result.get("session"):
                stopped_sessions.append(result["session"])
        return {"ok": True, "stopped": True, "all": True, "sessions": stopped_sessions}

    session = None
    if session_id:
        session = _find_session(data, session_id)
        if not session or session.get("status") != "active":
            return {"ok": False, "error": "Session not found or not active."}
    else:
        session = active_list[0]

    session["status"] = "stopped"
    session["stopped_at"] = _now()
    session["completion_reason"] = reason
    session["realized_pnl_inr"] = _session_realized_pnl(session["id"])

    from trading.paper_ledger import close_session_mis_positions

    square_result = close_session_mis_positions(
        session_id=str(session["id"]),
        reason="session_stop_square",
    )

    remaining_ids = _deactivate_session(data, session["id"])
    _save_store(data)
    _sync_session_from_stores(session["id"])

    from trading.session_history import log_event
    from trading.pick_learning import list_session_trades

    log_event(
        session["id"],
        event_type="session_stop",
        title=f"Session stopped — {reason}",
        detail={
            "reason": reason,
            "realized_pnl_inr": session["realized_pnl_inr"],
            "trade_count": len(list_session_trades(session["id"], limit=500)),
            "cycle_count": session.get("cycle_count") or 0,
            "squared_on_stop": int(square_result.get("count") or 0),
        },
        level="complete",
    )

    from trading.session_report import finalize_session_report

    finalize_session_report(session, reason=reason, force=reason == "user_stop")
    store = _load_store()
    session = _find_session(store, session["id"]) or session
    _save_store(store)

    if remaining_ids:
        _sync_config_with_store(store)
        combined = sum(
            float(_find_session(store, sid).get("caps", {}).get("max_daily_notional_inr") or 0)
            for sid in remaining_ids
            if _find_session(store, sid)
        )
        save_trading_config({"risk": {"max_daily_notional_inr": combined}})
    else:
        cfg = load_trading_config()
        ap = cfg.get("autopilot") or {}
        patch: dict[str, Any] = {
            "session_active": False,
            "session_id": None,
            "active_session_ids": [],
            "dual_mode": False,
        }
        # Keep dual desk UI preferences + curated list after stop (do not wipe user selections).
        prefs = ap.get("dual_desk_preferences")
        if prefs:
            patch["dual_desk_preferences"] = prefs
            curated = (prefs.get("curated") or {})
            if curated.get("symbols"):
                patch["curated_symbols"] = curated["symbols"]
            patch["pick_mode"] = "dual_desk"
        save_trading_config({"autopilot": patch})

    from trading.mac_sleep_guard import stop_mac_sleep_guard

    sleep_guard = {"active": False}
    if not remaining_ids:
        sleep_guard = stop_mac_sleep_guard(reason=reason)
    return {
        "ok": True,
        "stopped": True,
        "session": session,
        "mac_sleep_guard": sleep_guard,
        "remaining_active": remaining_ids,
        "squared_on_stop": int(square_result.get("count") or 0),
    }


def _complete_session(session: dict[str, Any], reason: str, data: dict[str, Any]) -> None:
    session_id = str(session.get("id") or "")
    session["status"] = "completed"
    session["completed_at"] = _now()
    session["completion_reason"] = reason
    session["realized_pnl_inr"] = _session_realized_pnl(session_id)
    _sync_session_from_stores(session_id)
    store = _load_store()
    session = _find_session(store, session_id) or session
    from trading.session_history import log_event
    from trading.pick_learning import list_session_trades

    log_event(
        session_id,
        event_type="session_complete",
        title=f"Session completed — {reason}",
        detail={
            "reason": reason,
            "realized_pnl_inr": session["realized_pnl_inr"],
            "trade_count": len(list_session_trades(session_id, limit=500)),
            "cycle_count": session.get("cycle_count") or len(session.get("cycles") or []),
        },
        level="complete",
    )
    from trading.session_report import finalize_session_report

    finalize_session_report(session, reason=reason, force=True)
    remaining_ids = _deactivate_session(store, session_id)
    _save_store(store)
    if remaining_ids:
        _sync_config_with_store(store)
        combined = sum(
            float(_find_session(store, sid).get("caps", {}).get("max_daily_notional_inr") or 0)
            for sid in remaining_ids
            if _find_session(store, sid)
        )
        save_trading_config({"risk": {"max_daily_notional_inr": combined}})
    else:
        cfg = load_trading_config()
        ap = cfg.get("autopilot") or {}
        patch: dict[str, Any] = {
            "session_active": False,
            "session_id": None,
            "active_session_ids": [],
            "dual_mode": False,
        }
        # Keep dual desk UI preferences + curated list after stop (do not wipe user selections).
        prefs = ap.get("dual_desk_preferences")
        if prefs:
            patch["dual_desk_preferences"] = prefs
            curated = (prefs.get("curated") or {})
            if curated.get("symbols"):
                patch["curated_symbols"] = curated["symbols"]
            patch["pick_mode"] = "dual_desk"
        save_trading_config({"autopilot": patch})
        from trading.mac_sleep_guard import stop_mac_sleep_guard

        stop_mac_sleep_guard(reason=reason)


def session_status() -> dict[str, Any]:
    data = _load_store()
    _sync_config_with_store(data)
    session = _active_session(data)
    display = _resolve_display_session(data)
    cfg = load_trading_config()
    snap = get_risk_snapshot(_session_quote_fn())
    history = [
        {
            "id": s.get("id"),
            "status": s.get("status"),
            "pick_mode": s.get("pick_mode"),
            "started_at": s.get("started_at"),
            "stopped_at": s.get("stopped_at"),
            "realized_pnl_inr": s.get("realized_pnl_inr"),
            "trade_count": s.get("trade_count"),
        }
        for s in (data.get("sessions") or [])[:20]
    ]
    from trading.session_history import list_session_events

    display_id = (display or {}).get("id") or ""
    events: list[dict[str, Any]] = []
    if display_id:
        events = list_session_events(display_id, limit=100)
    elif session:
        events = list_session_events(session["id"], limit=100)
    from trading.mac_sleep_guard import sleep_guard_status
    from trading.trade_plan import intraday_rules_from_config, swing_rules_summary
    from trading.session_report import load_session_report, report_is_stale

    report_stale = bool(display_id and report_is_stale(display, load_session_report(display_id)))
    active_list = [_hydrate_session(s) for s in _active_sessions(data)]
    active_ids = {str(s.get("id") or "") for s in active_list}
    dual_pnl = {
        "realized_pnl_inr": round(sum(float(s.get("realized_pnl_inr") or 0) for s in active_list), 2),
        "unrealized_pnl_inr": round(sum(float(s.get("unrealized_pnl_inr") or 0) for s in active_list), 2),
        "net_pnl_inr": round(sum(float(s.get("net_pnl_inr") or 0) for s in active_list), 2),
    }
    orphan_pnl = _orphan_desk_pnl(active_ids)

    return {
        "active": bool(active_list),
        "dual_mode": len(active_list) > 1,
        "dual_desk_pnl": dual_pnl if len(active_list) > 1 else None,
        "desk_pnl": dual_pnl if active_list else None,
        "orphan_pnl": orphan_pnl if orphan_pnl.get("position_count") else None,
        "sessions": active_list,
        "session": active_list[0] if active_list else None,
        "display_session": display,
        "report_session_id": display_id,
        "report_stale": report_stale,
        "recent_events": events,
        "nse": nse_session_info(cfg),
        "premarket_plan": (session or display or {}).get("premarket_plan") if (session or display) else None,
        "intraday_rules": intraday_rules_from_config(cfg),
        "swing_rules": swing_rules_summary(),
        "config": {
            "pick_mode": (cfg.get("autopilot") or {}).get("pick_mode"),
            "curated_symbols": (cfg.get("autopilot") or {}).get("curated_symbols") or [],
            "max_concurrent_picks": (cfg.get("autopilot") or {}).get("max_concurrent_picks"),
            "dual_desk_preferences": (cfg.get("autopilot") or {}).get("dual_desk_preferences"),
            "dual_mode": len(active_list) > 1,
        },
        "risk_snapshot": snap,
        "ledger": ledger_summary(),
        "history": history,
        "mac_sleep_guard": sleep_guard_status(),
    }


def _today_ist() -> str:
    from trading.market_hours import _ist_now
    return _ist_now().strftime("%Y-%m-%d")


def run_premarket_analysis(
    session: dict[str, Any],
    *,
    analyze_fn: Callable[[str], dict[str, Any]],
    quote_fn: Callable[[str], float],
    cycle_id: str = "",
) -> dict[str, Any]:
    """
    09:00–09:15 IST — score universe, learn timing, build trade plan (no orders).
    """
    from trading.session_history import log_event, sanitize_pick_row
    from trading.trade_plan import enrich_row_with_plan, intraday_rules_from_config

    cfg = load_trading_config()
    rules = intraday_rules_from_config(cfg)

    session_id = session["id"]
    today = _today_ist()
    if session.get("premarket_done_date") == today:
        return {"skipped": True, "reason": "premarket_already_done", "plan": session.get("premarket_plan")}

    pick_mode = str(session.get("pick_mode") or "curated_list")
    max_picks = int(session.get("max_concurrent_picks") or 3)
    result: dict[str, Any] = {"phase": "pre_market", "pick_mode": pick_mode, "steps": []}

    log_event(
        session_id,
        event_type="premarket_begin",
        title="Pre-market analysis started (09:00 IST window)",
        detail={"pick_mode": pick_mode, "cycle_id": cycle_id},
        level="action",
        cycle_id=cycle_id,
    )

    if pick_mode == "agent_auto":
        from trading.morning_scan import run_morning_scan

        scan = run_morning_scan(force=False)
        result["steps"].append({"morning_scan": scan})
        scan_rows = list((scan or {}).get("rows") or [])
        curated_syms = list(
            (session.get("curated_symbols") or [])
            or (cfg.get("autopilot") or {}).get("curated_symbols")
            or []
        )
        if scan_rows:
            from trading.agent_learning import agent_premarket_learn

            agent_learn = agent_premarket_learn(scan_rows, curated_symbols=curated_syms)
            result["steps"].append({"agent_timing_learn": agent_learn})
    else:
        symbols = list(session.get("curated_symbols") or [])
        from trading.symbol_validate import CURATED_SYMBOLS_MAX
        from trading.timing_intelligence import learn_timing_batch

        if symbols:
            timing = learn_timing_batch(symbols[:CURATED_SYMBOLS_MAX], feed_rag=True)
            result["steps"].append({"timing_learn": timing})

    from trading.agent_picker import run_autonomous_stock_picks, run_given_stock_trades

    if pick_mode == "agent_auto":
        plan = run_autonomous_stock_picks(execute=False, max_picks=max_picks, session=session)
    else:
        plan = run_given_stock_trades(
            execute=False,
            max_picks=max_picks,
            symbols=list(session.get("curated_symbols") or []),
            session=session,
        )
    result["plan"] = plan

    symbol_entries: list[dict[str, Any]] = []
    for row in plan.get("universe_audit") or plan.get("candidates") or []:
        sym = str(row.get("symbol") or "")
        if not sym:
            continue
        timing_gate = None
        try:
            from trading.latency_compensation import compensated_entry_allowed

            timing_gate = compensated_entry_allowed(symbol=sym)
        except Exception:
            pass
        symbol_entries.append(
            enrich_row_with_plan(
                {
                    "symbol": sym,
                    "pick_score": row.get("pick_score"),
                    "composite_score": row.get("composite_score"),
                    "stance": row.get("stance"),
                    "expected_profit_inr": row.get("expected_profit_inr"),
                    "price": row.get("price"),
                    "quantity": row.get("quantity"),
                    "notional_inr": row.get("notional_inr"),
                    "decision": row.get("decision", "candidate"),
                    "reason": row.get("reason") or row.get("fit_reason"),
                    "entry_timing_now": timing_gate,
                },
                cfg=cfg,
                timing_gate=timing_gate,
            )
        )

    planned_with_plan = []
    for p in (plan.get("picks") or []):
        sym = str(p.get("symbol") or "")
        tg = None
        try:
            from trading.latency_compensation import compensated_entry_allowed

            tg = compensated_entry_allowed(symbol=sym)
        except Exception:
            pass
        planned_with_plan.append(
            sanitize_pick_row(enrich_row_with_plan(p, cfg=cfg, timing_gate=tg))
        )

    premarket_plan = {
        "at": _now(),
        "trade_date_ist": today,
        "pick_mode": pick_mode,
        "intraday_rules": rules,
        "planned_picks": planned_with_plan,
        "candidates": [sanitize_pick_row(c) for c in (plan.get("candidates") or [])[:15]],
        "universe_audit": plan.get("universe_audit") or [],
        "symbol_entries": symbol_entries,
        "budget": plan.get("budget"),
        "trading_starts_at": "09:15 IST",
        "strategy": "Poll until timing gate allows entry; exit on target/stop/EOD; re-enter after profit booked",
    }
    session["premarket_plan"] = premarket_plan
    session["premarket_done_date"] = today

    log_event(
        session_id,
        event_type="premarket_complete",
        title=f"Pre-market plan ready — {len(plan.get('picks') or [])} planned picks from {len(symbol_entries)} scored",
        detail={
            "planned_symbols": [p.get("symbol") for p in (plan.get("picks") or [])],
            "top_candidates": [c.get("symbol") for c in (plan.get("candidates") or [])[:5]],
            "trading_starts_at": "09:15 IST",
        },
        level="action",
        cycle_id=cycle_id,
    )
    _patch_session(
        session_id,
        premarket_plan=premarket_plan,
        premarket_done_date=today,
    )
    result["premarket_plan"] = premarket_plan
    return result


def sanitize_pick_row(row: dict[str, Any]) -> dict[str, Any]:
    from trading.session_history import sanitize_pick_row as _sanitize
    return _sanitize(row)


def _check_session_caps(session: dict[str, Any], quote_fn: Callable[[str], float]) -> Optional[str]:
    caps = session.get("caps") or {}
    session_id = str(session.get("id") or "")
    realized = _session_realized_pnl(session_id)
    max_profit = float(caps.get("max_profit_inr") or 0)
    max_loss = float(caps.get("max_intraday_loss_inr") or 0)

    if max_profit > 0 and realized >= max_profit:
        return "profit_cap_reached"
    if max_loss > 0 and realized <= -max_loss:
        return "loss_cap_reached"

    snap = get_risk_snapshot(quote_fn)
    if snap.get("halted"):
        return str(snap.get("halt_reason") or "trading_halted")
    return None


def run_session_cycle(
    *,
    analyze_fn: Callable[[str], dict[str, Any]],
    quote_fn: Callable[[str], float],
    session: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """One scheduler tick for an active all-day session."""
    from trading.session_history import (
        build_universe_audit,
        log_cycle_record,
        log_event,
        sanitize_pick_row,
    )

    data = _load_store()
    if session is None:
        session = _active_session(data)
    if not session:
        return {"skipped": True, "reason": "no_active_session"}

    cfg = load_trading_config()
    ap = cfg.get("autopilot") or {}
    if not ap.get("enabled") or not ap.get("session_active"):
        return {"skipped": True, "reason": "session_not_enabled"}

    cycle_id = f"cyc-{uuid.uuid4().hex[:10]}"
    session_id = session["id"]
    pick_mode = str(session.get("pick_mode") or "curated_list")
    nse_info = nse_session_info(cfg)
    phase = nse_info["phase"]
    trading = is_trading_window(cfg)
    snap = get_risk_snapshot(quote_fn)
    session_symbols = _session_open_symbols(session_id)
    session_realized = _session_realized_pnl(session_id)
    session_buy_used = _session_buy_notional(session_id)

    log_event(
        session_id,
        event_type="cycle_begin",
        title=f"Scheduler tick — {nse_info['label']}",
        detail={
            "cycle_id": cycle_id,
            "nse_phase": phase,
            "ist_time": nse_info.get("ist_time"),
            "realized_pnl_inr": session_realized,
            "buy_notional_used_inr": session_buy_used,
            "session_open_positions": len(session_symbols),
            "global_realized_pnl_inr": snap.get("realized_pnl_inr"),
            "global_buy_notional_used_inr": snap.get("buy_notional_used_inr"),
            "unrealized_pnl_inr": snap.get("unrealized_pnl_inr"),
            "open_positions": len(open_positions("mis", session_id=session_id)),
            "next_transition": nse_info.get("next_transition"),
        },
        level="info",
        cycle_id=cycle_id,
    )

    results: dict[str, Any] = {
        "session_id": session_id,
        "cycle_id": cycle_id,
        "pick_mode": pick_mode,
        "nse_phase": phase,
        "nse_info": nse_info,
        "steps": [],
    }

    force_eod = bool(nse_info.get("force_square_off"))
    guard = monitor_open_positions(
        quote_fn,
        force_eod=force_eod,
        symbols=session_symbols,
        session_id=session_id,
    )
    for action in guard.get("actions") or []:
        sym = str(action.get("symbol") or "")
        if action.get("order"):
            log_event(
                session_id,
                event_type="guard_exit",
                title=f"Sold {sym} — {action.get('reason')}",
                detail=sanitize_pick_row(action),
                level="action",
                symbol=sym,
                cycle_id=cycle_id,
            )
        elif action.get("skipped") or action.get("error"):
            log_event(
                session_id,
                event_type="guard_skip",
                title=f"Exit blocked for {sym} — {action.get('reason')}",
                detail=sanitize_pick_row(action),
                level="skip",
                symbol=sym,
                cycle_id=cycle_id,
            )
    if guard.get("actions"):
        results["steps"].append({"position_guard": guard})

    cap_reason = _check_session_caps(session, quote_fn)
    if cap_reason:
        log_event(
            session_id,
            event_type="cap_triggered",
            title=f"Session cap hit — {cap_reason}",
            detail={"reason": cap_reason, "risk_snapshot": snap},
            level="complete",
            cycle_id=cycle_id,
        )
        log_cycle_record(
            session_id,
            cycle_id=cycle_id,
            pick_mode=pick_mode,
            market_open=trading,
            risk_snapshot=snap,
            guard=guard,
            pick_result={},
            universe_audit=[],
            rag_context=[],
            cap_reason=cap_reason,
            notes=["Session ended due to cap"],
        )
        _complete_session(session, cap_reason, data)
        results["completed"] = True
        results["completion_reason"] = cap_reason
        return results

    pick_result: dict[str, Any] = {}
    universe_audit: list[dict[str, Any]] = []
    rag_context: list[dict[str, Any]] = []
    notes: list[str] = []

    if phase in {"weekend", "overnight"}:
        notes.append(f"nse_{phase} — waiting for 09:00 IST pre-market")
        log_event(
            session_id,
            event_type="session_waiting",
            title=nse_info["label"],
            detail=nse_info,
            level="info",
            cycle_id=cycle_id,
        )
    elif phase == "pre_market":
        notes.append("pre_market_analysis — no buys until 09:15 IST")
        if pick_mode == "agent_auto" and ap.get("auto_home_run_enabled", True):
            from trading.home_run_advisor import auto_apply_profit_profile

            auto_prof = auto_apply_profit_profile(cfg, pick_mode=pick_mode, session_id=session_id)
            if auto_prof.get("applied"):
                results["steps"].append({"auto_profit_profile": auto_prof})
                log_event(
                    session_id,
                    event_type="auto_profit_profile",
                    title=f"Auto-switched to {auto_prof.get('profile')} (score {(auto_prof.get('recommendation') or {}).get('score')})",
                    detail=auto_prof,
                    level="action",
                    cycle_id=cycle_id,
                )
                cfg = load_trading_config()
                ap = cfg.get("autopilot") or {}
        pre = run_premarket_analysis(
            session,
            analyze_fn=analyze_fn,
            quote_fn=quote_fn,
            cycle_id=cycle_id,
        )
        results["steps"].append({"premarket_analysis": pre})
        if nse_info.get("minutes_to_open"):
            log_event(
                session_id,
                event_type="entry_wait",
                title=f"Trading starts in {nse_info['minutes_to_open']} min — plan ready, polling",
                detail={
                    "minutes_to_open": nse_info["minutes_to_open"],
                    "planned_picks": (session.get("premarket_plan") or {}).get("planned_picks"),
                },
                level="info",
                cycle_id=cycle_id,
            )
    elif phase == "post_close":
        from trading.pick_learning import list_session_trades

        session_symbols = _session_open_symbols(session_id)
        post_close_n = int(session.get("post_close_cycles") or 0) + 1
        _patch_session(session_id, post_close_cycles=post_close_n)
        open_left = len(session_symbols)
        trade_count = len(list_session_trades(session_id, limit=500)) if session_id else 0
        notes.append(f"post_close — {open_left} open position(s) for this desk, attempt {post_close_n}")
        log_event(
            session_id,
            event_type="post_close",
            title=f"NSE closed (15:30 IST) — square-off attempt {post_close_n}",
            detail={**nse_info, "open_positions": open_left, "attempt": post_close_n},
            level="info",
            cycle_id=cycle_id,
        )
        # Auto-stop at market close when flat (default). Optional park-for-next-day if configured.
        park_next = bool(ap.get("session_park_for_next_day", False))
        if open_left == 0 and trade_count == 0 and post_close_n <= 1 and park_next:
            notes.append("post_close_park — no trades yet; session stays active until next open")
            log_event(
                session_id,
                event_type="session_waiting",
                title="Market closed — dual desk armed for next trading day",
                detail={**nse_info, "parked": True},
                level="info",
                cycle_id=cycle_id,
            )
            log_cycle_record(
                session_id,
                cycle_id=cycle_id,
                pick_mode=pick_mode,
                market_open=trading,
                risk_snapshot=snap,
                guard=guard,
                pick_result={},
                universe_audit=[],
                rag_context=[],
                notes=notes,
            )
            _patch_session(session_id, realized_pnl_inr=_session_realized_pnl(session_id))
            return results
        if open_left == 0 and ap.get("session_auto_stop_at_close", True):
            notes.append("auto_stop_at_close — flat at market close")
        if open_left and post_close_n < 15:
            log_cycle_record(
                session_id,
                cycle_id=cycle_id,
                pick_mode=pick_mode,
                market_open=trading,
                risk_snapshot=snap,
                guard=guard,
                pick_result={},
                universe_audit=[],
                rag_context=[],
                notes=notes + ["post_close_retry_until_flat"],
            )
            daily = daily_stats()
            _patch_session(session_id, realized_pnl_inr=_session_realized_pnl(session_id))
            return results
        if open_left:
            log_event(
                session_id,
                event_type="post_close",
                title=f"Completing session with {open_left} open position(s) after {post_close_n} attempts",
                detail={"open_positions": open_left},
                level="warn",
                cycle_id=cycle_id,
            )
        from trading.session_report import finalize_session_report

        finalize_session_report(session, reason="eod_market_close", force=True)
        log_cycle_record(
            session_id,
            cycle_id=cycle_id,
            pick_mode=pick_mode,
            market_open=trading,
            risk_snapshot=snap,
            guard=guard,
            pick_result={},
            universe_audit=[],
            rag_context=[],
            notes=notes + ["auto_stop_at_market_close"],
        )
        _complete_session(session, "eod_market_close", data)
        results["completed"] = True
        results["completion_reason"] = "eod_market_close"
        return results
    elif phase == "trading":
        max_picks = int(session.get("max_concurrent_picks") or 3)
        if ap.get("auto_home_run_enabled", True):
            from trading.home_run_advisor import auto_apply_profit_profile

            auto_prof = auto_apply_profit_profile(cfg, pick_mode=pick_mode, session_id=session_id)
            if auto_prof.get("applied"):
                results["steps"].append({"auto_profit_profile": auto_prof})
                log_event(
                    session_id,
                    event_type="auto_profit_profile",
                    title=f"Auto-switched to {auto_prof.get('profile')} — {(auto_prof.get('recommendation') or {}).get('headline', '')[:80]}",
                    detail=auto_prof,
                    level="action",
                    cycle_id=cycle_id,
                )
                cfg = load_trading_config()
                ap = cfg.get("autopilot") or {}
        from trading.agent_picker import run_autonomous_stock_picks, run_given_stock_trades

        if pick_mode == "agent_auto":
            pick_result = run_autonomous_stock_picks(execute=True, max_picks=max_picks, session=session)
        else:
            symbols = list(session.get("curated_symbols") or [])
            pick_result = run_given_stock_trades(
                execute=True,
                max_picks=max_picks,
                symbols=symbols,
                session=session,
            )

        universe_audit = list(pick_result.get("universe_audit") or [])
        results["steps"].append({"agent_picks": pick_result})

        executed = [t for t in (pick_result.get("trades") or []) if not t.get("skipped")]
        skipped = [t for t in (pick_result.get("trades") or []) if t.get("skipped")]
        if not executed and skipped:
            log_event(
                session_id,
                event_type="entry_wait",
                title=f"Polling — {len(skipped)} pick(s) waiting for correct entry timing",
                detail={
                    "skipped": [sanitize_pick_row(t) for t in skipped],
                    "window": (skipped[0].get("timing") or {}).get("window") if skipped else None,
                    "premarket_plan": [
                        p.get("symbol") for p in ((session.get("premarket_plan") or {}).get("planned_picks") or [])
                    ],
                },
                level="info",
                cycle_id=cycle_id,
            )

        for trade in pick_result.get("trades") or []:
            sym = str(trade.get("symbol") or "")
            if trade.get("skipped"):
                log_event(
                    session_id,
                    event_type="pick_skipped",
                    title=f"Buy skipped {sym} — {trade.get('reason') or 'timing/risk'}",
                    detail=sanitize_pick_row(trade),
                    level="skip",
                    symbol=sym,
                    cycle_id=cycle_id,
                )
                log_session_trade(
                    session_id=session_id,
                    side="buy_skipped",
                    symbol=sym,
                    quantity=int(trade.get("quantity") or 0),
                    price=0,
                    reason=str(trade.get("reason") or "skipped"),
                    pick_mode=pick_mode,
                    detail=sanitize_pick_row(trade),
                    cycle_id=cycle_id,
                )
                continue
            log_event(
                session_id,
                event_type="pick_executed",
                title=f"Bought {sym} × {trade.get('quantity')}",
                detail=sanitize_pick_row(trade),
                level="action",
                symbol=sym,
                cycle_id=cycle_id,
            )
            log_session_trade(
                session_id=session_id,
                side="buy",
                symbol=sym,
                quantity=int(trade.get("quantity") or 0),
                price=float(trade.get("fill_price") or trade.get("limit_price") or 0),
                notional_inr=trade.get("notional_inr"),
                reason="session_entry",
                pick_mode=pick_mode,
                order_id=trade.get("order_id"),
                detail=sanitize_pick_row(trade),
                cycle_id=cycle_id,
            )

        for row in universe_audit:
            decision = row.get("decision")
            sym = str(row.get("symbol") or "")
            if decision in {"rejected", "skipped"}:
                log_event(
                    session_id,
                    event_type=f"candidate_{decision}",
                    title=f"{sym} {decision} — {row.get('reason')}",
                    detail=row,
                    level="skip" if decision == "rejected" else "info",
                    symbol=sym,
                    cycle_id=cycle_id,
                )

        for pick in pick_result.get("picks") or []:
            sym = str(pick.get("symbol") or "")
            if sym:
                rag = retrieve_pick_lessons(sym, top_k=3)
                if rag:
                    rag_context.append({"symbol": sym, "lessons": rag})
                    log_event(
                        session_id,
                        event_type="rag_retrieved",
                        title=f"RAG lessons for {sym} ({len(rag)} hits)",
                        detail={"symbol": sym, "lessons": rag},
                        level="info",
                        symbol=sym,
                        cycle_id=cycle_id,
                    )

    log_cycle_record(
        session_id,
        cycle_id=cycle_id,
        pick_mode=pick_mode,
        market_open=trading,
        risk_snapshot=snap,
        guard=guard,
        pick_result=pick_result,
        universe_audit=universe_audit,
        rag_context=rag_context,
        notes=notes + [f"nse_phase:{phase}"],
    )

    _patch_session(session_id, realized_pnl_inr=_session_realized_pnl(session_id))
    return results


def run_all_session_cycles(
    *,
    analyze_fn: Callable[[str], dict[str, Any]],
    quote_fn: Callable[[str], float],
) -> dict[str, Any]:
    """Run one scheduler tick for every active desk in parallel (AI + curated)."""
    data = _load_store()
    sessions = _active_sessions(data)
    if not sessions:
        return {"skipped": True, "reason": "no_active_session"}

    if len(sessions) == 1:
        cycles = [run_session_cycle(analyze_fn=analyze_fn, quote_fn=quote_fn, session=sessions[0])]
    else:
        cycles: list[dict[str, Any]] = [dict() for _ in sessions]
        with ThreadPoolExecutor(max_workers=len(sessions), thread_name_prefix="desk-cycle") as pool:
            futures = {
                pool.submit(run_session_cycle, analyze_fn=analyze_fn, quote_fn=quote_fn, session=s): i
                for i, s in enumerate(sessions)
            }
            for fut in as_completed(futures):
                idx = futures[fut]
                try:
                    cycles[idx] = fut.result()
                except Exception as exc:
                    sess = sessions[idx]
                    cycles[idx] = {
                        "session_id": sess.get("id"),
                        "error": str(exc),
                        "pick_mode": sess.get("pick_mode"),
                    }

    return {
        "multi_session": True,
        "parallel": len(sessions) > 1,
        "session_count": len(sessions),
        "cycles": cycles,
        "completed_sessions": [c.get("completion_reason") for c in cycles if c.get("completed")],
    }


def _append_cycle(session: dict[str, Any], data: dict[str, Any], cycle: dict[str, Any]) -> None:
    """Legacy helper — cycles are now written by log_cycle_record."""
    daily = daily_stats()
    session["realized_pnl_inr"] = float(daily.get("realized_pnl_inr") or 0)
    _save_store(data)


def on_session_sell(
    *,
    session_id: str,
    symbol: str,
    quantity: int,
    entry_price: float,
    exit_price: float,
    reason: str,
    order_id: Optional[str] = None,
    decision_rationale: Optional[dict[str, Any]] = None,
) -> None:
    pnl = round((exit_price - entry_price) * quantity, 2)
    log_session_trade(
        session_id=session_id,
        side="sell",
        symbol=symbol,
        quantity=quantity,
        price=exit_price,
        pnl_inr=pnl,
        reason=reason,
        entry_price=entry_price,
        order_id=order_id,
        detail={
            "return_pct": round(((exit_price / entry_price) - 1) * 100, 2) if entry_price else None,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "decision_rationale": decision_rationale,
        },
    )
    from trading.session_history import log_event

    log_event(
        session_id,
        event_type="trade_closed",
        title=f"Closed {symbol} P&L ₹{pnl:+.0f} ({reason})",
        detail={
            "symbol": symbol,
            "quantity": quantity,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl_inr": pnl,
            "reason": reason,
            "order_id": order_id,
            "decision_rationale": decision_rationale,
        },
        level="action" if pnl >= 0 else "warn",
        symbol=symbol,
    )
    data = _load_store()
    session = _find_session(data, session_id)
    if session:
        session["realized_pnl_inr"] = float(daily_stats().get("realized_pnl_inr") or 0)
        _save_store(data)
