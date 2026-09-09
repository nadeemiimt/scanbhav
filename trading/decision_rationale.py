"""Structured buy/sell thought process for autopilot audit and tuning."""
from __future__ import annotations

from typing import Any, Optional


# Psychology is now an active gate — see trading/psychology_gates.py
PSYCHOLOGY_IN_TRADE_RULES = True
PSYCHOLOGY_NOTE = (
    "Crowd psychology (behavior_psychology + social sentiment) adjusts pick_score and can block buys "
    "(FOMO/euphoria/panic) or trigger early exits (greed take-profit, fear cut)."
)


def _fmt_inr(v: Any) -> str:
    try:
        return f"₹{float(v):,.0f}"
    except (TypeError, ValueError):
        return "—"


def build_buy_rationale(
    *,
    pick: dict[str, Any],
    gate: Optional[dict[str, Any]] = None,
    limits: Optional[dict[str, Any]] = None,
    trade: Optional[dict[str, Any]] = None,
    min_composite: float = 55,
    target_pct: float = 1.5,
    skipped: bool = False,
    skip_reason: str = "",
    psych_gate: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Human + machine-readable rationale for a buy or buy-skip."""
    row = pick.get("screen_row") or {}
    reasons = list(pick.get("reasons") or [])
    gate = gate or {}
    limits = limits or {}
    trade = trade or {}

    technical = {
        "composite_score": pick.get("composite_score"),
        "pick_score": pick.get("pick_score"),
        "stance": pick.get("stance"),
        "rsi_14": row.get("rsi_14"),
        "macd_hist": row.get("macd_hist"),
        "supertrend_dir": row.get("supertrend_dir"),
        "golden_cross": row.get("golden_cross"),
        "pattern_bias": row.get("pattern_bias"),
        "relative_volume": row.get("rvol") or row.get("relative_volume"),
        "horizon_return_pct": row.get("horizon_return_pct"),
        "min_composite_required": min_composite,
    }
    fundamentals_proxy = {
        "quality_ok": row.get("quality_ok"),
        "quality_score": row.get("quality_score"),
        "note": "Full fundamentals (debt, pledge, analyst) blend into composite upstream — not re-checked at order time.",
    }
    timing = {
        "allowed": gate.get("allowed"),
        "reason": gate.get("reason"),
        "window": gate.get("window"),
        "session_phase": gate.get("phase") or gate.get("session_window"),
        "preemptive": gate.get("preemptive"),
        "compensation": gate.get("compensation") if isinstance(gate.get("compensation"), str) else (gate.get("compensation") or {}).get("strategy"),
        "pattern_score": (gate.get("compensation") or {}).get("pattern", {}).get("score") if isinstance(gate.get("compensation"), dict) else None,
    }
    risk_budget = {
        "max_per_order_inr": limits.get("max_per_order_inr"),
        "remaining_budget_inr": limits.get("remaining_budget_inr"),
        "position_slots": limits.get("position_slots"),
        "orders_left": limits.get("orders_left"),
        "halted": limits.get("halted"),
        "quantity": pick.get("quantity"),
        "notional_inr": pick.get("notional_inr"),
        "expected_profit_inr": pick.get("expected_profit_inr"),
        "expected_return_pct": pick.get("expected_return_pct"),
        "target_pct": target_pct,
        "top_up": bool(pick.get("top_up")),
    }
    rag = {
        "reasons_in_pick_score": [r for r in reasons if str(r).startswith("rag_adj")],
        "note": "Past session wins/losses adjust pick_score ±10 via pick_learning RAG.",
    }

    psych_gate = psych_gate or pick.get("psychology_gate") or {}
    psych = psych_gate.get("psychology") or pick.get("psychology") or {}
    psychology = {
        "included_in_rules": PSYCHOLOGY_IN_TRADE_RULES,
        "allowed": psych_gate.get("allowed", True),
        "reason": psych_gate.get("reason"),
        "primary_mood": psych_gate.get("primary_mood") or psych.get("primary_mood"),
        "sentiment_score": psych_gate.get("sentiment_score") or psych.get("sentiment_score"),
        "rsi_14": psych_gate.get("rsi_14") or psych.get("rsi_14"),
        "score_adjustment": psych_gate.get("score_adjustment"),
        "headline": psych_gate.get("headline") or psych.get("headline") or psych.get("plain_english"),
        "warnings": psych_gate.get("warnings") or [],
        "biases": (psych.get("biases") or [])[:3],
    }

    gates_passed: list[str] = []
    gates_failed: list[str] = []
    if float(pick.get("composite_score") or 0) >= min_composite:
        gates_passed.append(f"composite ≥ {min_composite}")
    else:
        gates_failed.append(f"composite < {min_composite}")
    if str(pick.get("stance") or "").lower() in {"favorable", "strong_favorable", "bullish", "constructive"}:
        gates_passed.append(f"bullish stance ({pick.get('stance')})")
    elif pick.get("stance"):
        gates_failed.append(f"stance not bullish ({pick.get('stance')})")
    if gate.get("allowed"):
        gates_passed.append(f"timing gate ({gate.get('reason') or 'ok'})")
    elif gate:
        gates_failed.append(f"timing blocked ({gate.get('reason') or 'unknown'})")
    if psych_gate.get("allowed") is not False:
        mood = psychology.get("primary_mood") or "ok"
        gates_passed.append(f"psychology ({mood})")
    elif psych_gate:
        gates_failed.append(f"psychology blocked ({psych_gate.get('reason') or 'unknown'})")
    if trade.get("skipped"):
        gates_failed.append(f"order blocked ({trade.get('reason') or 'risk'})")
    elif trade and not skipped:
        gates_passed.append("risk + order router")

    lines = [
        f"BUY {pick.get('symbol')} × {pick.get('quantity') or '?'} @ ~{_fmt_inr(pick.get('price'))}",
        f"Pick score {pick.get('pick_score')} · composite {pick.get('composite_score')} · stance {pick.get('stance') or '—'}",
        f"Expected +{pick.get('expected_return_pct') or target_pct}% → profit ~{_fmt_inr(pick.get('expected_profit_inr'))} within budget {_fmt_inr(limits.get('remaining_budget_inr'))}",
    ]
    if reasons:
        lines.append("Score drivers: " + ", ".join(reasons))
    if timing.get("window") or timing.get("session_phase"):
        lines.append(f"Timing: {timing.get('window') or timing.get('session_phase')} ({timing.get('reason') or 'allowed'})")
    if psychology.get("primary_mood"):
        lines.append(
            f"Psychology: mood {psychology['primary_mood']}"
            + (f" · sentiment {psychology['sentiment_score']:.0f}" if psychology.get("sentiment_score") is not None else "")
            + (f" · adj {psychology['score_adjustment']:+.1f}" if psychology.get("score_adjustment") else "")
        )
        if psychology.get("headline"):
            lines.append(f"Crowd read: {str(psychology['headline'])[:200]}")
    if psychology.get("warnings"):
        lines.append("Psych warnings: " + "; ".join(psychology["warnings"][:2]))
    if pick.get("top_up"):
        lines.append(f"Top-up existing position (held {pick.get('held_quantity')} sh) — gradual scale-in")
    if skipped or trade.get("skipped"):
        lines.append(f"SKIPPED: {skip_reason or trade.get('reason') or gate.get('reason') or 'blocked'}")
    elif trade.get("order_id") or trade.get("fill_price"):
        lines.append(f"EXECUTED: fill {_fmt_inr(trade.get('fill_price') or pick.get('price'))} · order {trade.get('order_id') or 'paper'}")

    return {
        "action": "buy_skip" if (skipped or trade.get("skipped")) else "buy",
        "symbol": pick.get("symbol"),
        "thought_process": "\n".join(lines),
        "factors": {
            "technical": technical,
            "fundamentals_proxy": fundamentals_proxy,
            "timing": timing,
            "risk_budget": risk_budget,
            "rag_learning": rag,
            "psychology": psychology,
        },
        "score_breakdown": reasons,
        "gates_passed": gates_passed,
        "gates_failed": gates_failed,
    }


def build_sell_rationale(
    *,
    symbol: str,
    entry_price: float,
    exit_price: float,
    quantity: int,
    trigger: str,
    target_pct: float,
    stop_pct: float,
    max_unrealized_loss_inr: float = 0,
    eod: bool = False,
    ist_time: str = "",
    psych_exit: Optional[dict[str, Any]] = None,
    trailing_peak_ret_pct: float | None = None,
    trailing_stop_pct: float | None = None,
) -> dict[str, Any]:
    """Human + machine-readable rationale for guard exits."""
    ret_pct = ((exit_price / entry_price) - 1) * 100 if entry_price else 0.0
    unreal = round((exit_price - entry_price) * quantity, 2)

    trigger_labels = {
        "target_hit": f"Profit target hit (+{target_pct}% configured)",
        "stop_hit": f"Stop loss hit (−{stop_pct}% configured)",
        "eod_square_off": "End-of-day square-off (MIS must close before market close)",
        "unrealized_loss_cap": f"Unrealized loss cap ({_fmt_inr(max_unrealized_loss_inr)} per position rule)",
        "psych_take_profit": "Psychology take-profit — greed/euphoria; book before crowd reversal",
        "psych_fear_cut": "Psychology fear cut — defensive/panic mood; tighter exit than standard stop",
        "trailing_stop": "Trailing stop — locked profit after arm threshold; exit on pullback from peak",
    }
    label = trigger_labels.get(trigger, trigger)

    lines = [
        f"SELL {symbol} × {quantity}",
        f"Entry {_fmt_inr(entry_price)} → exit {_fmt_inr(exit_price)} ({ret_pct:+.2f}%) · P&L {_fmt_inr(unreal)}",
        f"Trigger: {label}",
        f"Rules checked: target +{target_pct}% | stop −{stop_pct}% | EOD={'yes' if eod else 'no'}",
    ]
    if trigger == "target_hit":
        lines.append("Take profit — price reached intraday target; booking gain.")
    elif trigger == "stop_hit":
        lines.append("Cut loss — price breached stop; limiting downside.")
    elif trigger == "eod_square_off":
        lines.append("Mandatory MIS exit — no overnight carry; flat before close.")
    elif trigger == "unrealized_loss_cap":
        lines.append("Risk halt — unrealized loss exceeded configured cap.")
    elif trigger == "psych_take_profit":
        lines.append(str((psych_exit or {}).get("note") or "Early profit — crowd greed/euphoria signals."))
    elif trigger == "psych_fear_cut":
        lines.append(str((psych_exit or {}).get("note") or "Early cut — fear/defensive crowd mood."))
    elif trigger == "trailing_stop":
        peak = trailing_peak_ret_pct if trailing_peak_ret_pct is not None else ret_pct
        trail = trailing_stop_pct if trailing_stop_pct is not None else 0.5
        lines.append(
            f"Trailing exit — peak was +{peak:.2f}%; price pulled back {trail:.2f}% from peak; booking gain."
        )

    psych = (psych_exit or {}).get("psychology") or {}
    if psych.get("primary_mood") or psych_exit:
        lines.append(
            f"Psychology at exit: mood {(psych_exit or {}).get('primary_mood') or psych.get('primary_mood') or '—'}"
            + (f" · sentiment {(psych_exit or {}).get('sentiment_score')}" if (psych_exit or {}).get("sentiment_score") is not None else "")
            + (f" · RSI {(psych_exit or {}).get('rsi_14')}" if (psych_exit or {}).get("rsi_14") is not None else "")
        )

    return {
        "action": "sell",
        "symbol": symbol,
        "trigger": trigger,
        "thought_process": "\n".join(lines),
        "math": {
            "entry_price": entry_price,
            "exit_price": exit_price,
            "quantity": quantity,
            "return_pct": round(ret_pct, 3),
            "pnl_inr": unreal,
        },
        "thresholds": {
            "target_pct": target_pct,
            "stop_pct": stop_pct,
            "max_unrealized_loss_inr": max_unrealized_loss_inr,
            "eod_active": eod,
            "ist_time": ist_time,
        },
        "factors": {
            "technical": {"note": "Price % rules + psychology overlay on guard."},
            "psychology": {
                "included_in_rules": PSYCHOLOGY_IN_TRADE_RULES,
                "exit": psych_exit or {},
                "note": PSYCHOLOGY_NOTE,
            },
        },
    }


def log_trade_decision(
    *,
    session_id: Optional[str],
    side: str,
    symbol: str,
    rationale: dict[str, Any],
    cycle_id: str = "",
) -> dict[str, Any]:
    """Persist decision + optional session event for UI audit."""
    from trading.pick_learning import append_trade_decision

    entry = append_trade_decision(
        session_id=session_id,
        side=side,
        symbol=symbol,
        rationale=rationale,
    )
    if session_id:
        try:
            from trading.session_history import log_event

            title = rationale.get("thought_process", "").split("\n")[0] or f"{side.upper()} {symbol}"
            log_event(
                session_id,
                event_type="trade_decision",
                title=title[:200],
                detail={"decision_rationale": rationale, "side": side, "symbol": symbol},
                level="action" if side == "buy" else ("warn" if side == "sell" and rationale.get("trigger") == "stop_hit" else "action"),
                symbol=symbol,
                cycle_id=cycle_id,
            )
        except Exception:
            pass
    return entry
