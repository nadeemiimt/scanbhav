"""Dual-desk universe rules — agent auto-pick as superset of curated list."""
from __future__ import annotations

from typing import Any, Optional

from trading.config_store import load_trading_config


def agent_independent_desk(session: Optional[dict[str, Any]] = None) -> bool:
    """
    When true (default), Auto AI desk ignores curated list, cross-desk state, and mirror/gap logic.
    Desks may still hold the same symbol by coincidence — not by design.
    """
    ap = load_trading_config().get("autopilot") or {}
    if ap.get("agent_independent_desk", True) is False:
        return False
    if session is None:
        return True
    return str(session.get("pick_mode") or "") == "agent_auto"


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
    """
    Cross-desk symbols the agent must not duplicate.

    In dual desk mode, default is to block ALL curated open symbols so Auto does not
    re-buy the same names Curated already holds (separate ledger, worse fills).
    Set agent_dual_allow_curated_overlap=true to restore mandatory mirror overlap.
    """
    if not session or str(session.get("pick_mode") or "") != "agent_auto":
        return cross_desk
    ap = load_trading_config().get("autopilot") or {}
    if ap.get("dual_mode") and ap.get("agent_dual_allow_curated_overlap", False) is not True:
        return set(cross_desk)
    mandatory = agent_curated_superset_symbols(session)
    if not mandatory:
        return cross_desk
    blocked: set[str] = set()
    for sym in cross_desk:
        if symbol_base(sym) not in mandatory:
            blocked.add(sym)
    return blocked


def agent_curated_gap_symbols(session: Optional[dict[str, Any]], *, session_id: str = "") -> list[str]:
    """Curated-list names the other desk has not opened yet — safe for agent gap-fill."""
    superset = agent_curated_superset_symbols(session)
    if not superset:
        return []
    cross: set[str] = set()
    if session_id:
        try:
            from trading.session_autopilot import cross_desk_held_symbols

            cross = cross_desk_held_symbols(session_id)
        except Exception:
            pass
    cross_bases = {symbol_base(s) for s in cross}
    gap = [s for s in sorted(superset) if s not in cross_bases]
    return [f"{s}.NSE" if not str(s).endswith(".NSE") else str(s) for s in gap]
