"""Time-of-day exit thresholds, ATR risk sizing, and universal entry cutoffs."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional


def ist_minutes_now() -> int:
    ist = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    return ist.hour * 60 + ist.minute


def no_buy_after_minute(ap: dict[str, Any]) -> int:
    return int(ap.get("no_buy_after_minute_ist") or ap.get("agent_no_buy_after_minute_ist") or (14 * 60 + 30))


def late_buy_blocked(
    ap: dict[str, Any],
    *,
    ist_mins: int | None = None,
) -> tuple[bool, str]:
    """Block new MIS buys after cutoff — applies to all desks."""
    ist_mins = ist_mins if ist_mins is not None else ist_minutes_now()
    cutoff = no_buy_after_minute(ap)
    if ist_mins >= cutoff:
        return True, "late_session_no_buy"
    return False, "ok"


def effective_exit_rules(
    ap: dict[str, Any],
    *,
    ist_mins: int | None = None,
    base_target_pct: float | None = None,
) -> dict[str, float]:
    """
    Seasoned MIS: tighten targets/trails as runway shrinks (power hour → last hour).
    Full target early; scale-down after 14:30; aggressive lock after 15:00.
    """
    ist_mins = ist_mins if ist_mins is not None else ist_minutes_now()
    base_target = float(base_target_pct if base_target_pct is not None else ap.get("target_pct") or 2.0)
    base_stop = float(ap.get("stop_pct") or 1.0)
    trail_arm = float(ap.get("trailing_stop_arm_pct") or 1.0)
    trail_pct = float(ap.get("trailing_stop_pct") or 0.5)

    power_hour = int(ap.get("power_hour_start_minute_ist") or (14 * 60 + 30))
    late_tighten = int(ap.get("late_tighten_minute_ist") or (15 * 60))

    target = base_target
    if ist_mins >= late_tighten:
        target = min(target, float(ap.get("late_target_pct") or 0.8))
        trail_arm = min(trail_arm, float(ap.get("late_trail_arm_pct") or 0.5))
        trail_pct = min(trail_pct, float(ap.get("late_trail_pct") or 0.3))
    elif ist_mins >= power_hour:
        target = min(target, float(ap.get("power_hour_target_pct") or 1.0))
        trail_arm = min(trail_arm, float(ap.get("power_hour_trail_arm_pct") or 0.6))
        trail_pct = min(trail_pct, float(ap.get("power_hour_trail_pct") or 0.35))

    scale_out_pct = float(ap.get("partial_scale_out_pct") or 0)
    if scale_out_pct <= 0:
        scale_out_pct = base_target * float(ap.get("partial_scale_out_target_fraction") or 0.5)

    return {
        "target_pct": round(target, 3),
        "stop_pct": base_stop,
        "trail_arm_pct": round(trail_arm, 3),
        "trail_pct": round(trail_pct, 3),
        "scale_out_pct": round(scale_out_pct, 3),
        "power_hour_lock_min_pct": float(ap.get("power_hour_lock_min_pct") or 0.4),
        "power_hour_lock_pullback_pct": float(ap.get("power_hour_lock_pullback_pct") or 0.25),
    }


def risk_per_trade_inr(ap: dict[str, Any], risk: dict[str, Any] | None = None) -> float:
    """Rupee risk budget per new trade (stop-out loss cap)."""
    risk = risk or {}
    explicit = float(ap.get("risk_per_trade_inr") or 0)
    if explicit > 0:
        return explicit
    session_loss = float(risk.get("max_intraday_loss_inr") or ap.get("max_loss_inr") or 0)
    slots = int(ap.get("max_concurrent_picks") or risk.get("max_open_positions") or 3)
    if session_loss > 0 and slots > 0:
        return round(session_loss / slots, 2)
    return 3500.0


def size_by_atr_risk(
    price: float,
    *,
    atr_pct: float,
    stop_pct: float,
    risk_inr: float,
    max_per_order_inr: float,
    remaining_budget_inr: float,
    max_shares_cap: Optional[int] = None,
) -> Optional[dict[str, Any]]:
    """
    Size so a stop hit risks ~risk_inr.
    Uses effective stop = max(configured stop, 50% of ATR) — wider vol → smaller size.
    """
    if price <= 0 or risk_inr <= 0:
        return None
    effective_stop = max(float(stop_pct or 1.0), float(atr_pct or 0) * 0.5, 0.5)
    risk_qty = int(risk_inr / (price * effective_stop / 100.0))
    max_qty_order = int(max_per_order_inr // price)
    max_qty_budget = int(remaining_budget_inr // price)
    qty = min(risk_qty, max_qty_order, max_qty_budget)
    if max_shares_cap and max_shares_cap > 0:
        qty = min(qty, int(max_shares_cap))
    if qty < 1:
        return None
    notional = round(price * qty, 2)
    if notional > max_per_order_inr + 0.01 or notional > remaining_budget_inr + 0.01:
        return None
    return {
        "quantity": qty,
        "notional_inr": notional,
        "price": price,
        "sizing_method": "atr_risk",
        "effective_stop_pct": round(effective_stop, 3),
        "risk_at_stop_inr": round(notional * effective_stop / 100.0, 2),
    }


def dynamic_target_pct(row: dict[str, Any], ap: dict[str, Any]) -> float:
    """
    Small-cap / high-ATR names get higher targets (home runs).
    Flat 2% caps upside — SHILPAMED moved 2.57% today; runners can do 4–8%.
    """
    if not ap.get("dynamic_target_enabled", True):
        return float(ap.get("target_pct") or 2.0)
    base = float(ap.get("target_pct") or 2.0)
    atr = float(row.get("atr_pct") or 0)
    bucket = str(row.get("bucket") or row.get("cap_bucket") or "").lower()
    home_run = float(ap.get("home_run_target_pct") or 5.0)
    extended = float(ap.get("extended_target_pct") or 3.5)
    min_atr_home = float(ap.get("home_run_min_atr_pct") or 3.5)

    if bucket == "small" and atr >= min_atr_home:
        return round(home_run, 2)
    if atr >= 3.0:
        return round(min(extended, max(base, atr * 0.65)), 2)
    return base


def conviction_risk_multiplier(row: dict[str, Any], ap: dict[str, Any]) -> float:
    """A+ edge setups get larger risk budget (up to max_position cap)."""
    if not ap.get("conviction_sizing_enabled", True):
        return 1.0
    edge = float(row.get("edge_score") or row.get("pick_score") or row.get("composite_score") or 0)
    threshold = float(ap.get("conviction_edge_threshold") or 75)
    mult = float(ap.get("conviction_risk_multiplier") or 2.0)
    if edge >= threshold:
        return mult
    return 1.0


def estimate_daily_profit_ceiling(
    *,
    max_positions: int,
    avg_notional_inr: float,
    avg_target_pct: float,
    win_rate: float = 0.45,
) -> dict[str, float]:
    """Rough MIS day P/L ceiling for planning (not a guarantee)."""
    winners = max_positions * win_rate
    losers = max_positions * (1 - win_rate)
    gross_win = winners * avg_notional_inr * (avg_target_pct / 100.0)
    gross_loss = losers * avg_notional_inr * 0.01
    return {
        "max_positions": max_positions,
        "avg_notional_inr": avg_notional_inr,
        "avg_target_pct": avg_target_pct,
        "win_rate": win_rate,
        "estimated_gross_win_inr": round(gross_win, 0),
        "estimated_gross_loss_inr": round(gross_loss, 0),
        "estimated_net_inr": round(gross_win - gross_loss, 0),
    }
