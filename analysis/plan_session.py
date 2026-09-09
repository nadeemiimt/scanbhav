"""Session-aware entry / exit plan — today vs next trading day (IST)."""
from __future__ import annotations

from typing import Any, Literal, Optional

from desk_tools import position_size
from trading.market_hours import nse_schedule, _ist_now

PlanTargetDay = Literal["today", "next_day"]


def session_plan_target_day(cfg: dict[str, Any] | None = None) -> PlanTargetDay:
    """09:00–15:30 IST → today; after 15:30 until next 09:00 → next_day."""
    now = _ist_now()
    if now.weekday() >= 5:
        return "next_day"
    mins = now.hour * 60 + now.minute
    sched = nse_schedule(cfg)
    start = sched["premarket_start"]
    close = sched["market_close"]
    if start <= mins <= close:
        return "today"
    return "next_day"


def session_plan_labels(target: PlanTargetDay) -> dict[str, str]:
    if target == "today":
        return {
            "target_day": "today",
            "entry_label": "Entry (today)",
            "exit_label": "Exit (today)",
            "stop_label": "Stop (today)",
            "hint": "Intraday session — enter on dip, exit at resistance / target same day.",
        }
    return {
        "target_day": "next_day",
        "entry_label": "Entry (next day)",
        "exit_label": "Exit (next day)",
        "stop_label": "Stop (next day)",
        "hint": "Post-close / pre-open — levels for the next NSE session.",
    }


def session_plan_context(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    target = session_plan_target_day(cfg)
    labels = session_plan_labels(target)
    now = _ist_now()
    return {
        **labels,
        "ist_time": now.strftime("%H:%M"),
        "ist_date": now.strftime("%Y-%m-%d"),
    }


def _tech_from_row(row: dict[str, Any]) -> dict[str, Any]:
    """Rebuild minimal technicals from a slim screener row."""
    price = float(row.get("price") or 0)
    levels: dict[str, Any] = {}
    for src, dst in (("pivot_s1", "s1"), ("pivot_r1", "r1"), ("pivot_r2", "r2"), ("pivot_pivot", "pivot")):
        val = row.get(src)
        if isinstance(val, (int, float)):
            levels[dst] = float(val)
    return {
        "price": price,
        "volatility": {
            "atr_14": row.get("atr_14"),
            "atr_pct": row.get("atr_pct") or 2.0,
        },
        "levels": levels,
        "returns_pct": {},
    }


def build_session_trade_plan(
    *,
    tech: dict[str, Any],
    ratings: Optional[dict[str, Any]] = None,
    target_day: Optional[PlanTargetDay] = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Educational buy zone, best exit, and stop for today or next NSE session."""
    price = float(tech.get("price") or 0)
    if price <= 0:
        return {"ok": False, "error": "No price data"}

    target = target_day or session_plan_target_day(cfg)
    labels = session_plan_labels(target)

    levels = tech.get("levels") or {}
    vol = tech.get("volatility") or {}
    atr = vol.get("atr_14")
    atr_pct = float(vol.get("atr_pct") or 2.0)
    s1 = levels.get("s1")
    pivot = levels.get("pivot")
    r1 = levels.get("r1")
    r2 = levels.get("r2")

    composite = float((ratings or {}).get("composite_score") or 50)
    stance = str((ratings or {}).get("composite_stance") or "mixed")

    # Today: tighter dip entry; next day: wider limit zone from prior close.
    entry_pull = 0.25 if target == "today" else 0.5
    exit_push = 0.75 if target == "today" else 1.0
    min_upside = 1.0 if target == "today" else (1.5 if composite >= 55 else 1.0)

    entry_candidates: list[float] = []
    if isinstance(s1, (int, float)) and float(s1) < price:
        entry_candidates.append(float(s1))
    if isinstance(pivot, (int, float)) and float(pivot) < price:
        entry_candidates.append(float(pivot))
    if isinstance(atr, (int, float)) and float(atr) > 0:
        entry_candidates.append(price - float(atr) * entry_pull)
    entry_candidates.append(price * (1 - min(atr_pct, 4.0) / (200.0 / entry_pull)))
    entry = round(min(entry_candidates) if entry_candidates else price * (0.995 if target == "today" else 0.99), 2)
    entry = min(entry, price)

    stop: Optional[float] = None
    target_2r: Optional[float] = None
    try:
        sizing = position_size(price=entry, atr=atr, capital=100_000.0, risk_pct=1.0)
        stop = sizing.get("stop_price")
        targets = sizing.get("targets") or []
        if len(targets) > 1:
            target_2r = float(targets[1]["price"])
    except Exception:
        stop_pct = 0.5 if target == "today" else 0.75
        stop = round(entry * (1 - stop_pct / 100), 2)

    exit_candidates: list[float] = []
    if isinstance(r1, (int, float)) and float(r1) > price:
        exit_candidates.append(float(r1))
    if target != "today" and isinstance(r2, (int, float)) and float(r2) > price:
        exit_candidates.append(float(r2))
    if isinstance(atr, (int, float)) and float(atr) > 0:
        exit_candidates.append(price + float(atr) * exit_push)
    if target_2r and target_2r > price:
        exit_candidates.append(target_2r)
    exit_candidates.append(price * (1 + min_upside / 100.0))
    exit_price = round(max(exit_candidates), 2)

    upside_pct = round((exit_price / entry - 1) * 100, 2) if entry else None
    downside_pct = round((1 - (stop or entry) / entry) * 100, 2) if stop and entry else None

    day_word = "today" if target == "today" else "next session"
    return {
        "ok": True,
        "target_day": target,
        "entry_price": entry,
        "exit_price": exit_price,
        "stop_price": round(float(stop), 2) if stop is not None else None,
        "current_price": round(price, 2),
        "upside_pct": upside_pct,
        "downside_pct": downside_pct,
        "stance": stance,
        "composite_score": composite,
        "levels_used": {"s1": s1, "pivot": pivot, "r1": r1, "r2": r2},
        "plain": (
            f"{day_word.title()}: enter near ₹{entry:,.2f}, best exit ₹{exit_price:,.2f}, "
            f"stop ₹{(stop or 0):,.2f} ({upside_pct:+.1f}% vs entry)."
        ),
        **labels,
        "disclaimer": "Educational session plan from pivots and ATR — not investment advice.",
    }


def slim_session_fields(plan: dict[str, Any]) -> dict[str, Any]:
    if not plan.get("ok"):
        return {}
    return {
        "entry_15d": plan.get("entry_price"),
        "exit_15d": plan.get("exit_price"),
        "stop_15d": plan.get("stop_price"),
        "plan_15d_upside_pct": plan.get("upside_pct"),
        "plan_target_day": plan.get("target_day"),
    }


def enrich_row_session_plan(row: dict[str, Any], full: Optional[dict[str, Any]] = None) -> None:
    """Attach session entry/exit columns to one screener row (mutates row)."""
    from analysis.plan_session import session_plan_target_day

    target = session_plan_target_day()
    if row.get("entry_15d") is not None and row.get("plan_target_day") == target:
        return

    if full and full.get("technicals"):
        tech = full["technicals"]
        ratings = full.get("ratings")
    else:
        tech = _tech_from_row(row)
        ratings = {
            "composite_score": row.get("composite_score") or row.get("score"),
            "composite_stance": row.get("stance"),
        }
    row.update(slim_session_fields(build_session_trade_plan(tech=tech, ratings=ratings)))
    row["plan_target_day"] = target
