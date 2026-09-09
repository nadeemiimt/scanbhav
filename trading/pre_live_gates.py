"""Pre-live safety gates before arming live execution."""
from __future__ import annotations

from typing import Any

from trading.config_store import load_trading_config


def check_pre_live_gates(*, run_reconcile: bool = False) -> dict[str, Any]:
    """Returns {ok, blockers[], warnings[]} — all blockers must clear before live."""
    cfg = load_trading_config()
    blockers: list[str] = []
    warnings: list[str] = []

    if cfg.get("execution_mode") != "live" and not cfg.get("live_armed"):
        return {"ok": True, "skipped": True, "reason": "not_live_mode"}

    # Orphan / stale session hygiene
    try:
        from trading.paper_ledger import open_positions
        from trading.session_autopilot import _active_sessions, _load_store

        store = _load_store()
        active = _active_sessions(store)
        if len(active) > 2:
            blockers.append(f"Too many active sessions ({len(active)} > 2)")
        positions = open_positions()
        orphan = [p for p in positions if p.get("session_id") and p.get("session_id") not in {s.get("id") for s in active}]
        if len(orphan) > 0:
            blockers.append(f"{len(orphan)} orphan positions — square before live")
    except Exception as exc:
        warnings.append(f"session check failed: {exc}")

    # Scoreboard minimum
    try:
        from quant_layer.trade_journal import journal_stats

        js = journal_stats(min_entries=10)
        if not js.get("ready"):
            warnings.append(f"Trade journal only {js.get('n_closed', 0)} closed signals (want ≥10)")
    except Exception:
        pass

    try:
        from trading.autopilot import load_calibration

        cal = load_calibration()
        total = ((cal or {}).get("scoreboard_summary") or {}).get("total") or 0
        if total < 20:
            warnings.append(f"Calibration scoreboard thin ({total} outcomes)")
    except Exception:
        warnings.append("Calibration scoreboard unavailable")

    if run_reconcile and cfg.get("reconcile_enabled", True):
        try:
            from trading.reconcile import reconcile_broker_positions
            bid = str(cfg.get("default_broker") or "stub")
            if bid != "stub":
                rec = reconcile_broker_positions(broker_id=bid)
                if rec.get("drift"):
                    blockers.append("Broker reconcile drift detected")
        except Exception as exc:
            warnings.append(f"reconcile skipped: {exc}")

    if cfg.get("block_live_without_arm") and not cfg.get("live_armed"):
        blockers.append("Live not armed — call /api/trading/arm-live")

    return {"ok": len(blockers) == 0, "blockers": blockers, "warnings": warnings}
