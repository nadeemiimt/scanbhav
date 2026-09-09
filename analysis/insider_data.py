"""Insider transactions and bulk/block deals."""
from __future__ import annotations

from typing import Any, Optional

from analysis.india_data import fetch_bulk_block_deals
from fetch_stock_data import yahoo_symbol


def fetch_yahoo_insider(symbol: str) -> dict[str, Any]:
    sym = yahoo_symbol(symbol)
    try:
        import yfinance as yf
        t = yf.Ticker(sym)
        tx = getattr(t, "insider_transactions", None)
        if tx is None:
            tx = t.get_insider_transactions()
        purchases = getattr(t, "insider_purchases", None)
        if purchases is None:
            try:
                purchases = t.get_insider_purchases()
            except Exception:
                purchases = None
        rows: list[dict[str, Any]] = []
        if tx is not None and hasattr(tx, "empty") and not tx.empty:
            for _, row in tx.head(12).iterrows():
                rows.append({
                    "date": str(row.get("Start Date") or row.get("startDate") or ""),
                    "insider": str(row.get("Insider") or row.get("insider") or ""),
                    "transaction": str(row.get("Transaction") or row.get("transaction") or ""),
                    "shares": _num(row.get("Shares") or row.get("shares")),
                    "value": _num(row.get("Value") or row.get("value")),
                })
        net_buy = None
        if purchases is not None and hasattr(purchases, "empty") and not purchases.empty:
            try:
                net_buy = _num(purchases.iloc[0].get("Insider Purchases Last 6m"))
            except Exception:
                pass
        return {"status": "ok", "source": "yahoo", "transactions": rows, "net_purchases_6m": net_buy}
    except Exception as exc:
        return {"status": "error", "source": "yahoo", "transactions": [], "error": str(exc)[:120]}


def _num(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def compute_insider_context(symbol: str) -> dict[str, Any]:
    insider = fetch_yahoo_insider(symbol)
    bulk = fetch_bulk_block_deals(symbol)
    buys = sum(1 for t in insider.get("transactions") or [] if "purchase" in str(t.get("transaction", "")).lower())
    sells = sum(1 for t in insider.get("transactions") or [] if "sale" in str(t.get("transaction", "")).lower())
    bias = "accumulation" if buys > sells else ("distribution" if sells > buys else "neutral")
    return {
        "insider_transactions": insider,
        "bulk_block_deals": bulk,
        "insider_bias": bias,
        "headline": f"Insider {bias}: {buys} buys vs {sells} sells recent · {bulk.get('count', 0)} bulk/block today",
    }
