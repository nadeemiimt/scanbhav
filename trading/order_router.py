"""Unified order path: paper ledger or live broker (same as Swing desk)."""
from __future__ import annotations

from typing import Any, Optional

from brokers.service import check_margin, get_live_quotes, place_order as broker_place_order
from brokers.token_store import token_health
from trading.config_store import is_live_execution, load_trading_config
from trading.order_book import record_pending
from trading.order_lifecycle import poll_order_fill
from trading.paper_ledger import record_confirmed_live_fill, record_paper_order
from trading.risk import RiskBlocked, validate_auto_entry, validate_order


def _resolve_fill_price(payload: dict[str, Any], broker_id: str) -> tuple[float, str]:
    symbol = str(payload.get("symbol", "")).upper()
    limit = payload.get("limit_price")
    if limit and float(limit) > 0:
        return float(limit), "limit_price"
    quotes = get_live_quotes(broker_id, [symbol])
    q = (quotes.get("quotes") or {}).get(symbol) or {}
    price = q.get("price") or q.get("ltp")
    if price:
        return float(price), "broker_ltp"
    if payload.get("order_type") == "market":
        try:
            from routes.helpers import fetch_prices, rows_from_payload
            from technicals import compute_technicals

            raw = fetch_prices(symbol, "auto", force_refresh=False)
            rows = rows_from_payload(raw)
            tech = compute_technicals(rows)
            yp = tech.get("price")
            if yp and float(yp) > 0:
                return float(yp), "yfinance_fallback"
        except Exception:
            pass
        raise RuntimeError(f"No live price for {symbol}; set limit_price or connect broker quotes.")
    raise RuntimeError(f"Cannot resolve fill price for {symbol}.")


def _ensure_live_ready(broker_id: str) -> None:
    cfg = load_trading_config()
    if not is_live_execution(cfg):
        return
    bid = broker_id.lower()
    if bid == "stub":
        raise RuntimeError("Live mode requires zerodha, groww, or fyers — not stub.")
    from brokers.service import get_adapter

    adapter = get_adapter(bid)
    if not adapter.status().get("configured"):
        raise RuntimeError(f"{bid} not configured. Complete OAuth and credentials.")
    th = token_health(bid)
    if not th.get("ok"):
        raise RuntimeError(th.get("message") or f"Broker token invalid: {th.get('reason')}")


def _maybe_place_sl_m(
    *,
    payload: dict[str, Any],
    fill_price: float,
    filled_qty: int,
    broker_id: str,
    cfg: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """Place broker SL-M after confirmed MIS buy (Zerodha/Groww)."""
    risk = cfg.get("risk") or {}
    ap = cfg.get("autopilot") or {}
    if not risk.get("place_sl_m_at_entry", True):
        return None
    product = str(payload.get("product") or "mis").lower()
    if product not in {"mis", "intraday"} or str(payload.get("side")).lower() != "buy":
        return None
    stop_pct = float(ap.get("stop_pct") or risk.get("default_stop_pct") or 0.75)
    trigger = round(fill_price * (1 - stop_pct / 100.0), 2)
    sl_payload = {
        **payload,
        "side": "sell",
        "quantity": filled_qty,
        "order_type": "sl-m",
        "stop_price": trigger,
        "limit_price": trigger,
    }
    try:
        return broker_place_order(sl_payload)
    except Exception as exc:
        return {"skipped": True, "reason": "sl_m_failed", "error": str(exc)}


def execute_order(
    payload: dict[str, Any],
    *,
    source: str = "api",
    force_mode: Optional[str] = None,
    composite_score: Optional[float] = None,
    skip_auto_checks: bool = False,
) -> dict[str, Any]:
    """Route order through risk checks, then paper or live broker."""
    cfg = load_trading_config()
    broker_id = str(payload.get("broker") or cfg.get("default_broker") or "stub").lower()
    product = str(payload.get("product") or cfg.get("default_product") or "mis").lower()
    payload = {**payload, "broker": broker_id, "product": product}
    side = str(payload.get("side", "buy")).lower()

    auto_sources = {"genai_agent", "agent", "autopilot"}
    if not skip_auto_checks and not str(source).startswith("guard_") and source in auto_sources and side == "buy":
        risk_cfg = cfg.get("risk") or {}
        min_score = float(risk_cfg.get("agent_min_composite") or cfg.get("autopilot", {}).get("entry_min_composite") or 55)
        if composite_score is not None and float(composite_score) < min_score:
            raise RiskBlocked("min_composite", f"Composite {composite_score:.1f} below auto minimum {min_score}.")

    fill_price, price_source = _resolve_fill_price(payload, broker_id)
    if skip_auto_checks or str(source).startswith("guard_"):
        risk = validate_order(payload, fill_price=fill_price)
    else:
        risk = validate_auto_entry(
            payload,
            fill_price=fill_price,
            source=source,
            composite_score=composite_score,
        )

    live = force_mode == "live" or (force_mode != "paper" and is_live_execution(cfg))
    if live:
        _ensure_live_ready(broker_id)
        if side == "buy" and cfg.get("margin_check_enabled", True):
            margin = check_margin(broker_id, payload)
            if not margin.get("sufficient") and not margin.get("skipped"):
                raise RiskBlocked(
                    "insufficient_margin",
                    f"Margin insufficient (need ₹{margin.get('required_inr')}, have ₹{margin.get('available_inr')}).",
                )

        result = broker_place_order(payload)
        broker_order_id = str(result.get("order_id") or "")
        if not broker_order_id or broker_order_id.endswith("UNKNOWN"):
            raise RuntimeError(f"Broker did not return order_id: {result}")

        pending = record_pending(
            broker_order_id=broker_order_id,
            payload=payload,
            estimated_price=fill_price,
            source=source,
        )
        fill = poll_order_fill(broker_id, broker_order_id)
        if fill.get("rejected"):
            raise RuntimeError(f"Order rejected by broker: {fill.get('status')}")

        confirmed_price = float(fill.get("average_price") or fill_price)
        filled_qty = int(fill.get("filled_quantity") or payload.get("quantity") or 0)
        if filled_qty <= 0 and fill.get("confirmed"):
            filled_qty = int(payload.get("quantity") or 0)

        shadow = None
        sl_order = None
        if fill.get("confirmed") or is_live_execution(cfg):
            shadow = record_confirmed_live_fill(
                payload=payload,
                fill_price=confirmed_price,
                broker_order_id=broker_order_id,
                source=source,
                filled_qty=filled_qty,
            )
            if side == "buy":
                sl_order = _maybe_place_sl_m(
                    payload=payload,
                    fill_price=confirmed_price,
                    filled_qty=filled_qty,
                    broker_id=broker_id,
                    cfg=cfg,
                )

        result["mode"] = "live"
        result["fill_price"] = confirmed_price
        result["price_source"] = price_source if not fill.get("confirmed") else "broker_fill"
        result["risk"] = risk
        result["source"] = source
        result["pending"] = pending
        result["fill_poll"] = fill
        result["shadow_ledger"] = shadow
        result["sl_m_order"] = sl_order
        if fill.get("pending") and not shadow:
            result["status"] = "pending_confirmation"
            result["message"] = "Order submitted — fill not yet confirmed; reconcile will sync."
        return result

    paper = record_paper_order(payload=payload, fill_price=fill_price, source=source)
    paper["mode"] = "paper"
    paper["price_source"] = price_source
    paper["risk"] = risk
    paper["message"] = "Paper fill recorded at market rate (educational)."
    return paper


def agent_trade_from_signal(
    *,
    symbol: str,
    side: str,
    quantity: int,
    stance: str,
    composite_score: Optional[float] = None,
    product: str = "mis",
    source: str = "agent",
    session_id: Optional[str] = None,
    position_meta: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Agent hook — same service as Swing desk `/api/broker/order`."""
    cfg = load_trading_config()
    if stance.lower() in {"avoid", "unfavorable", "bearish", "cautious"} and side == "buy":
        return {"skipped": True, "reason": "stance_blocks_buy", "stance": stance}
    payload = {
        "symbol": symbol.upper(),
        "side": side,
        "quantity": quantity,
        "order_type": "market",
        "broker": cfg.get("default_broker") or "stub",
        "product": product,
        "trade_id": f"agent-{symbol}",
        "session_id": session_id,
    }
    if position_meta:
        payload["position_meta"] = position_meta
    try:
        return execute_order(payload, source=source, composite_score=composite_score)
    except RiskBlocked as exc:
        return {"skipped": True, "reason": exc.code, "message": exc.message}
    except RuntimeError as exc:
        return {"skipped": True, "reason": "broker_error", "message": str(exc)}
