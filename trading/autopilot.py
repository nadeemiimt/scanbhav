"""Phase D — paper autopilot on watchlist; Phase E — calibration weights."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from config import BASE_DIR
from trading.config_store import is_live_execution, load_trading_config
from trading.intraday_sim import market_open_ist, sim_configure, sim_tick
from trading.order_router import execute_order
from trading.paper_ledger import open_positions
from trading.position_guard import monitor_open_positions
from trading.scoreboard import compute_summary
from trading.watchlist_agent import scan_watchlist

CALIBRATION_PATH = BASE_DIR / "data" / "trading" / "calibration.json"

DEFAULT_WEIGHTS = {
    "technicals": 0.30,
    "composite": 0.25,
    "horizons": 0.15,
    "competitive": 0.20,
    "news": 0.10,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _entry_candidates(watchlist: list[str], ap: dict[str, Any]) -> list[str]:
    candidates = list(watchlist)
    if ap.get("use_morning_scan_candidates", True):
        try:
            from trading.morning_scan import load_morning_scan

            ms = load_morning_scan() or {}
            for row in (ms.get("top_bullish") or [])[:8]:
                sym = str(row.get("symbol") or "").upper()
                if sym and sym not in candidates:
                    candidates.append(sym)
        except Exception:
            pass
    return candidates


def _premarket_ready(cfg: dict[str, Any]) -> tuple[bool, str]:
    from brokers.token_store import token_health
    from trading.health import trading_health

    if not (cfg.get("autopilot") or {}).get("require_premarket_ready", False):
        return True, "ok"
    h = trading_health(run_reconcile=False)
    if not h.get("checks", {}).get("token_valid"):
        return False, "token_invalid"
    if is_live_execution(cfg) and not h.get("checks", {}).get("broker_configured"):
        return False, "broker_not_configured"
    return True, "ok"


def run_autopilot_cycle(
    *,
    analyze_fn: Callable[[str], dict[str, Any]],
    quote_fn: Callable[[str], float],
) -> dict[str, Any]:
    """One scheduler tick: watchlist alerts + optional paper intraday sim."""
    cfg = load_trading_config()
    ap = cfg.get("autopilot") or {}
    if not ap.get("enabled"):
        return {"skipped": True, "reason": "autopilot_disabled"}

    if ap.get("session_active"):
        from trading.session_autopilot import run_all_session_cycles

        return run_all_session_cycles(analyze_fn=analyze_fn, quote_fn=quote_fn)

    if ap.get("session_follow_nse_hours", True):
        from trading.market_hours import nse_session_phase

        phase = nse_session_phase(cfg)
        if phase == "post_close":
            guard = monitor_open_positions(quote_fn, force_eod=True)
            return {"skipped": True, "reason": "nse_post_close", "position_guard": guard}

    watchlist = [s.upper() for s in (cfg.get("watchlist") or []) if s]
    ready, ready_reason = _premarket_ready(cfg)
    if not ready:
        return {"skipped": True, "reason": f"premarket_not_ready_{ready_reason}"}

    candidates = _entry_candidates(watchlist, ap)
    results: dict[str, Any] = {"watchlist": watchlist, "candidates": candidates[:12], "steps": []}

    guard = monitor_open_positions(quote_fn, force_eod=not market_open_ist())
    if guard.get("actions"):
        results["steps"].append({"position_guard": guard})

    if ap.get("watchlist_agent", True) and watchlist:
        scan = scan_watchlist(
            watchlist,
            quote_fn=quote_fn,
            analyze_fn=analyze_fn,
            rules=ap,
        )
        results["steps"].append({"watchlist_scan": scan})

    active = (ap.get("active_symbol") or "").upper()
    if ap.get("intraday_sim") and active:
        sim_configure(active, rules=ap)
        analysis = analyze_fn(active)
        tick = sim_tick(
            price=float(quote_fn(active)),
            composite_score=float(analysis.get("composite_score") or 50),
            stance=str(analysis.get("composite_stance") or "neutral"),
            force_eod=not market_open_ist(),
        )
        results["steps"].append({"intraday_sim": tick})

    if ap.get("paper_autopilot", True) and not is_live_execution(cfg) and candidates and market_open_ist():
        from trading.latency_compensation import compensated_entry_allowed

        for sym in candidates[:5]:
            pos = [p for p in open_positions("mis") if p.get("symbol") == sym]
            if pos:
                continue
            gate = compensated_entry_allowed(symbol=sym)
            if not gate.get("allowed"):
                results["steps"].append({"paper_entry_skipped": {"symbol": sym, "timing": gate}})
                continue
            analysis = analyze_fn(sym)
            if analysis.get("extended_allowed") is False:
                results["steps"].append({"paper_entry_skipped": {"symbol": sym, "reason": "extended_gate"}})
                continue
            score = float(analysis.get("composite_score") or 0)
            stance = str(analysis.get("composite_stance") or "")
            min_score = float(ap.get("entry_min_composite") or 55)
            if score >= min_score and stance.lower() in {"favorable", "strong_favorable", "constructive", "bull"}:
                order = execute_order(
                    {
                        "symbol": sym,
                        "side": "buy",
                        "quantity": int(ap.get("default_qty") or 1),
                        "order_type": "market",
                        "limit_price": quote_fn(sym),
                        "product": "mis",
                    },
                    source="autopilot",
                    composite_score=score,
                )
                results["steps"].append({"paper_entry": {"symbol": sym, "order": order}})
                break

    if ap.get("live_autopilot") and is_live_execution(cfg) and candidates and market_open_ist():
        from trading.latency_compensation import compensated_entry_allowed

        for sym in candidates[:5]:
            pos = [p for p in open_positions("mis") if p.get("symbol") == sym]
            if pos:
                continue
            gate = compensated_entry_allowed(symbol=sym)
            if not gate.get("allowed"):
                results["steps"].append({"live_entry_skipped": {"symbol": sym, "timing": gate}})
                continue
            analysis = analyze_fn(sym)
            if analysis.get("extended_allowed") is False:
                results["steps"].append({"live_entry_skipped": {"symbol": sym, "reason": "extended_gate"}})
                continue
            score = float(analysis.get("composite_score") or 0)
            stance = str(analysis.get("composite_stance") or "")
            min_score = float(ap.get("entry_min_composite") or 55)
            if score >= min_score and stance.lower() in {"favorable", "strong_favorable", "constructive", "bull"}:
                order = execute_order(
                    {
                        "symbol": sym,
                        "side": "buy",
                        "quantity": int(ap.get("default_qty") or 1),
                        "order_type": "market",
                        "limit_price": quote_fn(sym),
                        "product": "mis",
                    },
                    source="autopilot",
                    composite_score=score,
                    force_mode="live",
                )
                results["steps"].append({"live_entry": {"symbol": sym, "order": order}})
                break

    return results


def load_calibration() -> dict[str, Any]:
    CALIBRATION_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CALIBRATION_PATH.exists():
        payload = {
            "weights": dict(DEFAULT_WEIGHTS),
            "adjustments": [],
            "updated_at": _now(),
            "note": "Educational factor weights — derived from scoreboard hit rates.",
        }
        CALIBRATION_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload
    try:
        return json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"weights": dict(DEFAULT_WEIGHTS), "adjustments": []}


def recalibrate_from_scoreboard() -> dict[str, Any]:
    """Phase E — nudge conviction factor weights from historical hit rates."""
    summary = compute_summary()
    weights = dict(DEFAULT_WEIGHTS)
    adjustments = []

    stance_buckets = summary.get("by_stance") or {}
    horizon_buckets = summary.get("by_horizon") or {}

    # Boost composite weight if horizon 1d/1w hits are strong
    for h in ("1d", "1w", "1m"):
        bucket = horizon_buckets.get(h) or {}
        rate = bucket.get("hit_rate_pct")
        if rate is not None and rate >= 55:
            weights["composite"] = min(0.35, weights["composite"] + 0.02)
            weights["technicals"] = max(0.20, weights["technicals"] - 0.01)
            adjustments.append(f"Raised composite weight (horizon {h} hit {rate}%)")
        elif rate is not None and rate <= 40:
            weights["composite"] = max(0.15, weights["composite"] - 0.02)
            weights["news"] = min(0.15, weights["news"] + 0.01)
            adjustments.append(f"Lowered composite weight (horizon {h} hit {rate}%)")

    for st, bucket in stance_buckets.items():
        rate = bucket.get("hit_rate_pct")
        if rate is not None and rate <= 35 and bucket.get("total", 0) >= 5:
            weights["horizons"] = max(0.10, weights["horizons"] - 0.01)
            adjustments.append(f"Reduced horizon agreement weight ({st} underperformed)")

    total = sum(weights.values())
    weights = {k: round(v / total, 4) for k, v in weights.items()}

    payload = {
        "weights": weights,
        "adjustments": adjustments,
        "scoreboard_summary": summary,
        "updated_at": _now(),
        "disclaimer": "Heuristic calibration from local scoreboard — not validated ML.",
    }
    CALIBRATION_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
