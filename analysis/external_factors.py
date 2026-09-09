"""External macro, commodities, FX, calendar, NLP sentiment, social volume proxies."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Optional

from analysis._ttl_cache import get_ttl_cached
from analysis.data_feeds import fetch_economic_calendar, fetch_rbi_macro, fetch_social_volume
from analysis._helpers import num

_MACRO_TTL = 900.0  # 15 minutes — shared across analyze calls


def _yahoo_quote(ticker: str) -> Optional[dict[str, Any]]:
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        info = t.fast_info if hasattr(t, "fast_info") else {}
        price = getattr(info, "last_price", None) or getattr(info, "lastPrice", None)
        if price is None:
            hist = t.history(period="5d")
            if hist is not None and not hist.empty:
                price = float(hist["Close"].iloc[-1])
        chg = getattr(info, "previous_close", None)
        change_pct = round((price / chg - 1) * 100, 2) if price and chg else None
        return {"ticker": ticker, "price": round(float(price), 4) if price else None, "change_pct": change_pct}
    except Exception:
        return None


def _parallel_yahoo_quotes(tickers: list[str]) -> dict[str, Optional[dict[str, Any]]]:
    if not tickers:
        return {}
    if len(tickers) == 1:
        return {tickers[0]: _yahoo_quote(tickers[0])}
    out: dict[str, Optional[dict[str, Any]]] = {}
    with ThreadPoolExecutor(max_workers=min(6, len(tickers))) as pool:
        futures = {pool.submit(_yahoo_quote, t): t for t in tickers}
        for fut, ticker in futures.items():
            out[ticker] = fut.result()
    return out


def fetch_macro_commodities() -> dict[str, Any]:
    def _build() -> dict[str, Any]:
        quotes = _parallel_yahoo_quotes(["INR=X", "CL=F", "GC=F", "^TNX"])
        rbi = fetch_rbi_macro()
        india_gs = rbi.get("gsec_10y_pct")
        return {
            "fx": {"usd_inr": quotes.get("INR=X")},
            "commodities": {"crude_wti": quotes.get("CL=F"), "gold": quotes.get("GC=F")},
            "rates": {
                "us_10y_proxy": quotes.get("^TNX"),
                "india_gs_10y": india_gs,
                "rbi_repo_pct": rbi.get("rbi_repo_pct"),
                "note": "Repo/CPI from dynamic RBI + World Bank/data.gov.in when available.",
            },
            "cpi_india_yoy": rbi.get("cpi_yoy_pct"),
            "cpi_period": rbi.get("cpi_period"),
            "cpi_source": rbi.get("cpi_source"),
            "rbi": rbi,
        }

    return get_ttl_cached("external.macro_commodities", _MACRO_TTL, _build)


def fetch_inter_market() -> dict[str, Any]:
    def _build() -> dict[str, Any]:
        tickers = ["^GSPC", "^IXIC", "^DJI", "DX-Y.NYB", "^NSEI", "^NSEBANK"]
        quotes = _parallel_yahoo_quotes(tickers)
        indices = {
            "sp500": quotes.get("^GSPC"),
            "nasdaq": quotes.get("^IXIC"),
            "dow": quotes.get("^DJI"),
            "dxy": quotes.get("DX-Y.NYB"),
            "nifty": quotes.get("^NSEI"),
            "bank_nifty": quotes.get("^NSEBANK"),
        }
        return {"indices": indices, "note": "Inter-market read uses delayed Yahoo indices."}

    return get_ttl_cached("external.inter_market", _MACRO_TTL, _build)


_POS = re.compile(r"\b(beat|surge|growth|upgrade|bull|gain|record|profit|strong)\b", re.I)
_NEG = re.compile(r"\b(miss|fall|cut|downgrade|bear|loss|weak|probe|fraud|default|raid)\b", re.I)


def nlp_sentiment_score(headlines: list[str]) -> dict[str, Any]:
    if not headlines:
        return {"score": 0.0, "label": "neutral", "method": "keyword_heuristic"}
    pos = neg = 0
    for h in headlines:
        pos += len(_POS.findall(h))
        neg += len(_NEG.findall(h))
    raw = (pos - neg) / max(len(headlines), 1)
    score = max(-1.0, min(1.0, raw / 3))
    label = "positive" if score > 0.15 else ("negative" if score < -0.15 else "neutral")
    return {"score": round(score, 3), "label": label, "positive_hits": pos, "negative_hits": neg, "method": "keyword_heuristic_v2"}



def governance_flags(quote: dict[str, Any] | None) -> dict[str, Any]:
    quote = quote or {}
    company = quote.get("company") or {}
    flags: list[str] = []
    officers = company.get("officers") or company.get("company_officers") or []
    for o in officers[:5]:
        title = str(o.get("title") or "").lower()
        if "chief" in title and "interim" in title:
            flags.append("Interim leadership in officer roster.")
    rating = company.get("credit_rating")
    return {"flags": flags, "credit_rating": rating, "count": len(flags)}


def compute_external_factors(
    symbol: str,
    quote: dict[str, Any] | None = None,
    news: dict[str, Any] | None = None,
    *,
    fast_social: bool = False,
) -> dict[str, Any]:
    news = news or {}
    headlines = [h.get("title") or h.get("headline") or "" for h in (news.get("headlines") or [])[:15]]
    sentiment = nlp_sentiment_score(headlines)
    social_headlines = [h for h in headlines if h.strip()] or None

    with ThreadPoolExecutor(max_workers=4) as pool:
        f_macro = pool.submit(fetch_macro_commodities)
        f_inter = pool.submit(fetch_inter_market)
        f_cal = pool.submit(
            lambda: get_ttl_cached("external.economic_calendar", _MACRO_TTL, fetch_economic_calendar)
        )
        f_social = pool.submit(
            fetch_social_volume,
            symbol,
            existing_headlines=social_headlines,
            fast=fast_social or bool(social_headlines),
        )
        macro = f_macro.result()
        inter = f_inter.result()
        calendar = f_cal.result()
        social = f_social.result()

    return {
        "macro": macro,
        "inter_market": inter,
        "economic_calendar": calendar,
        "nlp_sentiment": sentiment,
        "social_volume": social,
        "governance": governance_flags(quote),
    }
