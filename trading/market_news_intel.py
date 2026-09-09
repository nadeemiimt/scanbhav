"""
Market news intelligence for Auto Pick — batch catalyst + sentiment scoring.

Uses Yahoo headlines + optional Google News RSS (news_catalysts) and social_volume
fast path. Curated desk is unchanged; this layer feeds agent ranking only.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from trading.config_store import load_trading_config

# Intraday MIS catalyst tags — boost when fresh headlines align with long bias.
_BULLISH_CATALYST_TAGS = frozenset({
    "earnings_corporate",
    "government_policy",
    "regulation_policy",
})
_VOLATILE_CATALYST_TAGS = frozenset({
    "geopolitics_war",
    "supply_constraints",
    "commodity_energy",
    "rates_macro",
    "weather_climate",
})


def news_intel_cfg() -> dict[str, Any]:
    ap = load_trading_config().get("autopilot") or {}
    return {
        "enabled": bool(ap.get("agent_news_intel_enabled", True)),
        "enrich_top_n": int(ap.get("agent_news_enrich_top_n") or 80),
        "fast_rss": bool(ap.get("agent_news_fast_rss", True)),
        "edge_weight": float(ap.get("agent_news_edge_weight") or 1.0),
        "min_headlines": int(ap.get("agent_news_min_headlines") or 1),
    }


def _bare_symbol(symbol: str) -> str:
    sym = str(symbol or "").upper().strip()
    for suffix in (".NSE", ".NS", ".BO", ".BSE"):
        if sym.endswith(suffix):
            return sym[: -len(suffix)]
    return sym.split(".")[0]


def score_news_bundle(
    bundle: dict[str, Any],
    *,
    sentiment_score: float | None = None,
) -> tuple[float, dict[str, Any]]:
    """Convert gather_news_catalysts output + optional sentiment into 0–100 score."""
    headlines = list(bundle.get("headlines") or [])
    count = len(headlines)
    high_impact = int(bundle.get("high_impact_count") or 0)
    tag_counts = dict(bundle.get("tag_counts") or {})

    score = 42.0
    reasons: list[str] = []

    if count == 0:
        return 40.0, {"news_score": 40.0, "news_reasons": ["no_headlines"], "headline_count": 0}

    score += min(12.0, count * 1.8)
    reasons.append(f"headlines_{count}")

    if high_impact >= 1:
        score += min(10.0, high_impact * 3.5)
        reasons.append(f"high_impact_{high_impact}")

    bullish_tags = sum(tag_counts.get(t, 0) for t in _BULLISH_CATALYST_TAGS)
    volatile_tags = sum(tag_counts.get(t, 0) for t in _VOLATILE_CATALYST_TAGS)

    if bullish_tags >= 1:
        score += min(14.0, bullish_tags * 4.0)
        reasons.append(f"bullish_catalyst_{bullish_tags}")
    if volatile_tags >= 1:
        score += min(8.0, volatile_tags * 2.5)
        reasons.append(f"volatile_flow_{volatile_tags}")

    earnings_n = int(tag_counts.get("earnings_corporate") or 0)
    if earnings_n >= 2:
        score += 4.0
        reasons.append("earnings_cluster")

    if sentiment_score is not None:
        try:
            sent = float(sentiment_score)
            if sent >= 62:
                score += min(12.0, (sent - 50) * 0.35)
                reasons.append(f"sentiment_bull_{sent:.0f}")
            elif sent <= 38:
                score -= min(10.0, (50 - sent) * 0.4)
                reasons.append(f"sentiment_bear_{sent:.0f}")
        except (TypeError, ValueError):
            pass

    news_score = round(max(0.0, min(100.0, score)), 1)
    meta = {
        "news_score": news_score,
        "news_reasons": reasons,
        "headline_count": count,
        "high_impact_count": high_impact,
        "tag_counts": tag_counts,
        "top_headlines": [h.get("title") for h in headlines[:5] if h.get("title")],
        "catalyst_tags": list(tag_counts.keys())[:6],
    }
    if sentiment_score is not None:
        meta["sentiment_score"] = sentiment_score
    return news_score, meta


def fetch_symbol_news_intel(
    symbol: str,
    *,
    fast: bool = True,
    skip_rss: bool | None = None,
) -> dict[str, Any]:
    """Fetch news catalysts + fast social sentiment for one symbol."""
    from news_catalysts import gather_news_catalysts

    sym = str(symbol or "").upper()
    rss_skip = skip_rss if skip_rss is not None else fast

    try:
        bundle = gather_news_catalysts(sym, limit=12, skip_rss=rss_skip)
    except Exception as exc:
        return {"symbol": sym, "news_score": 40.0, "error": str(exc)[:120]}

    headlines = [h.get("title") for h in (bundle.get("headlines") or []) if h.get("title")]
    sentiment_score: float | None = None
    sentiment_label: str | None = None

    try:
        from analysis.social_volume import fetch_social_volume

        social = fetch_social_volume(sym, existing_headlines=headlines or None, fast=True)
        if social.get("status") == "ok" and social.get("sentiment_score") is not None:
            sentiment_score = float(social["sentiment_score"])
            sentiment_label = social.get("sentiment_label")
    except Exception:
        pass

    news_score, meta = score_news_bundle(bundle, sentiment_score=sentiment_score)
    return {
        "symbol": sym,
        "news_score": news_score,
        "sentiment_score": sentiment_score,
        "sentiment_label": sentiment_label,
        "headlines": bundle.get("headlines") or [],
        **meta,
    }


def _merge_news_into_row(row: dict[str, Any], intel: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["news_score"] = intel.get("news_score")
    out["news_headline_count"] = intel.get("headline_count")
    out["news_catalyst_tags"] = intel.get("catalyst_tags") or []
    out["news_top_headlines"] = intel.get("top_headlines") or []
    out["news_reasons"] = intel.get("news_reasons") or []
    if intel.get("sentiment_score") is not None:
        out["sentiment_score"] = intel.get("sentiment_score")
        out["sentiment_label"] = intel.get("sentiment_label")
    return out


def batch_enrich_rows_with_news(
    rows: list[dict[str, Any]],
    *,
    top_n: int | None = None,
    max_workers: int = 6,
    fast: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Enrich top scan rows with news_score (agent ranking only)."""
    cfg = news_intel_cfg()
    if not cfg["enabled"] or not rows:
        return rows, {"skipped": True, "reason": "disabled_or_empty"}

    n = top_n or cfg["enrich_top_n"]
    ranked = sorted(rows, key=lambda r: float(r.get("composite_score") or 0), reverse=True)
    targets = ranked[:n]
    target_syms = {str(r.get("symbol") or "").upper() for r in targets if r.get("symbol")}

    by_sym = {str(r.get("symbol") or "").upper(): dict(r) for r in rows}
    enriched = 0
    errors = 0
    skip_rss = cfg["fast_rss"] and fast

    def _fetch(sym: str) -> tuple[str, dict[str, Any]]:
        return sym, fetch_symbol_news_intel(sym, fast=fast, skip_rss=skip_rss)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch, sym): sym for sym in target_syms if sym}
        for fut in as_completed(futures):
            sym = futures[fut]
            try:
                _, intel = fut.result()
            except Exception as exc:
                errors += 1
                intel = {"news_score": 40.0, "error": str(exc)[:80]}
            if sym in by_sym:
                by_sym[sym] = _merge_news_into_row(by_sym[sym], intel)
                enriched += 1

    out = list(by_sym.values())
    out.sort(key=lambda r: float(r.get("composite_score") or 0), reverse=True)
    return out, {
        "enriched": enriched,
        "errors": errors,
        "top_n": n,
        "fast_rss": skip_rss,
    }


def news_factor_from_row(row: dict[str, Any]) -> float:
    """Calibration factor 0–100 from precomputed row fields."""
    if row.get("news_score") is not None:
        try:
            return float(row["news_score"])
        except (TypeError, ValueError):
            pass
    sent = row.get("sentiment_score")
    if sent is not None:
        try:
            return float(sent)
        except (TypeError, ValueError):
            pass
    count = int(row.get("news_headline_count") or 0)
    if count >= 3:
        return 58.0
    if count >= 1:
        return 52.0
    return 50.0
