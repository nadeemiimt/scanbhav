"""7-day swing summary: pullback zones, recovery targets, and scenario paths."""
from __future__ import annotations

from typing import Any, Optional

from analysis.plan_15d import build_15d_trade_plan
from forecast_tracker import build_heuristic_forecast


def _num(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _pct_from(price: float, level: float) -> Optional[float]:
    if price <= 0:
        return None
    return round((level / price - 1) * 100, 2)


def _zone(label: str, price: Optional[float], spot: float, role: str) -> Optional[dict[str, Any]]:
    if price is None or price <= 0:
        return None
    return {
        "label": label,
        "price": round(price, 2),
        "pct_from_now": _pct_from(spot, price),
        "role": role,
    }


def build_7d_swing_summary(
    *,
    symbol: str,
    tech: dict[str, Any],
    ratings: dict[str, Any],
    plan_15d: Optional[dict[str, Any]] = None,
    news: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Educational 7-day pullback / recovery map from TA levels + heuristic forecast."""
    price = _num(tech.get("price")) or 0.0
    if price <= 0:
        return {"ok": False, "error": "No price data"}

    levels = tech.get("levels") or {}
    momentum = tech.get("momentum") or {}
    vol = tech.get("volatility") or {}
    ma = tech.get("moving_averages") or {}
    rsi = _num(momentum.get("rsi_14"))
    atr_pct = _num(vol.get("atr_pct"))

    if not plan_15d or not plan_15d.get("ok"):
        plan_15d = build_15d_trade_plan(tech=tech, ratings=ratings)

    as_of = str(tech.get("as_of") or "")
    forecast = build_heuristic_forecast(
        symbol=symbol,
        baseline_price=price,
        as_of=as_of,
        technicals=tech,
        ratings=ratings,
        news_bundle=news,
    )

    s1 = _num(levels.get("s1"))
    s2 = _num(levels.get("s2"))
    pivot = _num(levels.get("pivot"))
    r1 = _num(levels.get("r1"))
    r2 = _num(levels.get("r2"))
    entry = _num(plan_15d.get("entry_price")) if plan_15d.get("ok") else None
    stop = _num(plan_15d.get("stop_price")) if plan_15d.get("ok") else None
    exit_15d = _num(plan_15d.get("exit_price")) if plan_15d.get("ok") else None
    fc_target = _num(forecast.get("target_price"))
    fc_low = _num(forecast.get("price_band_low"))
    fc_high = _num(forecast.get("price_band_high"))

    zones: list[dict[str, Any]] = []
    for z in (
        _zone("R2", r2, price, "resistance"),
        _zone("R1", r1, price, "resistance"),
        _zone("52w high", _num(levels.get("high_52w")), price, "resistance"),
        _zone("Now", price, price, "spot"),
        _zone("Pivot", pivot, price, "support"),
        _zone("S1", s1, price, "support"),
        _zone("Plan entry (15d)", entry, price, "support"),
        _zone("S2", s2, price, "support"),
        _zone("Plan stop (15d)", stop, price, "invalidation"),
        _zone("7d band high", fc_high, price, "target"),
        _zone("7d target", fc_target, price, "target"),
        _zone("7d band low", fc_low, price, "support"),
        _zone("15d exit", exit_15d, price, "target"),
    ):
        if z:
            zones.append(z)

    # Pullback band: shallow support cluster above stop
    pullback_candidates = [x for x in (s1, entry, pivot) if x is not None and x < price]
    shallow_low = min(pullback_candidates) if pullback_candidates else (s1 or entry)
    shallow_high = max(pullback_candidates) if pullback_candidates else price * 0.99
    if shallow_low and shallow_high and shallow_low > shallow_high:
        shallow_low, shallow_high = shallow_high, shallow_low

    recovery_targets = [x for x in (r1, fc_target, r2, fc_high) if x is not None and x > price]
    recovery_targets = sorted(set(round(x, 2) for x in recovery_targets))

    stance = str(ratings.get("composite_stance") or "mixed")
    overbought = rsi is not None and rsi >= 70
    oversold = rsi is not None and rsi <= 30

    path_a = {
        "id": "shallow_pullback",
        "title": "Shallow pullback, then continuation",
        "likelihood_note": (
            "More aligned when trend is strong and composite stance is favorable."
            if stance in ("strong_favorable", "favorable", "bullish")
            else "Possible if supports hold."
        ),
        "steps": [
            {
                "phase": "Pullback",
                "detail": (
                    f"Price toward ₹{shallow_low:,.2f}–₹{shallow_high:,.2f} "
                    f"({_pct_from(price, shallow_low):+.1f}% to {_pct_from(price, shallow_high):+.1f}%)"
                    if shallow_low and shallow_high
                    else "Watch S1 / plan entry zone."
                ),
            },
            {
                "phase": "Hold",
                "detail": (
                    f"Support holds above ₹{entry:,.2f}; RSI cools from {rsi:.0f} toward ~60–65."
                    if entry and rsi is not None
                    else "Support holds; momentum resets without breaking plan stop."
                ),
            },
            {
                "phase": "Recovery",
                "detail": (
                    f"Reclaim ₹{recovery_targets[0]:,.2f}+, stretch toward "
                    f"₹{recovery_targets[1]:,.2f}"
                    if len(recovery_targets) >= 2
                    else (
                        f"Push toward ₹{recovery_targets[0]:,.2f}"
                        if recovery_targets
                        else "Push toward R1 / 7d target."
                    )
                ),
            },
        ],
    }

    path_b = {
        "id": "deeper_correction",
        "title": "Deeper correction if support breaks",
        "likelihood_note": "Watch if price closes below plan entry / S2.",
        "steps": [
            {
                "phase": "Breakdown",
                "detail": (
                    f"Below ₹{entry:,.2f} → next zones ₹{s2:,.2f} → ₹{stop:,.2f}."
                    if entry and s2 and stop
                    else "Break below plan entry opens deeper support."
                ),
            },
            {
                "phase": "Recovery",
                "detail": (
                    f"Needs reclaim of ₹{s1:,.2f}+ before bullish 7d view resumes."
                    if s1
                    else "Needs reclaim of S1 / pivot before resuming upside scenario."
                ),
            },
        ],
    }

    triggers: list[dict[str, str]] = []
    if s1:
        triggers.append({"kind": "pullback", "label": "Pullback watch", "level": f"₹{s1:,.2f} (S1)"})
    if entry:
        triggers.append({"kind": "pullback", "label": "Plan entry", "level": f"₹{entry:,.2f}"})
    if r1:
        triggers.append({"kind": "recovery", "label": "Recovery watch", "level": f"₹{r1:,.2f} (R1)"})
    if fc_target:
        triggers.append({"kind": "recovery", "label": "7d target", "level": f"₹{fc_target:,.2f}"})
    if stop:
        triggers.append({"kind": "invalidation", "label": "Invalidation", "level": f"₹{stop:,.2f}"})

    rsi_note = None
    if overbought:
        rsi_note = f"RSI {rsi:.0f} is overbought — pullback-first is common before the next leg up."
    elif oversold:
        rsi_note = f"RSI {rsi:.0f} is oversold — bounce scenarios get more weight."

    down_lo = _pct_from(price, shallow_low) if shallow_low else None
    down_hi = _pct_from(price, shallow_high) if shallow_high else None
    up_tgt = _pct_from(price, fc_target) if fc_target else None

    plain_parts = [
        f"Next 7 days: heuristic band ₹{fc_low:,.2f}–₹{fc_high:,.2f}, target ₹{fc_target:,.2f} "
        f"({forecast.get('expected_return_pct'):+.1f}%).",
    ]
    if down_lo is not None and down_hi is not None:
        plain_parts.append(
            f"Pullback zone ₹{shallow_low:,.2f}–₹{shallow_high:,.2f} ({down_lo:+.1f}% to {down_hi:+.1f}%)."
        )
    if up_tgt is not None:
        plain_parts.append(f"Recovery toward ₹{fc_target:,.2f} ({up_tgt:+.1f}%) if supports hold.")
    if rsi_note:
        plain_parts.append(rsi_note)

    return {
        "ok": True,
        "horizon_days": 7,
        "symbol": symbol.upper(),
        "current_price": round(price, 2),
        "as_of": as_of,
        "rsi_14": rsi,
        "atr_pct": atr_pct,
        "composite_stance": stance,
        "overbought": overbought,
        "overbought_note": rsi_note,
        "forecast_7d": forecast,
        "zones": zones,
        "pullback_band": {
            "low": round(shallow_low, 2) if shallow_low else None,
            "high": round(shallow_high, 2) if shallow_high else None,
            "pct_low": down_lo,
            "pct_high": down_hi,
        },
        "recovery_targets": recovery_targets,
        "paths": [path_a, path_b],
        "triggers": triggers,
        "plan_15d_ref": {
            "entry": entry,
            "exit": exit_15d,
            "stop": stop,
        },
        "plain": " ".join(plain_parts),
        "disclaimer": (
            "Educational 7-day scenario map from pivots, ATR, RSI, and horizon grades — "
            "not a guaranteed price path or investment advice."
        ),
    }
