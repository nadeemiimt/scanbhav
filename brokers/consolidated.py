"""Consolidated holdings + sell-all across Zerodha / Groww / FYERS."""
from __future__ import annotations

from typing import Any, Literal, Optional

from brokers.payout_account import load_payout_account, payout_summary
from brokers.service import get_adapter
from portfolio import compute_tax, estimate_charges
from trading.order_router import execute_order

BROKERS_TO_SYNC = ("zerodha", "groww", "fyers")


def fetch_consolidated_holdings(brokers: Optional[list[str]] = None) -> dict[str, Any]:
    """Pull holdings from each configured broker adapter."""
    targets = brokers or list(BROKERS_TO_SYNC)
    by_broker: dict[str, list[dict[str, Any]]] = {}
    errors: list[str] = []
    all_rows: list[dict[str, Any]] = []

    for bid in targets:
        try:
            adapter = get_adapter(bid)
            st = adapter.status()
            if not st.get("configured"):
                errors.append(f"{bid}: not connected — add credentials or complete OAuth.")
                by_broker[bid] = []
                continue
            pack = adapter.get_holdings()
            rows = pack.get("holdings") or []
            by_broker[bid] = rows
            all_rows.extend(rows)
            for err in pack.get("errors") or []:
                errors.append(f"{bid}: {err}")
        except Exception as exc:
            errors.append(f"{bid}: {exc}")
            by_broker[bid] = []

    totals = _holding_totals(all_rows)
    return {
        "holdings": all_rows,
        "by_broker": by_broker,
        "brokers": {b: len(by_broker.get(b) or []) for b in targets},
        "totals": totals,
        "errors": errors,
        "disclaimer": (
            "Live holdings from broker APIs when connected. "
            "Historical research still uses Yahoo/NSE. Verify before placing orders."
        ),
    }


def _holding_totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    invested = sum(float(r.get("invested") or 0) for r in rows)
    mkt = sum(float(r.get("market_value") or 0) for r in rows)
    pnl = sum(float(r.get("pnl") or 0) for r in rows)
    stocks = [r for r in rows if r.get("asset_type") == "stock"]
    mfs = [r for r in rows if r.get("asset_type") == "mutual_fund"]
    return {
        "positions": len(rows),
        "stock_positions": len(stocks),
        "mf_positions": len(mfs),
        "invested": round(invested, 2),
        "market_value": round(mkt, 2),
        "unrealized_pnl": round(pnl, 2),
        "unrealized_pnl_pct": round(pnl / invested * 100, 2) if invested else None,
    }


def sell_all_preview(
    holdings: Optional[list[dict[str, Any]]] = None,
    *,
    tax_bracket_rate_pct: float = 30.0,
    include_mf: bool = False,
) -> dict[str, Any]:
    pack = fetch_consolidated_holdings() if holdings is None else {"holdings": holdings, "totals": _holding_totals(holdings)}
    rows = pack.get("holdings") or []
    lines: list[dict[str, Any]] = []
    total_market = 0.0
    total_fees = 0.0
    total_tax = 0.0
    total_net = 0.0
    ltcg_exempt = 125_000.0

    for h in rows:
        if h.get("asset_type") == "mutual_fund" and not include_mf:
            lines.append({**h, "included_in_sell": False, "note": "MF — preview only; redeem via broker MF flow."})
            continue
        if not h.get("sellable", True):
            lines.append({**h, "included_in_sell": False, "note": "Not sellable via equity API."})
            continue

        turnover = float(h.get("market_value") or 0)
        buy_val = float(h.get("invested") or 0)
        broker = h.get("broker") or "zerodha"
        asset = h.get("asset_type") or "stock"
        sell_charges = estimate_charges(
            side="sell",
            turnover=turnover,
            broker=broker if broker in ("zerodha", "groww") else "zerodha",
            asset_type=asset,
            intraday=False,
        )
        tax_pack = compute_tax(
            buy_value=buy_val,
            sell_value=turnover,
            holding_days=400,
            asset_type=asset,
            tax_bracket_rate_pct=tax_bracket_rate_pct,
            ltcg_exemption_remaining=ltcg_exempt,
            equity_oriented=True,
            intraday=False,
        )
        tax_amt = float(tax_pack.get("tax") or 0)
        if tax_pack.get("regime") == "equity_ltcg":
            ltcg_exempt = max(0, ltcg_exempt - float(tax_pack.get("exemption_applied") or 0))

        fees = float(sell_charges.get("total") or 0)
        transfer_now = turnover - fees
        net_after_tax = transfer_now - tax_amt

        total_market += turnover
        total_fees += fees
        total_tax += tax_amt
        total_net += net_after_tax

        lines.append({
            **h,
            "included_in_sell": True,
            "sell_charges": sell_charges,
            "tax_estimate": tax_pack,
            "transfer_before_tax": round(transfer_now, 2),
            "net_after_tax_estimate": round(net_after_tax, 2),
        })

    payout = payout_summary()
    return {
        "preview": True,
        "lines": lines,
        "totals": {
            "market_value": round(total_market, 2),
            "sell_fees": round(total_fees, 2),
            "tax_estimate": round(total_tax, 2),
            "net_transfer_estimate": round(total_market - total_fees, 2),
            "net_after_tax_estimate": round(total_net, 2),
            "positions_to_sell": sum(1 for ln in lines if ln.get("included_in_sell")),
        },
        "payout_account": payout,
        "disclaimer": (
            "Estimated proceeds before broker settlement (T+1). "
            "Tax is illustrative — pay advance tax / file ITR as applicable. "
            "MF redemptions may take 1–3 business days."
        ),
    }


def sell_all_execute(
    *,
    brokers: Optional[list[str]] = None,
    include_mf: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    preview = sell_all_preview(include_mf=include_mf)
    orders: list[dict[str, Any]] = []
    errors: list[str] = []

    for line in preview.get("lines") or []:
        if not line.get("included_in_sell"):
            continue
        if line.get("asset_type") != "stock":
            errors.append(f"{line.get('symbol')}: MF sell not automated — redeem in broker app.")
            continue
        payload = {
            "broker": line.get("broker"),
            "symbol": line.get("symbol"),
            "side": "sell",
            "quantity": int(line.get("quantity") or 0),
            "order_type": "market",
            "product": "cnc",
            "trade_id": line.get("id"),
        }
        if payload["quantity"] <= 0:
            continue
        if dry_run:
            orders.append({"dry_run": True, **payload})
            continue
        try:
            result = execute_order(payload, source="sell_all", skip_auto_checks=True)
            orders.append(result)
        except Exception as exc:
            errors.append(f"{line.get('symbol')}: {exc}")

    payout = load_payout_account()
    return {
        "executed": not dry_run,
        "orders": orders,
        "errors": errors,
        "preview_totals": preview.get("totals"),
        "payout_account": payout_summary(),
        "message": (
            f"Queued {len(orders)} sell orders."
            if not dry_run
            else f"Dry run — {len(orders)} orders would be placed."
        ),
    }
