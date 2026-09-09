"""Hard risk caps before live MIS / autopilot orders."""
from __future__ import annotations

from typing import Any, Callable, Optional

from trading.config_store import is_live_execution, load_trading_config
from trading.paper_ledger import daily_stats, is_trading_halted, mark_trading_halted, open_positions


class RiskBlocked(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def compute_unrealized_pnl(
    quote_fn: Optional[Callable[[str], float]] = None,
    *,
    session_id: str | None = None,
) -> float:
    """Mark open MIS positions to market; returns total unrealized INR."""
    total = 0.0
    positions = open_positions("mis", session_id=session_id) if session_id else open_positions("mis")
    for pos in positions:
        qty = int(pos.get("quantity") or 0)
        entry = float(pos.get("avg_price") or 0)
        if qty <= 0 or entry <= 0:
            continue
        sym = str(pos.get("symbol") or "")
        mark = entry
        if quote_fn:
            try:
                px = float(quote_fn(sym))
                if px > 0:
                    mark = px
            except Exception:
                pass
        total += (mark - entry) * qty
    return round(total, 2)


def get_risk_snapshot(quote_fn: Optional[Callable[[str], float]] = None) -> dict[str, Any]:
    cfg = load_trading_config()
    risk = cfg.get("risk") or {}
    daily = daily_stats()
    halted, halt_reason = is_trading_halted()
    unreal = compute_unrealized_pnl(quote_fn)
    realized = float(daily.get("realized_pnl_inr") or 0)
    buy_notional = float(daily.get("buy_notional_inr") or 0)
    return {
        "halted": halted,
        "halt_reason": halt_reason,
        "daily": daily,
        "realized_pnl_inr": realized,
        "realized_pnl_label": "realized",
        "unrealized_pnl_inr": unreal,
        "total_pnl_inr": round(realized + unreal, 2),
        "total_pnl_label": "realized_plus_unrealized",
        "buy_notional_used_inr": buy_notional,
        "buy_notional_cap_inr": float(risk.get("max_daily_notional_inr") or 0),
        "open_positions": len(open_positions("mis")),
        "caps": {
            "max_intraday_loss_inr": float(risk.get("max_intraday_loss_inr") or 5000),
            "max_profit_inr": float(risk.get("max_profit_inr") or 0),
            "max_unrealized_loss_inr": float(risk.get("max_unrealized_loss_inr") or 0),
            "max_position_inr": float(risk.get("max_position_inr") or 50000),
            "max_daily_notional_inr": float(risk.get("max_daily_notional_inr") or 100000),
            "max_orders_per_day": int(risk.get("max_orders_per_day") or 5),
            "max_open_positions": int(risk.get("max_open_positions") or 3),
        },
    }


def validate_order(
    payload: dict[str, Any],
    *,
    fill_price: float | None = None,
    skip_watchlist: bool = False,
) -> dict[str, Any]:
    cfg = load_trading_config()
    risk = cfg.get("risk") or {}
    symbol = str(payload.get("symbol", "")).upper()
    product = str(payload.get("product") or "mis").lower()
    qty = int(payload.get("quantity") or 0)
    side = str(payload.get("side", "buy")).lower()
    live = is_live_execution(cfg)

    # Exit orders (stop/EOD square-off) must never be blocked by buy-side caps.
    if side == "sell":
        if live and risk.get("block_live_without_arm") and not cfg.get("live_armed"):
            raise RiskBlocked("live_not_armed", "Live mode requires live_armed=true in trading config.")
        return {
            "allowed": True,
            "mode": "live" if live else "paper",
            "checks_passed": ["exit_order"],
        }

    halted, halt_reason = is_trading_halted()
    if halted and side == "buy":
        raise RiskBlocked("trading_halted", halt_reason or "Auto trading halted for today.")

    if live and risk.get("block_live_without_arm") and not cfg.get("live_armed"):
        raise RiskBlocked("live_not_armed", "Live mode requires live_armed=true in trading config.")

    if not skip_watchlist and product in {"mis", "intraday"} and side == "buy":
        whitelist = risk.get("symbol_whitelist") or []
        watchlist = [s.upper() for s in (cfg.get("watchlist") or [])]
        allowed = set(whitelist) | set(watchlist)
        if allowed and symbol not in allowed:
            raise RiskBlocked("symbol_not_allowed", f"{symbol} not in watchlist/whitelist.")

    daily = daily_stats()
    max_orders = int(risk.get("max_orders_per_day") or 5)
    if side == "buy" and int(daily.get("orders") or 0) >= max_orders:
        raise RiskBlocked("max_orders", f"Daily order cap reached ({max_orders}).")

    max_loss = float(risk.get("max_intraday_loss_inr") or 5000)
    realized = float(daily.get("realized_pnl_inr") or 0)
    if realized <= -max_loss:
        mark_trading_halted("max_loss", f"Daily loss cap ₹{max_loss} hit.")
        raise RiskBlocked("max_loss", f"Daily loss cap hit (₹{max_loss}). Trading halted for today.")

    max_profit = float(risk.get("max_profit_inr") or 0)
    if side == "buy" and max_profit > 0 and risk.get("halt_new_buys_on_profit", True):
        if realized >= max_profit:
            mark_trading_halted("profit_target", f"Daily profit target ₹{max_profit} reached.")
            raise RiskBlocked("profit_target", f"Daily profit cap ₹{max_profit} hit — new buys blocked.")

    open_p = open_positions("mis")
    max_open = int(risk.get("max_open_positions") or 3)
    if side == "buy" and len(open_p) >= max_open:
        existing = any(p.get("symbol") == symbol for p in open_p)
        if not existing:
            raise RiskBlocked("max_positions", f"Max open positions ({max_open}).")

    px = fill_price
    if px is None:
        px = float(payload.get("limit_price") or 0)
    if px and qty:
        notional = px * qty
        max_pos = float(risk.get("max_position_inr") or 50000)
        # Cap applies to new buys only — full-position sells must not be blocked at EOD.
        if side == "buy" and notional > max_pos:
            raise RiskBlocked("max_notional", f"Order notional ₹{notional:.0f} exceeds cap ₹{max_pos:.0f}.")

        if side == "buy":
            max_daily = float(risk.get("max_daily_notional_inr") or 100000)
            used = float(daily.get("buy_notional_inr") or 0)
            if used + notional > max_daily:
                raise RiskBlocked(
                    "max_daily_notional",
                    f"Daily buy bucket ₹{used:.0f}+₹{notional:.0f} exceeds cap ₹{max_daily:.0f}.",
                )

    if side == "buy":
        max_unreal = float(risk.get("max_unrealized_loss_inr") or 0)
        if max_unreal > 0:
            unreal = compute_unrealized_pnl()
            if unreal <= -max_unreal:
                mark_trading_halted("unrealized_loss_cap", f"Unrealized loss ₹{abs(unreal):.0f}")
                raise RiskBlocked(
                    "unrealized_loss_cap",
                    f"Unrealized loss ₹{abs(unreal):.0f} exceeds cap ₹{max_unreal}.",
                )

    return {
        "allowed": True,
        "mode": "live" if live else "paper",
        "checks_passed": [
            "halt_flag",
            "daily_orders",
            "daily_loss",
            "daily_profit",
            "positions",
            "notional",
            "daily_notional",
            "unrealized",
            "symbol",
        ],
    }


def validate_auto_entry(
    payload: dict[str, Any],
    *,
    fill_price: float,
    source: str,
    composite_score: Optional[float] = None,
) -> dict[str, Any]:
    """Stricter gates for agent/autopilot buy entries."""
    cfg = load_trading_config()
    risk = cfg.get("risk") or {}
    side = str(payload.get("side", "buy")).lower()
    auto_sources = {"genai_agent", "agent", "autopilot"}

    base = validate_order(payload, fill_price=fill_price, skip_watchlist=(source in auto_sources))

    if source not in auto_sources or side != "buy":
        return base

    min_score = float(risk.get("agent_min_composite") or cfg.get("autopilot", {}).get("entry_min_composite") or 55)
    if composite_score is not None and float(composite_score) < min_score:
        raise RiskBlocked("min_composite", f"Composite {composite_score:.1f} below auto minimum {min_score}.")

    max_profit = float(risk.get("max_profit_inr") or 0)
    if max_profit > 0 and risk.get("halt_new_buys_on_profit", True):
        daily = daily_stats()
        realized = float(daily.get("realized_pnl_inr") or 0)
        if realized >= max_profit:
            mark_trading_halted("profit_target", f"Daily profit target ₹{max_profit} reached.")
            raise RiskBlocked("profit_target", f"Daily profit cap ₹{max_profit} hit — new auto entries blocked.")

    return base
