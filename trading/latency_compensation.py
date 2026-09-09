"""
Latency compensation — act *early* when patterns predict a move before our delayed feed shows it.

We cannot see the exchange tick 2s before retail — instead we:
  1. Measure our latency budget (Yahoo ~15s, REST ~3s, Kite WS ~2s)
  2. Learn session/gap/momentum patterns from history + live tick velocity
  3. Enter preemptively when continuation is likely over the next budget window
  4. Feed RAG so the agent knows our delay and compensation logic
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from config import BASE_DIR
from genai_research import append_insight, retrieve_prior_insights

from trading.timing_intelligence import (
    _load_profiles,
    _today_ist,
    analyze_symbol_timing,
    current_session_window,
    timing_gate_allows,
)

COMPENSATION_PATH = BASE_DIR / "data" / "trading" / "latency_compensation.json"


def estimate_latency_budget() -> dict[str, Any]:
    """Our estimated delay vs co-lo / pro feed (seconds)."""
    from trading.config_store import load_trading_config

    ap = load_trading_config().get("autopilot") or {}
    override = ap.get("latency_budget_seconds")
    if override is not None:
        return {
            "budget_seconds": float(override),
            "source": "config_override",
            "pro_feed_advantage_seconds": float(override),
        }

    try:
        from brokers.ltp_stream import ltp_stream_status

        transport = ltp_stream_status().get("transport") or "none"
    except Exception:
        transport = "none"

    budgets = {"websocket": 2.0, "rest_poll": 3.5, "yahoo_poll": 15.0, "none": 5.0}
    budget = budgets.get(transport, 5.0)
    return {
        "budget_seconds": budget,
        "transport": transport,
        "source": "transport_estimate",
        "pro_feed_advantage_seconds": budget,
        "note": "Enter preemptively when pattern score high — aim to land order as move hits our feed.",
    }


def _pattern_score(symbol: str, side: str = "buy") -> dict[str, Any]:
    from brokers.quote_cache import tick_age_seconds, velocity

    sym = symbol.upper()
    profile = (_load_profiles().get("symbols") or {}).get(sym) or {}
    window = current_session_window()
    vel = velocity(sym, window_seconds=5.0)
    vel_15 = velocity(sym, window_seconds=15.0)
    tick_age = tick_age_seconds(sym)

    score = 0
    reasons: list[str] = []

    if side == "buy":
        if vel is not None and vel > 0.04:
            score += 2
            reasons.append(f"momentum_5s_{vel:+.3f}pct")
        elif vel is not None and vel > 0.01:
            score += 1
            reasons.append(f"drift_up_5s_{vel:+.3f}pct")

        if vel_15 is not None and vel_15 > 0.08:
            score += 1
            reasons.append(f"trend_15s_{vel_15:+.3f}pct")

        if profile.get("gap_continuation_rate", 0) >= 0.55:
            score += 1
            reasons.append("historical_gap_continuation")

        wid = window.get("id")
        if wid and wid in (profile.get("favorable_windows") or []):
            score += 1
            reasons.append(f"favorable_window_{wid}")

        if wid == "open_drive":
            score += 1
            reasons.append("open_drive_lead_window")

        if profile.get("open_strength_bias", 0) > 0.05:
            score += 1
            reasons.append("open_strength_bias")

        if vel is not None and vel < -0.05:
            score -= 2
            reasons.append(f"against_momentum_{vel:+.3f}pct")

    try:
        from routes.helpers import fetch_prices, rows_from_payload
        from technicals import compute_technicals
        from analysis.patterns import compute_patterns

        payload = fetch_prices(sym, "auto", force_refresh=False)
        rows = rows_from_payload(payload)
        if len(rows) >= 30:
            pat = compute_patterns(rows)
            bias = pat.get("composite_bias")
            if side == "buy" and bias == "bullish":
                score += +2
                reasons.append(f"extended_pattern_{bias}")
            elif side == "buy" and bias == "bearish":
                score -= 2
                reasons.append(f"extended_pattern_{bias}")
            names = pat.get("active_patterns") or []
            if names:
                reasons.append(f"patterns_{','.join(names[:2])}")
    except Exception:
        pass

    confidence = max(0.0, min(1.0, score / 6.0))
    return {
        "score": score,
        "confidence": round(confidence, 3),
        "reasons": reasons,
        "velocity_5s_pct": vel,
        "velocity_15s_pct": vel_15,
        "tick_age_seconds": tick_age,
        "profile": profile,
        "window": window,
    }


def predict_preemptive_entry(symbol: str, side: str = "buy") -> dict[str, Any]:
    budget = estimate_latency_budget()
    lead = float(budget.get("budget_seconds") or 2.0)
    pattern = _pattern_score(symbol, side=side)

    from trading.config_store import load_trading_config

    min_score = int(load_trading_config().get("autopilot", {}).get("latency_min_pattern_score") or 2)
    preemptive = pattern["score"] >= min_score and side == "buy"

    return {
        "symbol": symbol.upper(),
        "side": side,
        "preemptive": preemptive,
        "lead_seconds": lead,
        "latency_budget": budget,
        "pattern": pattern,
        "strategy": (
            f"Submit now — pattern suggests move continues over next ~{lead}s as our feed catches up."
            if preemptive
            else "Wait for stronger momentum/session pattern before early entry."
        ),
    }


def compensated_entry_allowed(
    symbol: str,
    side: str = "buy",
    *,
    session_id: str | None = None,
) -> dict[str, Any]:
    from trading.config_store import load_trading_config

    ap = load_trading_config().get("autopilot") or {}
    gate = timing_gate_allows(side, symbol, session_id=session_id)
    if not gate.get("allowed"):
        return {**gate, "compensation": "blocked_by_session_gate"}

    if not ap.get("latency_compensation_enabled", True):
        return {**gate, "compensation": "disabled", "preemptive": False}

    pred = predict_preemptive_entry(symbol, side=side)
    pattern = pred.get("pattern") or {}

    if side == "buy" and pattern.get("score", 0) < 0:
        return {
            "allowed": False,
            "reason": "latency_wait_negative_momentum",
            "message": "Delayed feed shows down-tick — waiting.",
            "compensation": pred,
            **gate,
        }

    if pred.get("preemptive"):
        return {
            "allowed": True,
            "preemptive": True,
            "reason": "latency_compensated_early_entry",
            "message": pred.get("strategy"),
            "lead_seconds": pred.get("lead_seconds"),
            "confidence": pattern.get("confidence"),
            "compensation": pred,
            **gate,
        }

    if ap.get("latency_require_preemptive", False):
        return {
            "allowed": False,
            "reason": "latency_pattern_too_weak",
            "message": "Pattern too weak for compensated entry.",
            "compensation": pred,
            **gate,
        }

    return {
        "allowed": True,
        "preemptive": False,
        "reason": "timing_ok_standard",
        "compensation": pred,
        **gate,
    }


def learn_latency_compensation_rag(symbols: list[str]) -> int:
    budget = estimate_latency_budget()
    count = 0
    for sym in symbols[:40]:
        sym = sym.upper().strip()
        if not sym:
            continue
        try:
            timing = analyze_symbol_timing(sym)
            if timing.get("error"):
                continue
            pred = predict_preemptive_entry(sym)
            insight = {
                "stance": "constructive" if pred.get("preemptive") else "neutral",
                "executive_summary": (
                    f"Latency compensation {sym}: feed ~{budget.get('budget_seconds')}s behind pro. "
                    f"Pre-emptive buy when momentum + gap continuation + favorable IST window. "
                    f"Gap cont {timing.get('gap_continuation_rate')}."
                ),
                "latency_budget_seconds": budget.get("budget_seconds"),
                "timing_profile": timing,
                "compensation_rules": pred,
                "not_advice_disclaimer": "Pattern-based delay compensation — not HFT.",
            }
            append_insight(
                symbol=sym,
                insight=insight,
                provider="latency_compensation",
                model="pattern_lead",
                as_of=_today_ist(),
                kind="latency_compensation",
            )
            count += 1
        except Exception:
            pass
    payload = {"updated_at": datetime.now(timezone.utc).isoformat(), "budget": budget, "symbols_rag": count}
    COMPENSATION_PATH.parent.mkdir(parents=True, exist_ok=True)
    COMPENSATION_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return count


def retrieve_latency_compensation_context(symbol: str, *, top_k: int = 3) -> str:
    lines = [f"Latency budget: {estimate_latency_budget()}"]
    lines.append(f"Live signal: {json.dumps(predict_preemptive_entry(symbol), default=str)[:1000]}")
    try:
        hits = retrieve_prior_insights(symbol, "latency compensation preemptive feed delay", top_k=top_k)
        for h in hits or []:
            meta = h.get("metadata") or {}
            if meta.get("kind") and meta.get("kind") != "latency_compensation":
                continue
            lines.append(f"- {(h.get('text') or '')[:300]}")
    except Exception:
        pass
    return "\n".join(lines)


def compensation_status(symbol: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {"latency_budget": estimate_latency_budget()}
    if symbol:
        out["symbol"] = symbol.upper()
        out["gate"] = compensated_entry_allowed(symbol, side="buy")
        out["prediction"] = predict_preemptive_entry(symbol)
    return out
