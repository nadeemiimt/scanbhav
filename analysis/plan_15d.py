"""15-day swing-style entry / exit price plan from technical levels."""
from __future__ import annotations

from typing import Any, Optional

from desk_tools import position_size


def build_15d_trade_plan(
    *,
    tech: dict[str, Any],
    ratings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Educational 15-day buy zone, best exit, and stop from pivots + ATR + momentum."""
    price = float(tech.get("price") or 0)
    if price <= 0:
        return {"ok": False, "error": "No price data"}

    levels = tech.get("levels") or {}
    returns = tech.get("returns_pct") or {}
    vol = tech.get("volatility") or {}
    atr = vol.get("atr_14")
    atr_pct = float(vol.get("atr_pct") or 2.0)
    ret_15d = returns.get("15d")

    s1 = levels.get("s1")
    pivot = levels.get("pivot")
    r1 = levels.get("r1")
    r2 = levels.get("r2")

    composite = float((ratings or {}).get("composite_score") or 50)
    stance = str((ratings or {}).get("composite_stance") or "mixed")

    entry_candidates: list[float] = []
    if isinstance(s1, (int, float)) and s1 < price:
        entry_candidates.append(float(s1))
    if isinstance(pivot, (int, float)) and pivot < price:
        entry_candidates.append(float(pivot))
    if isinstance(atr, (int, float)) and atr > 0:
        entry_candidates.append(price - float(atr))
    entry_candidates.append(price * (1 - min(atr_pct, 4.0) / 200.0))
    entry = round(min(entry_candidates) if entry_candidates else price * 0.99, 2)
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
        stop = round(entry * 0.97, 2)

    momentum_target: Optional[float] = None
    if isinstance(ret_15d, (int, float)):
        momentum_target = price * (1 + (float(ret_15d) * 0.6) / 100.0)

    exit_candidates: list[float] = []
    if isinstance(r1, (int, float)) and r1 > price:
        exit_candidates.append(float(r1))
    if isinstance(r2, (int, float)) and r2 > price:
        exit_candidates.append(float(r2))
    if target_2r and target_2r > price:
        exit_candidates.append(target_2r)
    if momentum_target and momentum_target > price:
        exit_candidates.append(momentum_target)
    min_upside = 1.5 if composite >= 55 else 1.0
    exit_candidates.append(price * (1 + min_upside / 100.0))
    exit_price = round(max(exit_candidates), 2)

    upside_pct = round((exit_price / entry - 1) * 100, 2) if entry else None
    downside_pct = round((1 - (stop or entry) / entry) * 100, 2) if stop and entry else None

    return {
        "ok": True,
        "horizon_days": 15,
        "entry_price": entry,
        "exit_price": exit_price,
        "stop_price": round(float(stop), 2) if stop is not None else None,
        "current_price": round(price, 2),
        "return_15d_hist_pct": ret_15d,
        "upside_pct": upside_pct,
        "downside_pct": downside_pct,
        "stance": stance,
        "composite_score": composite,
        "levels_used": {
            "s1": s1,
            "pivot": pivot,
            "r1": r1,
            "r2": r2,
        },
        "plain": (
            f"Next 15 days: enter near ₹{entry:,.2f}, target exit ₹{exit_price:,.2f}, "
            f"stop ₹{(stop or 0):,.2f} ({upside_pct:+.1f}% upside vs entry)."
        ),
        "disclaimer": "Educational plan from pivots, ATR, and 15d momentum — not investment advice.",
    }


def slim_15d_fields(plan: dict[str, Any]) -> dict[str, Any]:
    if not plan.get("ok"):
        return {}
    return {
        "entry_15d": plan.get("entry_price"),
        "exit_15d": plan.get("exit_price"),
        "stop_15d": plan.get("stop_price"),
        "plan_15d_upside_pct": plan.get("upside_pct"),
    }
