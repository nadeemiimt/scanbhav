"""Recommend Home run vs Conservative profile from scan breadth, vol, and session."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from trading.config_store import load_trading_config
from trading.morning_scan import load_morning_scan
from trading.profit_profiles import active_profit_profile_name

BULLISH_STANCES = {"favorable", "strong_favorable", "bullish", "constructive"}


def _ist_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=5, minutes=30)))


def _today_ist() -> str:
    return _ist_now().strftime("%Y-%m-%d")


def _scan_breadth(scan: dict[str, Any]) -> float:
    scored = float(scan.get("scored") or 0)
    bullish = float(scan.get("bullish_count") or 0)
    if scored <= 0:
        return 0.0
    return round(bullish / scored, 3)


def _analyze_universe(rows: list[dict[str, Any]], *, top_n: int = 40) -> dict[str, Any]:
    pool = rows[:top_n] if rows else []
    small_high_atr = 0
    atr_vals: list[float] = []
    small_bullish = 0
    for row in pool:
        bucket = str(row.get("bucket") or "").lower()
        atr = float(row.get("atr_pct") or 0)
        stance = str(row.get("stance") or "").lower()
        if atr > 0:
            atr_vals.append(atr)
        if bucket == "small" and stance in BULLISH_STANCES:
            small_bullish += 1
        if bucket == "small" and atr >= 3.5 and stance in BULLISH_STANCES:
            small_high_atr += 1
    return {
        "sample_size": len(pool),
        "avg_atr_pct": round(sum(atr_vals) / len(atr_vals), 2) if atr_vals else 0.0,
        "small_bullish_count": small_bullish,
        "small_high_atr_count": small_high_atr,
    }


def recommend_home_run_day(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Score today's market for Home run suitability (0–100).
    Uses morning scan breadth, small-cap ATR movers, and IST session window.
    """
    cfg = cfg or load_trading_config()
    ap = cfg.get("autopilot") or {}
    min_score = int(ap.get("home_run_recommend_min_score") or 65)
    strong_score = int(ap.get("home_run_recommend_strong_score") or 78)

    from trading.market_hours import nse_session_info
    from trading.timing_intelligence import current_session_window

    nse = nse_session_info(cfg)
    window = current_session_window()
    wid = str(window.get("id") or "")
    phase = str(nse.get("phase") or "")

    scan = load_morning_scan() or {}
    scan_today = scan.get("trade_date_ist") == _today_ist()
    rows = list(scan.get("rows") or scan.get("top_bullish") or [])
    if not rows and scan.get("top_bullish"):
        rows = list(scan.get("top_bullish") or [])

    breadth = _scan_breadth(scan) if scan_today else 0.0
    uni = _analyze_universe(rows, top_n=40)

    score = 0
    reasons: list[str] = []
    cautions: list[str] = []

    if not scan_today:
        score -= 25
        cautions.append("Morning scan not fresh for today — run scan before trusting Home run signal.")
    else:
        if breadth >= 0.58:
            score += 28
            reasons.append(f"Broad bullish breadth {breadth * 100:.0f}% of Nifty 500")
        elif breadth >= 0.52:
            score += 16
            reasons.append(f"Moderate breadth {breadth * 100:.0f}%")
        elif breadth < 0.45:
            score -= 12
            cautions.append(f"Narrow breadth {breadth * 100:.0f}% — stock-picker day, not home run")

        sh = uni["small_high_atr_count"]
        if sh >= 8:
            score += 26
            reasons.append(f"{sh} small-cap names with ATR ≥ 3.5% in top movers")
        elif sh >= 5:
            score += 16
            reasons.append(f"{sh} volatile small caps in scan top 40")
        elif sh >= 3:
            score += 8
        else:
            cautions.append("Few high-ATR small caps — large-cap day limits home-run upside")

        avg_atr = uni["avg_atr_pct"]
        if avg_atr >= 3.5:
            score += 18
            reasons.append(f"Top movers avg ATR {avg_atr:.1f}% — room for 4–5% MIS runs")
        elif avg_atr >= 2.8:
            score += 10
        elif avg_atr > 0 and avg_atr < 2.3:
            score -= 8
            cautions.append(f"Low avg ATR {avg_atr:.1f}% — 2% targets may be stretch already")

    if wid in {"open_drive", "morning_trend"} and phase == "trading":
        score += 22
        reasons.append(f"Favorable entry window: {window.get('label')}")
    elif wid == "pre_market" or phase == "pre_market":
        score += 12
        reasons.append("Pre-market — review scan; switch to Home run before 9:45 if tape confirms")
    elif wid == "midday":
        score -= 18
        cautions.append("Midday chop — Home run entries should have started in morning")
    elif wid in {"power_hour", "closing"} or phase == "post_close":
        score -= 28
        cautions.append("Too late for new Home run — use Conservative or flat")

    if phase == "weekend":
        score = max(0, score - 40)
        cautions.append("Market closed")

    score = max(0, min(100, score))

    active = active_profit_profile_name(cfg)
    if score >= strong_score:
        recommendation = "home_run"
        headline = "Strong Home run day — favorable breadth, vol, and timing"
        action = "Switch to Home run before morning trend ends (≈10:30 IST)"
    elif score >= min_score:
        recommendation = "consider_home_run"
        headline = "Home run viable — small/mid momentum with decent breadth"
        action = "Consider Home run if open drive confirms; else stay Conservative"
    elif score >= 40:
        recommendation = "conservative"
        headline = "Stay Conservative — mixed or average conditions"
        action = "Use Conservative profile; pick best 3–5 setups only"
    else:
        recommendation = "avoid_home_run"
        headline = "Not a Home run day — protect capital"
        action = "Stay Conservative; reduce size or skip if breadth is weak"

    if active == "home_run" and score < min_score - 5:
        action = "Consider switching back to Conservative — conditions weakened"
    elif active == "home_run" and score >= min_score:
        action = "Home run profile matches today's conditions — monitor breadth"

    return {
        "score": score,
        "recommendation": recommendation,
        "headline": headline,
        "action": action,
        "reasons": reasons,
        "cautions": cautions,
        "signals": {
            "scan_today": scan_today,
            "breadth_pct": round(breadth * 100, 1),
            "small_high_atr_count": uni["small_high_atr_count"],
            "avg_atr_top_pct": uni["avg_atr_pct"],
            "session_window": wid,
            "session_label": window.get("label"),
            "nse_phase": phase,
            "ist_time": nse.get("ist_time"),
        },
        "thresholds": {"min_score": min_score, "strong_score": strong_score},
        "active_profile": active,
        "aligned": (recommendation in {"home_run", "consider_home_run"} and active == "home_run")
        or (recommendation in {"conservative", "avoid_home_run"} and active == "conservative"),
    }


AUTO_STATE_PATH = __import__("config").BASE_DIR / "data" / "trading" / "auto_profile_state.json"


def _load_auto_state() -> dict[str, Any]:
    import json

    if not AUTO_STATE_PATH.exists():
        return {}
    try:
        return json.loads(AUTO_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_auto_state(state: dict[str, Any]) -> None:
    import json

    AUTO_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUTO_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _minutes_since(iso_ts: str | None) -> float:
    if not iso_ts:
        return 9999.0
    try:
        dt = datetime.fromisoformat(str(iso_ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 60.0
    except Exception:
        return 9999.0


def auto_apply_profit_profile(
    cfg: dict[str, Any] | None = None,
    *,
    pick_mode: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """
    Auto-switch Conservative ↔ Home run when advisor score crosses thresholds.
    Called from agent auto-pick session cycles (cooldown prevents flip-flop).
    """
    cfg = cfg or load_trading_config()
    ap = cfg.get("autopilot") or {}
    if not ap.get("auto_home_run_enabled", True):
        return {"skipped": True, "reason": "auto_home_run_disabled"}

    all_desks = bool(ap.get("auto_home_run_all_desks", True))
    if pick_mode and pick_mode not in {"agent_auto", "auto_pick", "session_agent_auto"} and not all_desks:
        return {"skipped": True, "reason": "not_agent_auto_desk"}

    rec = recommend_home_run_day(cfg)
    active = active_profit_profile_name(cfg)
    min_up = int(ap.get("auto_home_run_min_score") or ap.get("home_run_recommend_min_score") or 65)
    revert = int(ap.get("auto_home_run_revert_score") or 45)
    cooldown = int(ap.get("auto_home_run_cooldown_minutes") or 20)

    state = _load_auto_state()
    if state.get("date_ist") != _today_ist():
        state = {"date_ist": _today_ist()}

    if _minutes_since(state.get("last_switch_at")) < cooldown:
        return {
            "skipped": True,
            "reason": "cooldown",
            "cooldown_minutes": cooldown,
            "recommendation": rec,
            "active_profile": active,
        }

    target: str | None = None
    switch_reason = ""

    if rec["recommendation"] == "home_run" and rec["score"] >= min_up and active != "home_run":
        target = "home_run"
        switch_reason = f"score_{rec['score']}_home_run"
    elif (
        rec["recommendation"] == "consider_home_run"
        and rec["score"] >= min_up
        and active != "home_run"
    ):
        wid = str((rec.get("signals") or {}).get("session_window") or "")
        if wid in {"open_drive", "morning_trend", "pre_market"}:
            target = "home_run"
            switch_reason = f"score_{rec['score']}_consider_morning"
    elif active == "home_run" and rec["score"] < revert:
        target = "conservative"
        switch_reason = f"score_{rec['score']}_revert"

    if not target or target == active:
        return {
            "skipped": True,
            "reason": "no_change",
            "recommendation": rec,
            "active_profile": active,
        }

    from trading.profit_profiles import apply_profit_profile

    applied = apply_profit_profile(target)
    now_iso = datetime.now(timezone.utc).isoformat()
    _save_auto_state({
        "date_ist": _today_ist(),
        "last_switch_at": now_iso,
        "last_profile": target,
        "last_score": rec["score"],
        "last_reason": switch_reason,
        "session_id": session_id,
    })

    return {
        "applied": True,
        "profile": target,
        "previous_profile": active,
        "switch_reason": switch_reason,
        "recommendation": rec,
        "message": applied.get("message"),
        "config": applied.get("config"),
    }
