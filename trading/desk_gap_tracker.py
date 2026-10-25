"""Track Auto AI vs Curated desk P&L, overlap, and coverage gap over time."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from config import BASE_DIR
from trading.desk_universe import symbol_base

LOG_PATH = BASE_DIR / "data" / "trading" / "desk_gap_log.json"
MAX_SNAPSHOTS = 400


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _desk_by_mode(sessions: list[dict[str, Any]]) -> tuple[Optional[dict], Optional[dict]]:
    agent = curated = None
    for s in sessions:
        mode = str(s.get("pick_mode") or "")
        if mode == "agent_auto":
            agent = s
        elif mode == "curated_list":
            curated = s
    return agent, curated


def _session_symbols(session: Optional[dict[str, Any]], *, from_positions: list[dict[str, Any]]) -> set[str]:
    if not session:
        return set()
    sid = str(session.get("id") or "")
    out = {symbol_base(p.get("symbol")) for p in from_positions if str(p.get("session_id") or "") == sid}
    return {s for s in out if s}


def compute_desk_gap(
    sessions: list[dict[str, Any]] | dict[str, Any],
    *,
    positions: Optional[list[dict[str, Any]]] = None,
    last_agent_pick: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Live gap metrics for dual desk (informational; agent may run independently)."""
    from trading.paper_ledger import open_positions

    if isinstance(sessions, dict):
        try:
            from trading.session_autopilot import _active_sessions, _hydrate_session

            sessions = [_hydrate_session(s) for s in _active_sessions(sessions)]
        except Exception:
            sessions = []
    positions = positions if positions is not None else open_positions("mis")
    agent, curated = _desk_by_mode(sessions)

    def _pnl(desk: Optional[dict[str, Any]]) -> dict[str, float]:
        if not desk:
            return {"realized": 0.0, "unrealized": 0.0, "net": 0.0}
        realized = float(desk.get("realized_pnl_inr") or 0)
        unrealized = float(desk.get("unrealized_pnl_inr") or 0)
        return {
            "realized": round(realized, 2),
            "unrealized": round(unrealized, 2),
            "net": round(float(desk.get("net_pnl_inr") or realized + unrealized), 2),
        }

    agent_pnl = _pnl(agent)
    curated_pnl = _pnl(curated)
    net_gap = round(agent_pnl["net"] - curated_pnl["net"], 2)

    agent_open = _session_symbols(agent, from_positions=positions)
    curated_open = _session_symbols(curated, from_positions=positions)
    overlap_open = agent_open & curated_open
    curated_only = curated_open - agent_open
    agent_only = agent_open - curated_open

    curated_list = set()
    if curated:
        curated_list = {symbol_base(s) for s in (curated.get("curated_symbols") or [])}

    coverage = 0.0
    if curated_open:
        coverage = round(100.0 * len(overlap_open) / len(curated_open), 1)
    elif curated_list:
        coverage = round(100.0 * len(agent_open & curated_list) / max(1, len(curated_list)), 1)

    agent_buys = int((agent or {}).get("trade_count") or 0)
    curated_buys = int((curated or {}).get("trade_count") or 0)

    pick_meta: dict[str, Any] = {}
    if last_agent_pick:
        pick_meta = {
            "affordable_candidates": last_agent_pick.get("affordable_candidates"),
            "pick_count": len(last_agent_pick.get("picks") or []),
            "mandatory_curated": last_agent_pick.get("mandatory_curated_symbols") or [],
            "filter_funnel": last_agent_pick.get("filter_funnel"),
        }
    elif agent:
        cycles = agent.get("cycles") or []
        if cycles:
            pr = (cycles[-1] or {}).get("pick_result") or {}
            pick_meta = {
                "affordable_candidates": pr.get("affordable_candidates"),
                "pick_count": len(pr.get("picks") or []),
                "mandatory_curated": pr.get("mandatory_curated_symbols") or [],
                "filter_funnel": pr.get("filter_funnel"),
            }

    headline = "in_sync"
    if net_gap < -500:
        headline = "curated_ahead"
    elif net_gap > 500:
        headline = "agent_ahead"
    if curated_open and not overlap_open:
        headline = "zero_overlap"
    elif curated_only:
        headline = "curated_symbols_missing_on_agent"

    return {
        "at": _now_iso(),
        "headline": headline,
        "net_gap_inr": net_gap,
        "agent_ahead": net_gap >= 0,
        "agent": {
            "session_id": (agent or {}).get("id"),
            "pnl": agent_pnl,
            "open_symbols": sorted(agent_open),
            "open_count": len(agent_open),
            "trade_count": agent_buys,
        },
        "curated": {
            "session_id": (curated or {}).get("id"),
            "pnl": curated_pnl,
            "open_symbols": sorted(curated_open),
            "open_count": len(curated_open),
            "trade_count": curated_buys,
        },
        "overlap_open_symbols": sorted(overlap_open),
        "curated_not_on_agent": sorted(curated_only),
        "agent_only_symbols": sorted(agent_only),
        "curated_coverage_pct": coverage,
        "agent_last_pick": pick_meta,
        "note": (
            "Positive net_gap_inr means Auto AI desk net P&L ≥ Curated; "
            "curated_coverage_pct is share of curated open names also held on agent desk."
        ),
    }


def append_gap_snapshot(gap: dict[str, Any]) -> dict[str, Any]:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {"snapshots": []}
    if LOG_PATH.exists():
        try:
            data = json.loads(LOG_PATH.read_text(encoding="utf-8"))
        except Exception:
            data = {"snapshots": []}
    snaps = list(data.get("snapshots") or [])
    snaps.append(gap)
    data["snapshots"] = snaps[-MAX_SNAPSHOTS:]
    data["latest"] = gap
    LOG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def load_gap_history(limit: int = 48) -> dict[str, Any]:
    if not LOG_PATH.exists():
        return {"snapshots": [], "latest": None}
    try:
        data = json.loads(LOG_PATH.read_text(encoding="utf-8"))
        snaps = list(data.get("snapshots") or [])
        return {"latest": data.get("latest"), "snapshots": snaps[-limit:]}
    except Exception:
        return {"snapshots": [], "latest": None}
