"""Social buzz / sentiment fallback chain (free sources first)."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Any, Callable, Optional

from analysis.external_factors import nlp_sentiment_score
from config import ALPHAVANTAGE_API_KEY

# Soft rate limit for optional Alpha Vantage social calls (avoid blocking analyze).
_av_last_call = 0.0
_AV_MIN_GAP = 12.0


def _bare_symbol(symbol: str) -> str:
    sym = symbol.upper().strip()
    for suffix in (".NSE", ".NS", ".BO", ".BSE"):
        if sym.endswith(suffix):
            return sym[: -len(suffix)]
    return sym.split(".")[0]


def _ok_partial(source: str, **fields: Any) -> dict[str, Any]:
    return {"status": "ok", "source": source, **fields}


def _from_forum_intel(symbol: str, *, fast: bool = False) -> dict[str, Any]:
    from forum_intel import gather_forum_intel

    try:
        bundle = gather_forum_intel(symbol, limit=8, max_queries=2 if fast else None)
    except Exception as exc:
        return {"status": "error", "source": "forum_intel", "error": str(exc)[:120]}

    tags = bundle.get("tag_counts") or {}
    bullish = int(tags.get("bullish_chatter") or 0)
    bearish = int(tags.get("bearish_chatter") or 0)
    threads = int(bundle.get("thread_count") or 0)
    if threads == 0:
        return {"status": "empty", "source": "forum_intel"}
    return _ok_partial(
        "forum_intel",
        forum_thread_count=threads,
        rumor_count=int(bundle.get("rumor_count") or 0),
        bullish_count=bullish,
        bearish_count=bearish,
        message_count=threads,
        headlines=[t.get("title") for t in (bundle.get("threads") or [])[:8] if t.get("title")],
        forum_counts=bundle.get("forum_counts"),
    )


def _from_yahoo_news(symbol: str) -> dict[str, Any]:
    from fetch_stock_data import fetch_yfinance_news

    try:
        items = fetch_yfinance_news(symbol, limit=10)
    except Exception as exc:
        return {"status": "error", "source": "yahoo_news", "error": str(exc)[:120]}
    if not items:
        return {"status": "empty", "source": "yahoo_news"}
    headlines = [i.get("title") for i in items if i.get("title")]
    return _ok_partial(
        "yahoo_news",
        news_headline_count=len(headlines),
        headlines=headlines,
        sample=headlines[:3],
    )


def _from_google_news(symbol: str) -> dict[str, Any]:
    from news_catalysts import _google_news_rss

    base = _bare_symbol(symbol)
    try:
        items = _google_news_rss(f'"{base}" NSE OR "{base}" stock India', limit=8)
    except Exception as exc:
        return {"status": "error", "source": "google_news", "error": str(exc)[:120]}
    if not items:
        return {"status": "empty", "source": "google_news"}
    headlines = [i.get("title") for i in items if i.get("title")]
    return _ok_partial(
        "google_news",
        news_headline_count=len(headlines),
        headlines=headlines,
    )


def _from_finnhub_news(symbol: str) -> dict[str, Any]:
    from analysis.finnhub_client import fetch_company_news

    try:
        bundle = fetch_company_news(symbol, days=14)
    except Exception as exc:
        return {"status": "error", "source": "finnhub_news", "error": str(exc)[:120]}
    if bundle.get("status") != "ok" or not bundle.get("headlines"):
        return {"status": "empty", "source": "finnhub_news", "note": bundle.get("note")}
    return _ok_partial(
        "finnhub_news",
        news_headline_count=len(bundle["headlines"]),
        headlines=bundle["headlines"],
    )


def _from_alpha_vantage(symbol: str) -> dict[str, Any]:
    global _av_last_call
    if not ALPHAVANTAGE_API_KEY or ALPHAVANTAGE_API_KEY == "replace_with_your_secret_key":
        return {"status": "unconfigured", "source": "alpha_vantage"}

    elapsed = time.monotonic() - _av_last_call
    if _av_last_call and elapsed < _AV_MIN_GAP:
        return {"status": "skipped", "source": "alpha_vantage", "note": "Rate-limit gap — skipped this request."}

    import requests

    base = _bare_symbol(symbol)
    tickers_to_try = [base, f"{base}.BSE", f"{base}.NS"]
    last_err: Optional[str] = None
    for ticker in tickers_to_try:
        try:
            _av_last_call = time.monotonic()
            r = requests.get(
                "https://www.alphavantage.co/query",
                params={
                    "function": "NEWS_SENTIMENT",
                    "tickers": ticker,
                    "limit": "30",
                    "apikey": ALPHAVANTAGE_API_KEY,
                },
                timeout=30,
            )
            payload = r.json()
            if payload.get("Note") or payload.get("Information"):
                last_err = str(payload.get("Note") or payload.get("Information"))[:120]
                break
            if payload.get("Error Message"):
                last_err = str(payload["Error Message"])[:120]
                continue
            feed = payload.get("feed") or []
            if not feed:
                continue
            scores: list[float] = []
            for article in feed[:20]:
                for ts in article.get("ticker_sentiment") or []:
                    if (ts.get("ticker") or "").upper().startswith(base):
                        val = ts.get("ticker_sentiment_score")
                        if val is not None:
                            scores.append(float(val))
                overall = article.get("overall_sentiment_score")
                if overall is not None and not scores:
                    scores.append(float(overall))
            if not scores:
                headlines = [a.get("title") for a in feed if a.get("title")]
                return _ok_partial(
                    "alpha_vantage",
                    news_headline_count=len(headlines),
                    headlines=headlines[:10],
                    note=f"No ticker-specific scores for {ticker}; headlines only.",
                )
            avg = sum(scores) / len(scores)
            label = "positive" if avg > 0.15 else ("negative" if avg < -0.15 else "neutral")
            return _ok_partial(
                "alpha_vantage",
                sentiment_score=round(avg * 100, 1),
                sentiment_label=label,
                news_headline_count=len(feed),
                headlines=[a.get("title") for a in feed[:8] if a.get("title")],
                av_ticker=ticker,
            )
        except Exception as exc:
            last_err = str(exc)[:120]
    return {"status": "empty" if not last_err else "error", "source": "alpha_vantage", "error": last_err}


def _from_stocktwits(symbol: str) -> dict[str, Any]:
    from analysis.stocktwits_client import fetch_social_snapshot

    snap = fetch_social_snapshot(symbol)
    if snap.get("status") not in {"ok"}:
        return snap
    return snap


def _label_from_score(score_0_100: Optional[float]) -> Optional[str]:
    if score_0_100 is None:
        return None
    if score_0_100 >= 60:
        return "Bullish"
    if score_0_100 <= 40:
        return "Bearish"
    return "Neutral"


def _nlp_to_score_100(nlp: dict[str, Any]) -> Optional[float]:
    raw = nlp.get("score")
    if raw is None:
        return None
    return round(50 + float(raw) * 50, 1)


def fetch_social_volume(
    symbol: str,
    *,
    existing_headlines: Optional[list[str]] = None,
    fast: bool = False,
) -> dict[str, Any]:
    """Aggregate social/news buzz from free sources; Stocktwits is last resort."""
    if existing_headlines:
        unique = []
        seen: set[str] = set()
        for h in existing_headlines:
            key = (h or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(h.strip())
        if unique:
            nlp = nlp_sentiment_score(unique[:20])
            score = _nlp_to_score_100(nlp)
            return {
                "status": "ok",
                "source": "analyze_news",
                "sources_used": ["analyze_news"],
                "symbol": _bare_symbol(symbol),
                "message_count": len(unique),
                "news_headline_count": len(unique),
                "sentiment_label": _label_from_score(score) or nlp.get("label"),
                "sentiment_score": score,
                "message_volume_label": "Low" if len(unique) < 5 else "Medium",
                "message_volume_score": min(100, len(unique) * 8),
                "nlp_sentiment": nlp,
                "headline_sample": unique[:5],
                "note": "Derived from analyze news headlines (skipped live social sweep).",
            }

    providers: list[tuple[str, Callable[[str], dict[str, Any]]]] = [
        ("forum_intel", lambda s: _from_forum_intel(s, fast=fast)),
        ("yahoo_news", _from_yahoo_news),
        ("google_news", _from_google_news),
        ("finnhub_news", _from_finnhub_news),
        ("alpha_vantage", _from_alpha_vantage),
        ("stocktwits", _from_stocktwits),
    ]
    if fast:
        providers = [p for p in providers if p[0] not in {"alpha_vantage", "google_news"}]

    parts: dict[str, dict[str, Any]] = {}
    sources_used: list[str] = []
    headlines: list[str] = []
    bullish = bearish = 0
    forum_threads = 0
    news_count = 0
    message_count = 0
    sentiment_score: Optional[float] = None
    sentiment_label: Optional[str] = None
    primary_source = "composite"

    with ThreadPoolExecutor(max_workers=min(4, len(providers))) as pool:
        futures = {pool.submit(fn, symbol): name for name, fn in providers}
        for fut in futures:
            name = futures[fut]
            try:
                result = fut.result()
            except Exception as exc:
                result = {"status": "error", "source": name, "error": str(exc)[:120]}
            parts[name] = result
            if result.get("status") != "ok":
                continue
            sources_used.append(name)
            headlines.extend(result.get("headlines") or [])
            bullish += int(result.get("bullish_count") or 0)
            bearish += int(result.get("bearish_count") or 0)
            forum_threads += int(result.get("forum_thread_count") or 0)
            news_count += int(result.get("news_headline_count") or 0)
            message_count += int(result.get("message_count") or result.get("forum_thread_count") or 0)
            if result.get("sentiment_score") is not None and sentiment_score is None:
                sentiment_score = float(result["sentiment_score"])
                sentiment_label = result.get("sentiment_label")
                primary_source = name

    # Dedupe headlines preserving order
    seen: set[str] = set()
    unique_headlines: list[str] = []
    for h in headlines:
        key = (h or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique_headlines.append(h.strip())

    nlp = nlp_sentiment_score(unique_headlines[:20])
    if sentiment_score is None:
        sentiment_score = _nlp_to_score_100(nlp)
        sentiment_label = nlp.get("label")
        if unique_headlines:
            primary_source = "nlp_headlines"

    if sentiment_label is None:
        sentiment_label = _label_from_score(sentiment_score)

    # Volume proxy: forum + news headline count
    buzz_count = max(message_count, forum_threads) + news_count
    if bullish > bearish + 1:
        chatter = "bullish_chatter"
    elif bearish > bullish + 1:
        chatter = "bearish_chatter"
    else:
        chatter = "mixed"

    if not sources_used:
        return {
            "status": "unavailable",
            "source": "none",
            "sources_tried": [p[0] for p in providers],
            "twitter_mentions": None,
            "stocktwits_messages": None,
            "note": "No social/news sources returned data. Check network or API keys.",
            "providers": parts,
        }

    volume_label = "High" if buzz_count >= 12 else ("Medium" if buzz_count >= 5 else "Low")
    return {
        "status": "ok",
        "source": primary_source,
        "sources_used": sources_used,
        "symbol": _bare_symbol(symbol),
        "message_count": buzz_count,
        "stocktwits_messages": parts.get("stocktwits", {}).get("message_count"),
        "forum_thread_count": forum_threads,
        "news_headline_count": news_count,
        "bullish_count": bullish,
        "bearish_count": bearish,
        "chatter_bias": chatter,
        "sentiment_label": sentiment_label,
        "sentiment_score": sentiment_score,
        "message_volume_label": volume_label,
        "message_volume_score": min(100, buzz_count * 8),
        "nlp_sentiment": nlp,
        "headline_sample": unique_headlines[:5],
        "providers": {k: {kk: vv for kk, vv in v.items() if kk != "headlines"} for k, v in parts.items()},
        "note": "Composite social/news buzz (forum RSS + Yahoo + Google + Finnhub + AV). Reddit OAuth skipped.",
    }
