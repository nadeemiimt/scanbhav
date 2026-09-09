"""Entry / exit plan helpers for intraday (MIS) and swing desks."""
from __future__ import annotations

from typing import Any, Optional

from trading.config_store import load_trading_config


def _pct_levels(price: float, target_pct: float, stop_pct: float) -> dict[str, float]:
    return {
        "entry_price_inr": round(price, 2),
        "target_price_inr": round(price * (1 + target_pct / 100), 2),
        "stop_price_inr": round(price * (1 - stop_pct / 100), 2),
        "target_pct": target_pct,
        "stop_pct": stop_pct,
    }


def _timing_summary(gate: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not gate:
        return {
            "allowed": None,
            "window_id": None,
            "window_label": None,
            "reason": "Timing check at entry — waits for favorable IST window",
        }
    window = gate.get("window") or {}
    return {
        "allowed": gate.get("allowed"),
        "window_id": window.get("id"),
        "window_label": window.get("label") or window.get("ist_time"),
        "reason": gate.get("reason") or gate.get("detail"),
        "preemptive": gate.get("preemptive"),
        "lead_seconds": gate.get("lead_seconds"),
    }


def intraday_rules_from_config(cfg: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    cfg = cfg or load_trading_config()
    ap = cfg.get("autopilot") or {}
    risk = cfg.get("risk") or {}
    target_pct = float(ap.get("target_pct") or risk.get("default_target_pct") or 1.5)
    stop_pct = float(ap.get("stop_pct") or risk.get("default_stop_pct") or 0.75)
    eod_minute = int(ap.get("square_off_minute_ist") or 15 * 60 + 20)
    min_composite = float(
        risk.get("agent_min_composite") or ap.get("entry_min_composite") or 55.0
    )
    return {
        "style": "intraday_mis",
        "product": "MIS",
        "horizon": "same day",
        "target_pct": target_pct,
        "stop_pct": stop_pct,
        "min_composite": min_composite,
        "square_off_ist": f"{eod_minute // 60:02d}:{eod_minute % 60:02d}",
        "entry_strategy": (
            "Market buy at LTP when timing gate allows (open drive / morning trend windows); "
            "latency compensation may pre-empt by a few seconds"
        ),
        "exit_strategy": (
            f"Sell full qty on +{target_pct:.2f}% target, −{stop_pct:.2f}% stop, "
            f"unrealized loss cap, or mandatory square-off by {eod_minute // 60:02d}:{eod_minute % 60:02d} IST"
        ),
        "reentry": "After profit booked, symbol may re-enter if caps and timing allow",
        "timing_gate_enabled": bool(ap.get("timing_gate_auto_trades", True)),
        "latency_compensation": bool(ap.get("latency_compensation_enabled", True)),
    }


def swing_rules_summary() -> dict[str, Any]:
    return {
        "style": "swing",
        "product": "CNC / delivery",
        "horizon": "1W default (5 hold days) or 1M (22 hold days)",
        "entry_strategy": "Pullback to support / plan entry from swing setup scan (ATR-based sizing)",
        "exit_strategy": "Stop at ATR×1.5 below entry; targets at 1R and 2R; optional trailing stop",
        "sizing": "Risk 1% of capital per trade; shares = risk ₹ ÷ (entry − stop)",
        "note": "Use Swing desk → Setup scan for symbol-specific entry/stop/target levels",
    }


def build_intraday_plan(
    row: dict[str, Any],
    *,
    cfg: Optional[dict[str, Any]] = None,
    timing_gate: Optional[dict[str, Any]] = None,
    entry_price: Optional[float] = None,
) -> dict[str, Any]:
    """Build MIS entry/exit plan for one symbol row (pick, audit, or quote-only)."""
    cfg = cfg or load_trading_config()
    rules = intraday_rules_from_config(cfg)
    sym = str(row.get("symbol") or "").upper()
    price = float(entry_price if entry_price is not None else (row.get("price") or 0))
    qty = int(row.get("quantity") or 0)
    notional = float(row.get("notional_inr") or (price * qty if price and qty else 0))

    entry: dict[str, Any] = {
        "type": "market_mis",
        "when": "Timing gate open + composite ≥ min",
        "timing": _timing_summary(timing_gate or row.get("entry_timing_now") or row.get("timing")),
    }
    exit_plan: dict[str, Any] = {
        "type": "percent_from_fill",
        "target_pct": rules["target_pct"],
        "stop_pct": rules["stop_pct"],
        "square_off_ist": rules["square_off_ist"],
        "triggers": ["target_hit", "stop_hit", "eod_square_off", "unrealized_loss_cap"],
    }

    if price > 0:
        levels = _pct_levels(price, rules["target_pct"], rules["stop_pct"])
        entry.update(levels)
        exit_plan.update({
            "target_price_inr": levels["target_price_inr"],
            "stop_price_inr": levels["stop_price_inr"],
            "expected_profit_inr": row.get("expected_profit_inr")
            or round(notional * rules["target_pct"] / 100, 2) if notional else None,
        })

    return {
        "symbol": sym,
        "style": "intraday",
        "stance": row.get("stance"),
        "composite_score": row.get("composite_score"),
        "pick_score": row.get("pick_score"),
        "quantity": qty or None,
        "notional_inr": round(notional, 2) if notional else None,
        "entry": entry,
        "exit": exit_plan,
        "fit_reason": row.get("fit_reason") or row.get("reason"),
        "reasons": row.get("reasons"),
    }


def enrich_row_with_plan(
    row: dict[str, Any],
    *,
    cfg: Optional[dict[str, Any]] = None,
    timing_gate: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    out = dict(row)
    out["plan"] = build_intraday_plan(row, cfg=cfg, timing_gate=timing_gate)
    return out


def build_plan_preview(symbols: list[str], *, max_picks: int = 10) -> dict[str, Any]:
    """Dry-run entry/exit plans for curated symbols (no orders)."""
    cfg = load_trading_config()
    sym_list = [s.upper().strip() for s in symbols if s and str(s).strip()]
    payload: dict[str, Any] = {
        "intraday_rules": intraday_rules_from_config(cfg),
        "swing_rules": swing_rules_summary(),
        "symbols": [],
        "planned_picks": [],
        "universe_audit": [],
        "error": None,
    }
    if not sym_list:
        return payload

    try:
        from trading.agent_picker import run_given_stock_trades

        pick_result = run_given_stock_trades(
            execute=False,
            max_picks=min(max_picks, len(sym_list)),
            symbols=sym_list,
        )
    except Exception as exc:
        payload["error"] = str(exc)
        return payload

    audit_by_sym = {
        str(r.get("symbol") or "").upper(): r
        for r in (pick_result.get("universe_audit") or [])
    }

    for sym in sym_list:
        row = audit_by_sym.get(sym.upper(), {"symbol": sym})
        timing_gate = None
        try:
            from trading.latency_compensation import compensated_entry_allowed

            timing_gate = compensated_entry_allowed(symbol=sym)
        except Exception:
            pass
        if float(row.get("price") or 0) <= 0:
            try:
                from trading.scheduler import _quote_symbol

                px = float(_quote_symbol(sym))
                if px > 0:
                    row = {**row, "price": px}
            except Exception:
                pass
        payload["symbols"].append(
            enrich_row_with_plan(row, cfg=cfg, timing_gate=timing_gate)
        )

    for pick in pick_result.get("picks") or []:
        timing_gate = None
        sym = str(pick.get("symbol") or "")
        try:
            from trading.latency_compensation import compensated_entry_allowed

            timing_gate = compensated_entry_allowed(symbol=sym)
        except Exception:
            pass
        payload["planned_picks"].append(
            enrich_row_with_plan(pick, cfg=cfg, timing_gate=timing_gate)
        )

    payload["universe_audit"] = [
        enrich_row_with_plan(r, cfg=cfg) for r in (pick_result.get("universe_audit") or [])
    ]
    payload["budget"] = pick_result.get("budget")
    payload["target_pct"] = pick_result.get("target_pct")
    payload["min_composite"] = pick_result.get("min_composite")
    return payload
