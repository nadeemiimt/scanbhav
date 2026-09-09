"""
Agent desk capital goals — minimum daily profit target vs user-set max profit cap.

`agent_min_daily_profit_target_inr` is a *goal* (e.g. ₹100k on ₹30L capital).
`max_profit_inr` on risk/desk caps remains user-controlled and may be higher.
"""
from __future__ import annotations

from typing import Any

from trading.config_store import load_trading_config


def agent_capital_goals(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or load_trading_config()
    ap = cfg.get("autopilot") or {}
    # Legacy alias: agent_profit_target_inr
    target = ap.get("agent_min_daily_profit_target_inr")
    if target is None:
        target = ap.get("agent_profit_target_inr")
    return {
        "capital_inr": float(ap.get("agent_capital_inr") or 0),
        "min_daily_profit_target_inr": float(target or 0),
        "target_return_pct": round(
            (float(target or 0) / float(ap.get("agent_capital_inr") or 1)) * 100, 3
        )
        if float(ap.get("agent_capital_inr") or 0) > 0 and float(target or 0) > 0
        else 0.0,
    }


def portfolio_expected_profit_inr(picks: list[dict[str, Any]]) -> float:
    return round(sum(float(p.get("expected_profit_inr") or 0) for p in picks), 2)


def optimize_picks_for_profit_target(
    picks: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    *,
    min_target_inr: float,
    max_picks: int,
) -> list[dict[str, Any]]:
    """
    Swap lower-profit picks for higher expected-profit names when the portfolio
    expected P/L is below the daily target (does not change max_profit caps).
    """
    if min_target_inr <= 0 or not picks:
        return picks

    out = list(picks)
    picked_syms = {str(p.get("symbol") or "").upper() for p in out}
    pool = [
        c for c in candidates
        if str(c.get("symbol") or "").upper() not in picked_syms
    ]
    pool.sort(key=lambda c: float(c.get("expected_profit_inr") or 0), reverse=True)

    def _total() -> float:
        return portfolio_expected_profit_inr(out)

    if _total() >= min_target_inr:
        return out

    # Replace weakest pick(s) with stronger expected-profit candidates.
    out.sort(key=lambda p: float(p.get("expected_profit_inr") or 0))
    for cand in pool:
        if _total() >= min_target_inr:
            break
        if len(out) >= max_picks and out:
            weakest = out.pop(0)
            picked_syms.discard(str(weakest.get("symbol") or "").upper())
        sym = str(cand.get("symbol") or "").upper()
        if sym in picked_syms:
            continue
        out.append(cand)
        picked_syms.add(sym)

    out.sort(
        key=lambda p: (
            p.get("edge_score") or 0,
            p.get("expected_profit_inr") or 0,
        ),
        reverse=True,
    )
    return out[:max_picks]
