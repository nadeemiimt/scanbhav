"""Local paper order book + intraday MIS positions."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from config import BASE_DIR

LEDGER_PATH = BASE_DIR / "data" / "trading" / "paper_ledger.json"
DAILY_PATH = BASE_DIR / "data" / "trading" / "daily_stats.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_ist() -> str:
    from datetime import timedelta

    ist = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(ist).strftime("%Y-%m-%d")


def _load(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps(default, indent=2), encoding="utf-8")
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def list_orders(limit: int = 100) -> list[dict[str, Any]]:
    data = _load(LEDGER_PATH, {"orders": [], "positions": []})
    return list(reversed((data.get("orders") or [])[-limit:]))


def open_positions(product: str | None = None, session_id: str | None = None) -> list[dict[str, Any]]:
    data = _load(LEDGER_PATH, {"orders": [], "positions": []})
    pos = data.get("positions") or []
    out = [p for p in pos if p.get("status") == "open"]
    if product:
        out = [p for p in out if p.get("product") == product]
    if session_id is not None:
        sid = str(session_id)
        out = [p for p in out if str(p.get("session_id") or "") == sid]
    return out


def _position_key(symbol: str, product: str, session_id: str | None) -> tuple[str, str, str]:
    return (symbol.upper(), product.lower(), str(session_id or ""))


def _find_open_position(
    positions: list[dict[str, Any]],
    symbol: str,
    product: str,
    session_id: str | None,
) -> dict[str, Any] | None:
    key = _position_key(symbol, product, session_id)
    return next(
        (
            p for p in positions
            if p.get("status") == "open"
            and _position_key(str(p.get("symbol") or ""), str(p.get("product") or "mis"), p.get("session_id")) == key
        ),
        None,
    )


def mark_position_flag(
    symbol: str,
    *,
    field: str,
    value: Any,
    product: str = "mis",
    session_id: str | None = None,
) -> None:
    """Set a metadata flag on an open position (e.g. partial_taken)."""
    from trading.store_lock import LOCK

    with LOCK:
        data = _load(LEDGER_PATH, {"orders": [], "positions": []})
        pos = _find_open_position(data.get("positions") or [], symbol, product, session_id)
        if not pos and session_id is not None:
            pos = _find_open_position(data.get("positions") or [], symbol, product, None)
        if not pos:
            return
        pos[field] = value
        pos["updated_at"] = _now()
        _save(LEDGER_PATH, data)


def update_trailing_peak(
    symbol: str,
    price: float,
    *,
    product: str = "mis",
    arm_pct: float = 1.0,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Track peak price for trailing stop; persists on open position."""
    sym = str(symbol or "").upper()
    data = _load(LEDGER_PATH, {"orders": [], "positions": []})
    pos = _find_open_position(data.get("positions") or [], sym, product, session_id)
    if not pos and session_id is not None:
        pos = _find_open_position(data.get("positions") or [], sym, product, None)
    if not pos:
        return {}
    entry = float(pos.get("avg_price") or 0)
    if entry <= 0 or price <= 0:
        return {}
    peak = float(pos.get("trailing_peak_price") or entry)
    if price > peak:
        peak = price
        pos["trailing_peak_price"] = round(peak, 4)
    peak_ret = ((peak / entry) - 1) * 100
    if peak_ret >= arm_pct:
        pos["trailing_armed"] = True
    pos["updated_at"] = _now()
    _save(LEDGER_PATH, data)
    return {
        "peak_price": round(peak, 4),
        "peak_ret_pct": round(peak_ret, 3),
        "trailing_armed": bool(pos.get("trailing_armed")),
    }


def record_paper_order(
    *,
    payload: dict[str, Any],
    fill_price: float,
    source: str = "paper",
) -> dict[str, Any]:
    from trading.store_lock import LOCK

    with LOCK:
        return _record_paper_order_locked(
            payload=payload, fill_price=fill_price, source=source,
        )


def _record_paper_order_locked(
    *,
    payload: dict[str, Any],
    fill_price: float,
    source: str = "paper",
) -> dict[str, Any]:
    data = _load(LEDGER_PATH, {"orders": [], "positions": []})
    order_id = f"PAPER-{uuid.uuid4().hex[:12].upper()}"
    side = str(payload.get("side", "buy")).lower()
    qty = int(payload.get("quantity") or 0)
    symbol = str(payload.get("symbol", "")).upper()
    product = str(payload.get("product") or "mis").lower()
    session_id = payload.get("session_id")
    position_meta = payload.get("position_meta") if isinstance(payload.get("position_meta"), dict) else None
    notional = round(fill_price * qty, 2)
    order = {
        "order_id": order_id,
        "status": "filled_paper",
        "mode": "paper",
        "broker": payload.get("broker") or "paper",
        "symbol": symbol,
        "side": side,
        "quantity": qty,
        "fill_price": round(float(fill_price), 4),
        "notional_inr": notional,
        "order_type": payload.get("order_type"),
        "product": product,
        "trade_id": payload.get("trade_id"),
        "session_id": session_id,
        "source": source,
        "created_at": _now(),
    }
    data.setdefault("orders", []).append(order)
    _apply_position(
        data, symbol, side, qty, fill_price, product, order_id,
        session_id=session_id, position_meta=position_meta,
    )
    _save(LEDGER_PATH, data)
    _bump_daily_orders(buy_notional=notional if side == "buy" else 0.0)
    return order


def record_shadow_fill(
    *,
    payload: dict[str, Any],
    fill_price: float,
    source: str = "live",
    mode: str = "live",
) -> dict[str, Any]:
    """Track live broker fills locally for risk/PnL (shadow ledger)."""
    data = _load(LEDGER_PATH, {"orders": [], "positions": []})
    order_id = f"LIVE-{uuid.uuid4().hex[:12].upper()}"
    side = str(payload.get("side", "buy")).lower()
    qty = int(payload.get("quantity") or 0)
    symbol = str(payload.get("symbol", "")).upper()
    product = str(payload.get("product") or "mis").lower()
    session_id = payload.get("session_id")
    position_meta = payload.get("position_meta") if isinstance(payload.get("position_meta"), dict) else None
    notional = round(fill_price * qty, 2)
    order = {
        "order_id": order_id,
        "status": "filled_live_shadow",
        "mode": mode,
        "broker": payload.get("broker") or "live",
        "symbol": symbol,
        "side": side,
        "quantity": qty,
        "fill_price": round(float(fill_price), 4),
        "notional_inr": notional,
        "order_type": payload.get("order_type"),
        "product": product,
        "trade_id": payload.get("trade_id"),
        "session_id": session_id,
        "source": source,
        "created_at": _now(),
    }
    data.setdefault("orders", []).append(order)
    _apply_position(
        data, symbol, side, qty, fill_price, product, order_id,
        session_id=session_id, position_meta=position_meta,
    )
    _save(LEDGER_PATH, data)
    _bump_daily_orders(buy_notional=notional if side == "buy" else 0.0)
    return order


def _apply_position(
    data: dict[str, Any],
    symbol: str,
    side: str,
    qty: int,
    price: float,
    product: str,
    order_id: str,
    *,
    session_id: str | None = None,
    position_meta: dict[str, Any] | None = None,
) -> None:
    positions: list[dict[str, Any]] = data.setdefault("positions", [])
    open_pos = _find_open_position(positions, symbol, product, session_id)
    if side == "buy":
        if open_pos:
            old_qty = int(open_pos.get("quantity") or 0)
            old_avg = float(open_pos.get("avg_price") or price)
            new_qty = old_qty + qty
            open_pos["avg_price"] = round((old_avg * old_qty + price * qty) / new_qty, 4)
            open_pos["quantity"] = new_qty
            open_pos["updated_at"] = _now()
            ids = list(open_pos.get("order_ids") or [])
            ids.append(order_id)
            open_pos["order_ids"] = ids
            if position_meta:
                for key, val in position_meta.items():
                    if val is not None:
                        open_pos[key] = val
        else:
            pos_row: dict[str, Any] = {
                "id": str(uuid.uuid4()),
                "symbol": symbol,
                "product": product,
                "session_id": session_id,
                "status": "open",
                "quantity": qty,
                "avg_price": round(price, 4),
                "opened_at": _now(),
                "order_ids": [order_id],
            }
            if position_meta:
                pos_row.update({k: v for k, v in position_meta.items() if v is not None})
            positions.append(pos_row)
    elif side == "sell":
        if not open_pos and session_id is not None:
            open_pos = _find_open_position(positions, symbol, product, None)
        if open_pos:
            old_qty = int(open_pos.get("quantity") or 0)
            avg = float(open_pos.get("avg_price") or price)
            sell_qty = min(qty, old_qty)
            pnl = round((price - avg) * sell_qty, 2)
            open_pos["quantity"] = old_qty - sell_qty
            open_pos["realized_pnl_inr"] = round(float(open_pos.get("realized_pnl_inr") or 0) + pnl, 2)
            open_pos["updated_at"] = _now()
            if open_pos["quantity"] <= 0:
                open_pos["status"] = "closed"
                open_pos["closed_at"] = _now()
                _record_daily_pnl(pnl)


def close_all_intraday(reason: str = "eod_square_off") -> list[dict[str, Any]]:
    """Mark open MIS positions for square-off (caller supplies prices)."""
    data = _load(LEDGER_PATH, {"orders": [], "positions": []})
    closed = []
    for p in data.get("positions") or []:
        if p.get("status") == "open" and p.get("product") in {"mis", "intraday"}:
            p["_pending_square_off"] = True
            p["square_off_reason"] = reason
            closed.append(p)
    _save(LEDGER_PATH, data)
    return closed


def sync_positions_from_broker(broker_rows: list[dict[str, Any]], *, product: str = "mis") -> dict[str, Any]:
    """Replace open shadow positions for product with broker truth."""
    data = _load(LEDGER_PATH, {"orders": [], "positions": []})
    positions: list[dict[str, Any]] = data.setdefault("positions", [])
    positions[:] = [p for p in positions if not (p.get("status") == "open" and p.get("product") == product)]
    added = 0
    for row in broker_rows:
        sym = str(row.get("symbol") or "").upper()
        qty = int(row.get("quantity") or 0)
        if not sym or qty <= 0:
            continue
        if str(row.get("product") or product).lower() != product:
            continue
        positions.append({
            "id": str(uuid.uuid4()),
            "symbol": sym,
            "product": product,
            "status": "open",
            "quantity": qty,
            "avg_price": round(float(row.get("avg_price") or 0), 4),
            "opened_at": _now(),
            "source": "broker_reconcile",
            "broker": row.get("broker"),
        })
        added += 1
    _save(LEDGER_PATH, data)
    return {"synced": added, "product": product}


def record_confirmed_live_fill(
    *,
    payload: dict[str, Any],
    fill_price: float,
    broker_order_id: str,
    source: str = "live",
    filled_qty: int | None = None,
) -> dict[str, Any]:
    """Shadow ledger entry only after broker fill confirmed."""
    qty = filled_qty if filled_qty is not None else int(payload.get("quantity") or 0)
    payload = {**payload, "quantity": qty, "broker_order_id": broker_order_id}
    data = _load(LEDGER_PATH, {"orders": [], "positions": []})
    order_id = f"LIVE-{broker_order_id}"
    side = str(payload.get("side", "buy")).lower()
    symbol = str(payload.get("symbol", "")).upper()
    product = str(payload.get("product") or "mis").lower()
    session_id = payload.get("session_id")
    notional = round(fill_price * qty, 2)
    order = {
        "order_id": order_id,
        "broker_order_id": broker_order_id,
        "status": "filled_live",
        "mode": "live",
        "broker": payload.get("broker") or "live",
        "symbol": symbol,
        "side": side,
        "quantity": qty,
        "fill_price": round(float(fill_price), 4),
        "notional_inr": notional,
        "order_type": payload.get("order_type"),
        "product": product,
        "trade_id": payload.get("trade_id"),
        "session_id": session_id,
        "source": source,
        "created_at": _now(),
    }
    data.setdefault("orders", []).append(order)
    _apply_position(data, symbol, side, qty, fill_price, product, order_id, session_id=session_id)
    _save(LEDGER_PATH, data)
    if side == "buy":
        _bump_daily_orders(buy_notional=notional)
    else:
        _bump_daily_orders(buy_notional=0.0)
    return order


def square_off_position(
    symbol: str,
    price: float,
    product: str = "mis",
    session_id: str | None = None,
    *,
    reason: str = "eod_square_off",
) -> Optional[dict[str, Any]]:
    data = _load(LEDGER_PATH, {"orders": [], "positions": []})
    pos = _find_open_position(data.get("positions") or [], symbol, product, session_id)
    if not pos and session_id is not None:
        pos = _find_open_position(data.get("positions") or [], symbol, product, None)
    if not pos:
        return None
    qty = int(pos.get("quantity") or 0)
    if qty <= 0:
        return None
    payload = {
        "symbol": symbol,
        "side": "sell",
        "quantity": qty,
        "product": product,
        "broker": "paper",
        "session_id": pos.get("session_id"),
    }
    order = record_paper_order(payload=payload, fill_price=price, source="eod_square_off")
    if order:
        entry = float(pos.get("avg_price") or 0)
        qty_closed = int(pos.get("quantity") or 0)
        try:
            from trading.pick_learning import on_trade_closed

            on_trade_closed(
                symbol=symbol,
                exit_price=price,
                entry_price=entry,
                quantity=qty_closed,
                reason=reason,
                order_id=order.get("order_id"),
                session_id=pos.get("session_id"),
            )
        except Exception:
            pass
    return order


def close_session_mis_positions(
    *,
    session_id: str,
    reason: str = "session_stop_square",
) -> dict[str, Any]:
    """Square off all open MIS positions for one desk session."""
    from trading.scheduler import _quote_symbol

    sid = str(session_id or "").strip()
    if not sid:
        return {"closed": [], "count": 0}
    closed: list[dict[str, Any]] = []
    for pos in list(open_positions("mis", session_id=sid)):
        sym = str(pos.get("symbol") or "").upper()
        if not sym:
            continue
        try:
            px = float(_quote_symbol(sym, "auto"))
        except Exception:
            px = float(pos.get("avg_price") or 0)
        if px <= 0:
            px = float(pos.get("avg_price") or 0)
        order = square_off_position(sym, px, session_id=sid, reason=reason)
        if order:
            closed.append({
                "symbol": sym,
                "session_id": sid,
                "quantity": int(pos.get("quantity") or 0),
                "price": px,
                "order_id": order.get("id") or order.get("order_id"),
                "reason": reason,
            })
    return {"closed": closed, "count": len(closed)}


def close_orphan_mis_positions(
    *,
    active_session_ids: set[str] | None = None,
    close_all: bool = False,
    reason: str = "orphan_cleanup",
) -> dict[str, Any]:
    """Square off open MIS positions outside active desk sessions (or all when close_all)."""
    from trading.scheduler import _quote_symbol

    active = {str(s) for s in (active_session_ids or []) if s}
    closed: list[dict[str, Any]] = []
    for pos in list(open_positions("mis")):
        sid = str(pos.get("session_id") or "")
        if not close_all and active and sid in active:
            continue
        sym = str(pos.get("symbol") or "").upper()
        if not sym:
            continue
        try:
            px = float(_quote_symbol(sym, "auto"))
        except Exception:
            px = float(pos.get("avg_price") or 0)
        if px <= 0:
            px = float(pos.get("avg_price") or 0)
        order = square_off_position(sym, px, session_id=sid or None, reason=reason)
        if order:
            closed.append({
                "symbol": sym,
                "session_id": sid,
                "quantity": int(pos.get("quantity") or 0),
                "price": px,
                "order_id": order.get("id"),
                "reason": reason,
            })
    return {"closed": closed, "count": len(closed)}


def daily_stats() -> dict[str, Any]:
    day = _today_ist()
    data = _load(DAILY_PATH, {"days": {}})
    default = {
        "date": day,
        "orders": 0,
        "realized_pnl_inr": 0.0,
        "buy_notional_inr": 0.0,
        "live_realized_pnl_inr": 0.0,
        "halted": False,
        "halt_code": None,
        "halt_reason": None,
    }
    return {**default, **(data.get("days", {}).get(day) or {})}


def is_trading_halted() -> tuple[bool, str]:
    daily = daily_stats()
    if daily.get("halted"):
        return True, str(daily.get("halt_reason") or daily.get("halt_code") or "Trading halted")
    return False, ""


def mark_trading_halted(code: str, reason: str) -> None:
    day = _today_ist()
    data = _load(DAILY_PATH, {"days": {}})
    days = data.setdefault("days", {})
    row = days.setdefault(day, {"date": day, "orders": 0, "realized_pnl_inr": 0.0, "buy_notional_inr": 0.0})
    row["halted"] = True
    row["halt_code"] = code
    row["halt_reason"] = reason
    _save(DAILY_PATH, data)


def clear_trading_halt() -> None:
    day = _today_ist()
    data = _load(DAILY_PATH, {"days": {}})
    days = data.setdefault("days", {})
    row = days.setdefault(day, {"date": day, "orders": 0, "realized_pnl_inr": 0.0, "buy_notional_inr": 0.0})
    row["halted"] = False
    row["halt_code"] = None
    row["halt_reason"] = None
    _save(DAILY_PATH, data)


def _bump_daily_orders(*, buy_notional: float = 0.0) -> None:
    day = _today_ist()
    data = _load(DAILY_PATH, {"days": {}})
    days = data.setdefault("days", {})
    row = days.setdefault(day, {"date": day, "orders": 0, "realized_pnl_inr": 0.0, "buy_notional_inr": 0.0})
    row["orders"] = int(row.get("orders") or 0) + 1
    if buy_notional > 0:
        row["buy_notional_inr"] = round(float(row.get("buy_notional_inr") or 0) + buy_notional, 2)
    _save(DAILY_PATH, data)


def _record_daily_pnl(pnl: float) -> None:
    day = _today_ist()
    data = _load(DAILY_PATH, {"days": {}})
    days = data.setdefault("days", {})
    row = days.setdefault(day, {"date": day, "orders": 0, "realized_pnl_inr": 0.0})
    row["realized_pnl_inr"] = round(float(row.get("realized_pnl_inr") or 0) + pnl, 2)
    _save(DAILY_PATH, data)


def ledger_summary() -> dict[str, Any]:
    data = _load(LEDGER_PATH, {"orders": [], "positions": []})
    open_p = [p for p in (data.get("positions") or []) if p.get("status") == "open"]
    daily = daily_stats()
    halted, halt_reason = is_trading_halted()
    return {
        "orders_count": len(data.get("orders") or []),
        "open_positions": len(open_p),
        "positions": open_p,
        "daily": daily,
        "halted": halted,
        "halt_reason": halt_reason,
    }
