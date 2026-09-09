"""One-shot pre-live hygiene: stale sessions, orphans, calibration sync."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from trading.config_store import load_trading_config


def _ist_today() -> str:
    ist = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    return ist.strftime("%Y-%m-%d")


def _session_trade_date(session: dict[str, Any]) -> Optional[str]:
    for key in ("trade_date_ist", "started_at", "created_at"):
        raw = session.get(key)
        if not raw:
            continue
        try:
            ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            ist = ts.astimezone(timezone(timedelta(hours=5, minutes=30)))
            return ist.strftime("%Y-%m-%d")
        except Exception:
            continue
    return None


def find_stale_active_sessions(*, today: Optional[str] = None) -> list[dict[str, Any]]:
    """Sessions still marked active from prior IST days or orphaned in store."""
    from trading.session_autopilot import _active_sessions, _load_store

    today = today or _ist_today()
    data = _load_store()
    cfg = load_trading_config()
    ap = cfg.get("autopilot") or {}
    config_active = bool(ap.get("session_active"))
    active_ids = {str(s.get("id") or "") for s in _active_sessions(data)}

    stale: list[dict[str, Any]] = []
    seen: set[str] = set()

    for row in data.get("sessions") or []:
        if str(row.get("status") or "") != "active":
            continue
        sid = str(row.get("id") or "")
        if not sid or sid in seen:
            continue
        seen.add(sid)
        trade_day = _session_trade_date(row)
        reasons: list[str] = []
        if trade_day and trade_day != today:
            reasons.append(f"prior_day_{trade_day}")
        if not config_active and sid in active_ids:
            reasons.append("config_session_inactive")
        if sid not in active_ids:
            reasons.append("not_in_active_ids")
        if reasons:
            stale.append({**row, "_stale_reasons": reasons})

    # Too many concurrent active desks — stop oldest extras beyond 2
    active_rows = [s for s in (_active_sessions(data)) if s.get("id")]
    if len(active_rows) > 2:
        sorted_rows = sorted(active_rows, key=lambda s: str(s.get("started_at") or ""))
        for extra in sorted_rows[:-2]:
            sid = str(extra.get("id") or "")
            if sid and sid not in {str(x.get("id")) for x in stale}:
                stale.append({**extra, "_stale_reasons": ["too_many_active"]})

    return stale


def stop_stale_sessions(*, reason: str = "pre_live_hygiene") -> dict[str, Any]:
    from trading.session_autopilot import stop_session

    stale = find_stale_active_sessions()
    stopped: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for row in stale:
        sid = str(row.get("id") or "")
        try:
            result = stop_session(session_id=sid, reason=reason)
            if result.get("ok"):
                stopped.append({
                    "session_id": sid,
                    "reasons": row.get("_stale_reasons") or [],
                    "pick_mode": row.get("pick_mode"),
                })
            else:
                errors.append({"session_id": sid, "error": str(result.get("error") or "stop_failed")})
        except Exception as exc:
            errors.append({"session_id": sid, "error": str(exc)[:200]})
    return {"stopped": stopped, "errors": errors, "count": len(stopped)}


def run_pre_live_hygiene(
    *,
    stop_stale: bool = True,
    square_orphans: bool = True,
    sync_calibration: bool = True,
    run_quant_scan: bool = False,
) -> dict[str, Any]:
    """Square orphans, stop stale sessions, sync scoreboard + calibration."""
    result: dict[str, Any] = {"ok": True, "steps": {}}

    if stop_stale:
        result["steps"]["stale_sessions"] = stop_stale_sessions()

    if square_orphans:
        from trading.session_autopilot import _active_sessions, _load_store, square_orphan_positions

        store = _load_store()
        active_ids = {str(s.get("id") or "") for s in _active_sessions(store)}
        result["steps"]["orphans"] = square_orphan_positions(
            active_session_ids=active_ids,
            reason="pre_live_hygiene",
        )

    if sync_calibration:
        from trading.autopilot import recalibrate_from_scoreboard
        from trading.scoreboard import sync_from_predictions

        result["steps"]["scoreboard_sync"] = sync_from_predictions()
        result["steps"]["calibration"] = recalibrate_from_scoreboard()

    if run_quant_scan:
        try:
            from quant_layer.pipeline import ensure_quant_shortlist
            from routes.helpers import fetch_prices_light, rows_from_payload

            ap = load_trading_config().get("autopilot") or {}

            def _load(sym: str) -> list[dict[str, Any]]:
                payload = fetch_prices_light(sym, force_refresh=False, provider="auto", allow_nse_fallback=True)
                rows = rows_from_payload(payload)
                if len(rows) < 30:
                    raise ValueError("insufficient history")
                return rows

            result["steps"]["quant_scan"] = ensure_quant_shortlist(
                load_rows=_load,
                limit=500,
                max_shortlist=int(ap.get("quant_shortlist_max") or 30),
            )
        except Exception as exc:
            result["steps"]["quant_scan"] = {"error": str(exc)[:200]}

    from trading.pre_live_gates import check_pre_live_gates

    result["pre_live_gates"] = check_pre_live_gates(run_reconcile=False)
    result["ok"] = bool(result["pre_live_gates"].get("ok") or result["pre_live_gates"].get("skipped"))
    return result
