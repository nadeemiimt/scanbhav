"""Swing-trading setup score and trade-plan helpers (multi-day holds, 1W–1M focus)."""
from __future__ import annotations

from typing import Any, Optional

from desk_tools import position_size, relative_strength
from horizon_rank import _grade, _stance


def _clamp(score: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, score))


def _num(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def build_swing_setup(
    *,
    symbol: str,
    tech: dict[str, Any],
    ratings: dict[str, Any],
    dossier: dict[str, Any] | None = None,
    relative_strength_pack: dict[str, Any] | None = None,
    capital: float = 100_000.0,
    risk_pct: float = 1.0,
    atr_stop_mult: float = 1.5,
    reward_r: float = 2.0,
) -> dict[str, Any]:
    """Blend 1W + 1M horizon scores into a swing setup read with plan hints."""
    horizons = ratings.get("horizons") or {}
    h1w = horizons.get("1w") or {}
    h1m = horizons.get("1m") or {}
    w1 = _num(h1w.get("score")) or 50.0
    w2 = _num(h1m.get("score")) or 50.0
    horizon_blend = (w1 + w2) / 2.0

    conviction = _num((dossier or {}).get("conviction", {}).get("conviction_score")) or 50.0

    rs_score = 50.0
    rs_note = None
    if relative_strength_pack:
        rs_h = (relative_strength_pack.get("horizons") or {}).get("1m") or {}
        rs_pct = _num(rs_h.get("rs_pct"))
        if rs_pct is not None:
            rs_score = _clamp(50 + rs_pct * 1.5)
            rs_note = (relative_strength_pack.get("headline") or {}).get("plain")

    setup_score = round(_clamp(0.55 * horizon_blend + 0.25 * conviction + 0.20 * rs_score), 1)
    grade = _grade(setup_score)
    stance = _stance(setup_score)

    reasons: list[str] = []
    for label, h in (("1W", h1w), ("1M", h1m)):
        for r in (h.get("reasons") or [])[:2]:
            reasons.append(f"{label}: {r}")
        ret = h.get("horizon_return_pct")
        if ret is not None:
            reasons.append(f"{label} return {ret:+.1f}% over horizon window.")
    if rs_note:
        reasons.append(rs_note)
    if not reasons:
        reasons.append("Run with fresh data for horizon-specific reasons.")

    price = _num(tech.get("price")) or 0.0
    atr = _num((tech.get("volatility") or {}).get("atr_14"))
    levels = tech.get("levels") or {}
    sizing = position_size(
        price=price,
        atr=atr,
        capital=capital,
        risk_pct=risk_pct,
        atr_stop_mult=atr_stop_mult,
        reward_r=reward_r,
    ) if price > 0 else {}

    entry = price
    stop = sizing.get("stop_price")
    targets = [t.get("price") for t in (sizing.get("targets") or []) if t.get("price") is not None]

    if stance in {"strong_favorable", "favorable"}:
        action = "watch_long"
        plain = "1W/1M horizons lean constructive — define entry at support or pullback, size with ATR stop."
    elif stance in {"cautious", "unfavorable"}:
        action = "avoid_or_wait"
        plain = "Short horizons lean weak — wait for base or skip unless you have a counter-trend plan."
    else:
        action = "wait_setup"
        plain = "Mixed 1W/1M — wait for clearer alignment (trend + RS + level) before sizing a swing."

    return {
        "symbol": symbol.upper(),
        "setup_score": setup_score,
        "grade": grade,
        "stance": stance,
        "action": action,
        "plain_english": plain,
        "reasons": reasons[:8],
        "horizons": {
            "1w": {
                "score": h1w.get("score"),
                "grade": h1w.get("grade"),
                "stance": h1w.get("stance"),
                "return_pct": h1w.get("horizon_return_pct"),
            },
            "1m": {
                "score": h1m.get("score"),
                "grade": h1m.get("grade"),
                "stance": h1m.get("stance"),
                "return_pct": h1m.get("horizon_return_pct"),
            },
        },
        "conviction_score": conviction,
        "relative_strength_score": round(rs_score, 1),
        "levels": {
            "pivot": levels.get("pivot"),
            "r1": levels.get("r1"),
            "s1": levels.get("s1"),
            "r2": levels.get("r2"),
            "s2": levels.get("s2"),
            "high_52w": levels.get("high_52w"),
            "low_52w": levels.get("low_52w"),
        },
        "plan_hint": {
            "entry": entry,
            "stop": stop,
            "targets": targets,
            "shares": sizing.get("shares"),
            "risk_pct": risk_pct,
            "atr_stop_mult": atr_stop_mult,
            "reward_r": reward_r,
            "capital": capital,
            "atr": atr,
            "plain": sizing.get("plain"),
        },
        "as_of": tech.get("as_of"),
        "price": price,
        "disclaimer": (
            "Swing setup is an educational blend of 1W/1M technical horizons — "
            "not a trade signal. Confirm levels on your broker chart before acting."
        ),
    }


def recalc_swing_size(
    *,
    entry: float,
    stop: Optional[float] = None,
    capital: float = 100_000.0,
    risk_pct: float = 1.0,
    atr: Optional[float] = None,
    atr_stop_mult: float = 1.5,
    reward_r: float = 2.0,
) -> dict[str, Any]:
    """Recalculate shares/targets from entry + explicit stop or ATR fallback."""
    if stop and stop > 0:
        risk_per_share = abs(entry - stop)
        if risk_per_share <= 0:
            raise ValueError("Stop must differ from entry.")
        risk_rupees = capital * (max(0.1, min(5.0, float(risk_pct))) / 100.0)
        shares = int(risk_rupees // risk_per_share)
        targets = [round(entry + risk_per_share * r, 4) for r in (1.0, reward_r)]
        rr = round((targets[0] - entry) / risk_per_share, 2) if targets else None
        return {
            "entry": round(entry, 4),
            "stop": round(stop, 4),
            "shares": shares,
            "targets": targets,
            "reward_r": rr,
            "risk_rupees": round(risk_per_share * shares, 2),
            "notional": round(entry * shares, 2),
            "plain": f"{shares} shares @ ₹{risk_per_share:.2f} risk/share.",
        }
    return position_size(
        price=entry,
        atr=atr,
        capital=capital,
        risk_pct=risk_pct,
        atr_stop_mult=atr_stop_mult,
        reward_r=reward_r,
    )


def max_hold_days(horizon: str) -> int:
    return 22 if horizon == "1m" else 5


def build_trade_plan_payload(
    *,
    symbol: str,
    entry: float,
    stop: float,
    targets: list[float],
    shares: int,
    thesis: str = "",
    horizon: str = "1w",
    capital: float = 100_000.0,
    risk_pct: float = 1.0,
    trailing_stop: Optional[float] = None,
    atr_stop_mult: float = 1.5,
    reward_r: float = 2.0,
) -> dict[str, Any]:
    """Normalize a swing trade plan for storage or broker handoff."""
    if entry <= 0:
        raise ValueError("Entry price must be positive.")
    if stop <= 0:
        raise ValueError("Stop price must be positive.")
    if shares <= 0:
        raise ValueError("Share count must be positive.")
    risk_per_share = abs(entry - stop)
    risk_rupees = round(risk_per_share * shares, 2)
    notional = round(entry * shares, 2)
    rr = None
    if targets and risk_per_share > 0:
        rr = round((targets[0] - entry) / risk_per_share, 2)

    return {
        "symbol": symbol.upper(),
        "horizon": horizon,
        "entry": round(entry, 4),
        "stop": round(stop, 4),
        "targets": [round(t, 4) for t in targets if t],
        "shares": shares,
        "notional": notional,
        "risk_rupees": risk_rupees,
        "risk_pct_of_capital": round(risk_rupees / capital * 100, 2) if capital else None,
        "reward_r": rr,
        "thesis": thesis.strip(),
        "trailing_stop": round(trailing_stop, 4) if trailing_stop else None,
        "atr_stop_mult": atr_stop_mult,
        "plan_reward_r": reward_r,
        "max_hold_days": max_hold_days(horizon),
        "status": "planned",
    }
