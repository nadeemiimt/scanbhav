"""Normalize broker intraday/CNC positions to app schema."""
from __future__ import annotations

from typing import Any


def app_symbol(exchange: str, tradingsymbol: str) -> str:
    ex = (exchange or "NSE").upper()
    base = (tradingsymbol or "").upper()
    suffix = ".BSE" if ex == "BSE" else ".NSE"
    return f"{base}{suffix}"


def normalize_kite_positions(raw: dict[str, Any], broker_id: str = "zerodha") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bucket in ("net", "day"):
        for row in raw.get(bucket) or []:
            if not isinstance(row, dict):
                continue
            qty = int(row.get("quantity") or 0)
            if qty == 0:
                continue
            product = str(row.get("product") or "").lower()
            sym = app_symbol(str(row.get("exchange") or "NSE"), str(row.get("tradingsymbol") or ""))
            rows.append({
                "symbol": sym,
                "quantity": abs(qty),
                "side": "long" if qty > 0 else "short",
                "avg_price": float(row.get("average_price") or row.get("buy_price") or 0),
                "product": "mis" if product in {"mis", "misl"} else product or "mis",
                "broker": broker_id,
                "pnl": float(row.get("pnl") or 0),
                "last_price": float(row.get("last_price") or 0),
                "source": "broker",
            })
    return rows


def normalize_groww_positions(raw: Any, broker_id: str = "groww") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    data = raw
    if isinstance(raw, dict):
        data = raw.get("data") or raw.get("positions") or raw
    if not isinstance(data, list):
        data = [data] if isinstance(data, dict) else []
    for row in data:
        if not isinstance(row, dict):
            continue
        qty = int(row.get("quantity") or row.get("net_quantity") or 0)
        if qty == 0:
            continue
        ex = str(row.get("exchange") or "NSE")
        ts = str(row.get("trading_symbol") or row.get("tradingSymbol") or row.get("symbol") or "")
        sym = app_symbol(ex, ts)
        prod = str(row.get("product") or "MIS").lower()
        rows.append({
            "symbol": sym,
            "quantity": abs(qty),
            "side": "long" if qty > 0 else "short",
            "avg_price": float(row.get("average_price") or row.get("avgPrice") or 0),
            "product": "mis" if prod in {"mis", "intraday"} else prod,
            "broker": broker_id,
            "source": "broker",
        })
    return rows


def normalize_fyers_positions(raw: Any, broker_id: str = "fyers") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    data = raw
    if isinstance(raw, dict):
        if raw.get("s") not in (None, "ok"):
            return []
        data = raw.get("netPositions") or raw.get("overall") or raw.get("d") or raw
    if isinstance(data, dict):
        data = data.get("netPositions") or data.get("overall") or list(data.values())
    if not isinstance(data, list):
        return []
    for row in data:
        if not isinstance(row, dict):
            continue
        qty = int(row.get("netQty") or row.get("qty") or 0)
        if qty == 0:
            continue
        fsym = str(row.get("symbol") or "")
        # NSE:RELIANCE-EQ -> RELIANCE.NSE
        parts = fsym.replace("-EQ", "").split(":")
        sym = app_symbol(parts[0] if len(parts) > 1 else "NSE", parts[-1])
        side = str(row.get("side") or row.get("productType") or "").upper()
        prod = "mis" if "INTRADAY" in side or "MIS" in side else "cnc"
        rows.append({
            "symbol": sym,
            "quantity": abs(qty),
            "side": "long" if qty > 0 else "short",
            "avg_price": float(row.get("avgPrice") or row.get("costPrice") or 0),
            "product": prod.lower(),
            "broker": broker_id,
            "source": "broker",
        })
    return rows
