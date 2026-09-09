"""Industry peer comparison via Yahoo Finance's equity screener.

Peers are discovered by matching the target stock's Yahoo Finance ``industry``
and listing region (derived from the ticker's exchange suffix), then ranked by
market capitalization. This module deliberately avoids inventing any figures:
if Yahoo does not return an industry or peers, an empty list is returned.
"""
from __future__ import annotations

from typing import Any


def region_for_symbol(symbol: str) -> str:
    """Best-effort region code derived from common exchange suffixes."""
    upper = symbol.upper()
    if upper.endswith(".NS") or upper.endswith(".BO"):
        return "in"
    if upper.endswith(".L"):
        return "gb"
    if upper.endswith(".HK"):
        return "hk"
    if upper.endswith(".T"):
        return "jp"
    if upper.endswith(".SS") or upper.endswith(".SZ"):
        return "cn"
    if upper.endswith(".TO"):
        return "ca"
    if upper.endswith(".AX"):
        return "au"
    return "us"


def fetch_peers(yahoo_symbol: str, industry: str | None, limit: int = 6) -> list[dict[str, Any]]:
    """Return up to `limit` same-industry, same-region peers ranked by market cap.

    Excludes the queried symbol itself and both NSE/BSE duplicates of the same
    company where applicable. Returns an empty list if the industry is unknown
    or the screener call fails for any reason (network, unsupported field, etc).
    """
    if not industry:
        return []
    try:
        import yfinance as yf

        region = region_for_symbol(yahoo_symbol)
        query = yf.EquityQuery("and", [
            yf.EquityQuery("eq", ["industry", industry]),
            yf.EquityQuery("eq", ["region", region]),
        ])
        result = yf.screen(query, sortField="intradaymarketcap", sortAsc=False, size=limit + 6)
    except Exception:
        return []

    target = yahoo_symbol.upper()
    target_root = target.split(".")[0]
    seen_roots: set[str] = set()
    peers: list[dict[str, Any]] = []
    for quote in result.get("quotes", []):
        symbol = (quote.get("symbol") or "").upper()
        if not symbol or symbol == target:
            continue
        root = symbol.split(".")[0]
        if root == target_root or root in seen_roots:
            continue
        seen_roots.add(root)
        peers.append({
            "symbol": symbol,
            "name": quote.get("shortName") or quote.get("longName") or symbol,
            "price": quote.get("regularMarketPrice"),
            "change_pct": quote.get("regularMarketChangePercent"),
            "market_cap": quote.get("marketCap"),
            "trailing_pe": quote.get("trailingPE"),
            "forward_pe": quote.get("forwardPE"),
            "price_to_book": quote.get("priceToBook"),
            "dividend_yield_pct": quote.get("dividendYield"),
        })
        if len(peers) >= limit:
            break
    return peers
