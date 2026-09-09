"""Monitor open MIS positions — stop/target, partial scale-out, time-decay, EOD square-off."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from trading.config_store import is_live_execution, load_trading_config
from trading.intraday_rules import effective_exit_rules, ist_minutes_now
from trading.intraday_sim import market_open_ist
from trading.order_router import execute_order
from trading.paper_ledger import mark_position_flag, mark_trading_halted, open_positions, update_trailing_peak
from trading.risk import RiskBlocked


def _quote_or_avg(symbol: str, quote_fn: Callable[[str], float], avg: float) -> float:
    try:
        px = float(quote_fn(symbol))
        if px > 0:
            return px
    except Exception:
        pass
    return avg


def _execute_guard_sell(
    *,
    sym: str,
    qty: int,
    price: float,
    entry: float,
    reason: str,
    pos_session: str | None,
    session_id: str | None,
    target_pct: float,
    stop_pct: float,
    max_unreal: float,
    eod: bool,
    psych_exit: dict[str, Any],
    trail_state: dict[str, Any],
    trail_pct: float,
) -> dict[str, Any]:
    from trading.decision_rationale import build_sell_rationale, log_trade_decision
    from trading.entry_gates import record_stop_cooldown
    from trading.pick_learning import on_trade_closed

    ret_pct = ((price / entry) - 1) * 100 if entry else 0.0
    unreal = round((price - entry) * qty, 2)
    ist_now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    sell_rationale = build_sell_rationale(
        symbol=sym,
        entry_price=entry,
        exit_price=price,
        quantity=qty,
        trigger=reason,
        target_pct=target_pct,
        stop_pct=stop_pct,
        max_unrealized_loss_inr=max_unreal,
        eod=eod,
        ist_time=ist_now.strftime("%H:%M IST"),
        psych_exit=psych_exit,
        trailing_peak_ret_pct=trail_state.get("peak_ret_pct"),
        trailing_stop_pct=trail_pct if reason == "trailing_stop" else None,
    )
    if session_id:
        log_trade_decision(
            session_id=session_id,
            side="sell",
            symbol=sym,
            rationale=sell_rationale,
        )

    result = execute_order(
        {
            "symbol": sym,
            "side": "sell",
            "quantity": qty,
            "order_type": "market",
            "limit_price": price,
            "product": "mis",
            "session_id": pos_session or session_id,
        },
        source=f"guard_{reason}",
    )
    action = {
        "symbol": sym,
        "reason": reason,
        "return_pct": round(ret_pct, 2),
        "unrealized_inr": unreal,
        "quantity": qty,
        "order": result,
        "decision_rationale": sell_rationale,
    }
    if reason == "partial_scale_out":
        mark_position_flag(sym, field="partial_taken", value=True, session_id=pos_session or session_id)
        on_trade_closed(
            symbol=sym,
            exit_price=price,
            entry_price=entry,
            quantity=qty,
            reason=reason,
            order_id=(result or {}).get("order_id"),
            session_id=session_id,
            decision_rationale=sell_rationale,
        )
    else:
        if reason in {"stop_hit", "trailing_stop", "target_hit", "eod_square_off", "power_hour_profit_lock"} or str(reason).startswith("psychology_"):
            record_stop_cooldown(
                symbol=sym,
                reason=reason,
                session_id=session_id or pos_session,
                ret_pct=ret_pct,
            )
        on_trade_closed(
            symbol=sym,
            exit_price=price,
            entry_price=entry,
            quantity=qty,
            reason=reason,
            order_id=(result or {}).get("order_id"),
            session_id=session_id,
            decision_rationale=sell_rationale,
        )
    return action


def monitor_open_positions(
    quote_fn: Callable[[str], float],
    *,
    force_eod: bool = False,
    symbols: set[str] | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Exit open MIS positions on stop/target/partial/EOD/unrealized breach."""
    cfg = load_trading_config()
    risk = cfg.get("risk") or {}
    ap = cfg.get("autopilot") or {}
    mins = ist_minutes_now()
    base_stop = float(ap.get("stop_pct") or risk.get("default_stop_pct") or 0.75)
    max_unreal = float(risk.get("max_unrealized_loss_inr") or 0)
    trail_enabled = bool(ap.get("trailing_stop_enabled", True))
    eod_minute = int(ap.get("square_off_minute_ist") or 15 * 60 + 20)
    square_off_enabled = risk.get("auto_square_off_enabled", True)
    late_tighten = int(ap.get("late_tighten_minute_ist") or (15 * 60))
    scale_out_enabled = bool(ap.get("partial_scale_out_enabled", True))
    scale_out_fraction = float(ap.get("partial_scale_out_fraction") or 0.5)
    default_rules = effective_exit_rules(ap, ist_mins=mins)
    stop_pct = base_stop
    max_unreal = float(risk.get("max_unrealized_loss_inr") or 0)

    eod = force_eod or not market_open_ist() or mins >= eod_minute

    actions: list[dict[str, Any]] = []
    pos_list = open_positions("mis", session_id=session_id) if session_id else open_positions("mis")
    for pos in pos_list:
        sym = str(pos.get("symbol") or "")
        pos_session = pos.get("session_id")
        if symbols is not None and sym.upper() not in {s.upper() for s in symbols}:
            continue
        if session_id and pos_session and str(pos_session) != str(session_id):
            continue
        qty = int(pos.get("quantity") or 0)
        if not sym or qty <= 0:
            continue
        entry = float(pos.get("avg_price") or 0)
        if entry <= 0:
            continue
        price = _quote_or_avg(sym, quote_fn, entry)
        ret_pct = ((price / entry) - 1) * 100
        unreal = round((price - entry) * qty, 2)

        pos_target = float(pos.get("target_pct") or 0)
        rules = effective_exit_rules(
            ap,
            ist_mins=mins,
            base_target_pct=pos_target if pos_target > 0 else None,
        )
        target_pct = rules["target_pct"]
        trail_arm_pct = rules["trail_arm_pct"]
        trail_pct = rules["trail_pct"]
        scale_out_pct = rules["scale_out_pct"]
        power_lock_min = rules["power_hour_lock_min_pct"]
        power_lock_pullback = rules["power_hour_lock_pullback_pct"]

        reason = None
        sell_qty = qty
        psych_exit: dict[str, Any] = {}
        trail_state: dict[str, Any] = {}

        if eod:
            reason = "eod_square_off"
        elif square_off_enabled:
            if ret_pct <= -stop_pct:
                reason = "stop_hit"
            elif (
                scale_out_enabled
                and not pos.get("partial_taken")
                and ret_pct >= scale_out_pct
                and qty >= 2
            ):
                partial_qty = max(1, int(qty * scale_out_fraction))
                if partial_qty < qty:
                    reason = "partial_scale_out"
                    sell_qty = partial_qty
            elif trail_enabled:
                trail_state = update_trailing_peak(
                    sym, price, product="mis", arm_pct=trail_arm_pct, session_id=pos_session or session_id
                )
                peak_ret = float(trail_state.get("peak_ret_pct") or 0)
                if (
                    trail_state.get("trailing_armed")
                    and peak_ret >= trail_arm_pct
                    and ret_pct <= peak_ret - trail_pct
                ):
                    reason = "trailing_stop"
                elif (
                    mins >= late_tighten
                    and peak_ret >= power_lock_min
                    and ret_pct >= power_lock_min
                    and ret_pct <= peak_ret - power_lock_pullback
                ):
                    reason = "power_hour_profit_lock"
            if not reason and ret_pct >= target_pct:
                reason = "target_hit"

        if not reason and max_unreal > 0 and unreal <= -max_unreal:
            reason = "unrealized_loss_cap"
            mark_trading_halted("unrealized_loss_cap", f"Unrealized loss ₹{abs(unreal):.0f} on {sym}")

        if not reason and square_off_enabled and not eod:
            try:
                from trading.psychology_gates import evaluate_sell_psychology

                psych_exit = evaluate_sell_psychology(symbol=sym, ret_pct=ret_pct)
                if psych_exit.get("trigger"):
                    reason = str(psych_exit["trigger"])
            except Exception:
                psych_exit = {}

        if not reason:
            continue

        try:
            actions.append(
                _execute_guard_sell(
                    sym=sym,
                    qty=sell_qty,
                    price=price,
                    entry=entry,
                    reason=reason,
                    pos_session=pos_session,
                    session_id=session_id,
                    target_pct=target_pct,
                    stop_pct=stop_pct,
                    max_unreal=max_unreal,
                    eod=eod,
                    psych_exit=psych_exit,
                    trail_state=trail_state,
                    trail_pct=trail_pct,
                )
            )
        except RiskBlocked as exc:
            cfg = load_trading_config()
            if is_live_execution(cfg) and cfg.get("live_armed"):
                actions.append({
                    "symbol": sym,
                    "reason": reason,
                    "error": "live_exit_blocked",
                    "risk_note": exc.message,
                })
            else:
                actions.append({
                    "symbol": sym,
                    "reason": reason,
                    "skipped": True,
                    "risk_note": exc.message,
                })
        except RuntimeError as exc:
            actions.append({"symbol": sym, "reason": reason, "error": str(exc)})

    return {"actions": actions, "eod": eod, "exit_rules": default_rules}
