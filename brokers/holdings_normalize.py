"""Normalize broker holdings into a unified schema."""
from __future__ import annotations

from typing import Any, Optional


def _f(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _app_symbol(trading_symbol: str, exchange: str = "NSE") -> str:
    sym = (trading_symbol or "").upper().strip()
    ex = (exchange or "NSE").upper()
    if sym.endswith(".NSE") or sym.endswith(".BSE"):
        return sym
    return f"{sym}.{ex}"


def normalize_kite_equity(rows: list[dict[str, Any]], broker: str = "zerodha") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        qty = _f(row.get("quantity")) or 0
        if qty <= 0:
            continue
        avg = _f(row.get("average_price")) or _f(row.get("avg_price"))
        ltp = _f(row.get("last_price")) or _f(row.get("close_price"))
        invested = (avg or 0) * qty
        mkt = (ltp or avg or 0) * qty
        pnl = _f(row.get("pnl"))
        if pnl is None and avg and ltp:
            pnl = (ltp - avg) * qty
        ex = row.get("exchange") or "NSE"
        sym = row.get("tradingsymbol") or row.get("symbol") or ""
        app_sym = _app_symbol(sym, ex)
        out.append({
            "id": f"{broker}:{app_sym}:stock",
            "broker": broker,
            "symbol": app_sym,
            "name": row.get("tradingsymbol") or sym,
            "asset_type": "stock",
            "quantity": qty,
            "avg_price": round(avg or 0, 4),
            "last_price": round(ltp or avg or 0, 4),
            "invested": round(invested, 2),
            "market_value": round(mkt, 2),
            "pnl": round(pnl or 0, 2),
            "pnl_pct": round((pnl / invested * 100), 2) if invested and pnl is not None else None,
            "sellable": True,
            "product": row.get("product") or "CNC",
            "isin": row.get("isin"),
        })
    return out


def normalize_kite_mf(rows: list[dict[str, Any]], broker: str = "zerodha") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        qty = _f(row.get("quantity")) or 0
        if qty <= 0:
            continue
        avg = _f(row.get("average_price"))
        ltp = _f(row.get("last_price")) or avg
        invested = (avg or 0) * qty
        mkt = (ltp or 0) * qty
        pnl = _f(row.get("pnl"))
        sym = row.get("tradingsymbol") or row.get("fund") or row.get("symbol") or "MF"
        out.append({
            "id": f"{broker}:{sym}:mf",
            "broker": broker,
            "symbol": sym,
            "name": row.get("fund") or sym,
            "asset_type": "mutual_fund",
            "quantity": qty,
            "avg_price": round(avg or 0, 4),
            "last_price": round(ltp or 0, 4),
            "invested": round(invested, 2),
            "market_value": round(mkt, 2),
            "pnl": round(pnl or (mkt - invested), 2),
            "pnl_pct": round((mkt - invested) / invested * 100, 2) if invested else None,
            "sellable": True,
            "folio": row.get("folio"),
            "isin": row.get("isin"),
        })
    return out


def normalize_groww(payload: dict[str, Any] | list, broker: str = "groww") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    rows: list[Any] = []
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        for key in ("holdings", "data", "equity_holdings", "stock_holdings", "mutual_fund_holdings", "mf_holdings"):
            chunk = payload.get(key)
            if isinstance(chunk, list):
                rows.extend(chunk)
            elif isinstance(chunk, dict):
                for sub in chunk.values():
                    if isinstance(sub, list):
                        rows.extend(sub)
    for row in rows:
        if not isinstance(row, dict):
            continue
        qty = _f(row.get("quantity")) or _f(row.get("qty")) or _f(row.get("total_quantity"))
        if not qty or qty <= 0:
            continue
        sym = row.get("trading_symbol") or row.get("tradingSymbol") or row.get("symbol") or ""
        ex = row.get("exchange") or "NSE"
        asset = "mutual_fund" if row.get("asset_type") == "mf" or row.get("segment") == "MF" or "mf" in str(row.get("type", "")).lower() else "stock"
        if asset == "stock" and sym:
            app_sym = _app_symbol(sym, ex)
        else:
            app_sym = sym or "MF"
        avg = _f(row.get("average_price")) or _f(row.get("avg_price")) or _f(row.get("avgPrice"))
        ltp = _f(row.get("last_price")) or _f(row.get("ltp")) or _f(row.get("current_price"))
        invested = _f(row.get("invested_amount")) or ((avg or 0) * qty)
        mkt = _f(row.get("current_value")) or ((ltp or avg or 0) * qty)
        pnl = _f(row.get("pnl")) or _f(row.get("unrealised_pnl")) or (mkt - invested)
        out.append({
            "id": f"{broker}:{app_sym}:{asset}",
            "broker": broker,
            "symbol": app_sym,
            "name": row.get("company_name") or row.get("scheme_name") or sym,
            "asset_type": asset,
            "quantity": qty,
            "avg_price": round(avg or 0, 4),
            "last_price": round(ltp or avg or 0, 4),
            "invested": round(invested, 2),
            "market_value": round(mkt, 2),
            "pnl": round(pnl or 0, 2),
            "pnl_pct": round(pnl / invested * 100, 2) if invested else None,
            "sellable": asset == "stock",
            "isin": row.get("isin"),
        })
    return out


def normalize_fyers(payload: dict[str, Any], broker: str = "fyers") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if payload.get("s") not in (None, "ok"):
        return out
    rows = payload.get("holdings") or payload.get("overall") or payload.get("d") or []
    if isinstance(rows, dict):
        rows = rows.get("holdings") or rows.get("netPositions") or []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        qty = _f(row.get("quantity")) or _f(row.get("qty")) or _f(row.get("remainingQuantity"))
        if not qty or qty <= 0:
            continue
        sym_raw = row.get("symbol") or row.get("sym") or ""
        # NSE:RELIANCE-EQ → RELIANCE.NSE
        base = sym_raw.split(":")[-1].replace("-EQ", "") if sym_raw else ""
        app_sym = _app_symbol(base, "NSE") if base else sym_raw
        avg = _f(row.get("costPrice")) or _f(row.get("avgPrice"))
        ltp = _f(row.get("ltp")) or _f(row.get("marketVal")) and _f(row.get("marketVal")) / qty if qty else None
        invested = _f(row.get("costPrice")) and qty and _f(row.get("costPrice")) * qty or _f(row.get("investedValue"))
        mkt = _f(row.get("marketVal")) or ((ltp or 0) * qty)
        pnl = _f(row.get("pl")) or _f(row.get("profitAndLoss")) or (mkt - (invested or 0))
        out.append({
            "id": f"{broker}:{app_sym}:stock",
            "broker": broker,
            "symbol": app_sym,
            "name": row.get("symbolDescription") or base,
            "asset_type": "stock",
            "quantity": int(qty),
            "avg_price": round(avg or 0, 4),
            "last_price": round(ltp or (mkt / qty if qty else 0), 4),
            "invested": round(invested or 0, 2),
            "market_value": round(mkt, 2),
            "pnl": round(pnl or 0, 2),
            "pnl_pct": round(pnl / invested * 100, 2) if invested else None,
            "sellable": True,
        })
    return out
