"""Dual-desk universe rules — agent auto-pick as superset of curated list."""
from __future__ import annotations

from typing import Any, Optional

from trading.config_store import load_trading_config


def symbol_base(symbol: str) -> str:
    return str(symbol or "").upper().replace(".NSE", "")


def agent_curated_superset_symbols(session: Optional[dict[str, Any]] = None) -> set[str]:
    """
    Symbols the Auto AI desk must treat as mandatory overlap with the curated desk.
    In dual mode, agent picks should include at least these names (separate session ledger).
    """
    cfg = load_trading_config()
    ap = cfg.get("autopilot") or {}
    if session and str(session.get("pick_mode") or "") != "agent_auto":
        return set()

    dual = bool(ap.get("dual_mode")) or ap.get("pick_mode") == "dual_desk"
    if session is None and not dual:
        return set()

    out: set[str] = set()
    prefs = ap.get("dual_desk_preferences") or {}
    for s in (prefs.get("curated") or {}).get("symbols") or []:
        out.add(symbol_base(s))
    for s in ap.get("curated_symbols") or []:
        out.add(symbol_base(s))
    for s in cfg.get("watchlist") or []:
        out.add(symbol_base(s))

    if dual or session:
        try:
            from trading.session_autopilot import _active_sessions, _load_store

            data = _load_store()
            for row in _active_sessions(data):
                if str(row.get("pick_mode") or "") == "curated_list":
                    for s in row.get("curated_symbols") or []:
                        out.add(symbol_base(s))
        except Exception:
            pass

    return {s for s in out if s}


def filter_cross_desk_for_agent(
    cross_desk: set[str],
    *,
    session: Optional[dict[str, Any]] = None,
) -> set[str]:
    """Remove curated mandatory symbols from cross-desk block list on the agent desk."""
    if not session or str(session.get("pick_mode") or "") != "agent_auto":
        return cross_desk
    mandatory = agent_curated_superset_symbols(session)
    if not mandatory:
        return cross_desk
    blocked: set[str] = set()
    for sym in cross_desk:
        if symbol_base(sym) not in mandatory:
            blocked.add(sym)
    return blocked
