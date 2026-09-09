"""Analyst consensus, target prices, and recommendation history."""
from __future__ import annotations

from typing import Any

from analysis.finnhub_client import fetch_price_target, fetch_recommendation_trends, finnhub_key
from fetch_stock_data import yahoo_symbol


def fetch_analyst_history(symbol: str) -> dict[str, Any]:
    sym = yahoo_symbol(symbol)
    info: dict[str, Any] = {}
    try:
        import yfinance as yf
        info = yf.Ticker(sym).info or {}
    except Exception as exc:
        if not finnhub_key():
            return {"status": "error", "error": str(exc)[:120]}

    rec = info.get("recommendationKey") or info.get("recommendation")
    target_mean = info.get("targetMeanPrice") or info.get("targetMean")
    target_high = info.get("targetHighPrice")
    target_low = info.get("targetLowPrice")
    forward_eps = info.get("forwardEps") or info.get("epsForward")
    num_analysts = info.get("numberOfAnalystOpinions")

    history: list[dict[str, Any]] = []
    source = "yahoo"
    try:
        import yfinance as yf
        t = yf.Ticker(sym)
        rec_trend = getattr(t, "recommendations", None)
        if rec_trend is not None and hasattr(rec_trend, "empty") and not rec_trend.empty:
            for idx, row in rec_trend.tail(8).iterrows():
                history.append({
                    "period": str(idx),
                    "strong_buy": int(row.get("strongBuy") or row.get("strong_buy") or 0),
                    "buy": int(row.get("buy") or 0),
                    "hold": int(row.get("hold") or 0),
                    "sell": int(row.get("sell") or 0),
                    "strong_sell": int(row.get("strongSell") or row.get("strong_sell") or 0),
                })
    except Exception:
        pass

    upgrade_bias = "neutral"
    if finnhub_key():
        fh = fetch_recommendation_trends(symbol)
        if fh.get("status") == "ok" and fh.get("history"):
            if not history:
                history = fh["history"]
                source = "finnhub"
            else:
                source = "yahoo+finnhub"
            upgrade_bias = fh.get("upgrade_bias") or upgrade_bias
        pt = fetch_price_target(symbol)
        if pt:
            target_mean = target_mean or pt.get("target_mean")
            target_high = target_high or pt.get("target_high")
            target_low = target_low or pt.get("target_low")

    if len(history) >= 2 and upgrade_bias == "neutral":
        recent = history[-1]
        prior = history[-2]
        recent_bull = recent.get("strong_buy", 0) + recent.get("buy", 0)
        prior_bull = prior.get("strong_buy", 0) + prior.get("buy", 0)
        if recent_bull > prior_bull:
            upgrade_bias = "upgrades"
        elif recent_bull < prior_bull:
            upgrade_bias = "downgrades"

    return {
        "status": "ok",
        "source": source,
        "recommendation": rec,
        "target_mean": target_mean,
        "target_high": target_high,
        "target_low": target_low,
        "forward_eps": forward_eps,
        "num_analysts": num_analysts,
        "history": history,
        "upgrade_bias": upgrade_bias,
    }
