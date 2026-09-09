"""GenAI deep research with Chroma insight memory.

Flow:
1. Build a factual snapshot from technicals / quote / investors.
2. Retrieve prior stock insights from Chroma (append-only memory).
3. Optionally retrieve book RAG passages if the books collection has data.
4. Call the configured LLM (Ollama / Cursor Composer|Grok / Claude / OpenAI…).
5. Append the new insight into Chroma for the next run.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from config import COLLECTION_NAME, TOP_K, setting
from behavior_psychology import analyze_trader_behavior
from forecast_tracker import (
    build_forecast_table,
    format_lessons_block,
    normalize_forecast,
    prepare_forecast_filing,
    retrieve_forecast_lessons,
    review_pending_forecasts,
)
from forum_intel import gather_forum_intel
from market_signals import build_critical_signals
from llm_providers import chat_completion, list_providers, parse_llm_json
from news_catalysts import gather_news_catalysts
from rag import collection as books_collection, embed
from utils.errors import swallow
from utils.logging_config import get_logger
from utils.numbers import fmt_signed_pct

logger = get_logger(__name__)

INSIGHTS_COLLECTION = setting("INSIGHTS_COLLECTION", "stock_insights")


def insights_collection():
    import chromadb
    from config import CHROMA_PATH

    CHROMA_PATH.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    return client.get_or_create_collection(
        name=INSIGHTS_COLLECTION,
        metadata={"hnsw:space": "cosine", "purpose": "append-only stock GenAI insights"},
    )


def _safe_embed(texts: list[str]) -> list[list[float]]:
    try:
        return embed(texts)
    except Exception as exc:
        logger.warning("Embedding unavailable — using deterministic fallback vectors", exc_info=exc)
        out = []
        for text in texts:
            vec = [0.0] * 64
            for i, ch in enumerate(text[:2048]):
                vec[i % 64] += (ord(ch) % 31) / 31.0
            out.append(vec)
        return out


def retrieve_prior_insights(symbol: str, query: str, top_k: int = 6) -> list[dict[str, Any]]:
    db = insights_collection()
    if db.count() == 0:
        return []
    try:
        result = db.query(
            query_embeddings=_safe_embed([query]),
            n_results=min(top_k, db.count()),
            where={"symbol": symbol.upper()},
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:
        logger.debug("Insight query with symbol filter failed for %s, retrying broader query", symbol, exc_info=exc)
        result = db.query(
            query_embeddings=_safe_embed([f"{symbol} {query}"]),
            n_results=min(top_k, db.count()),
            include=["documents", "metadatas", "distances"],
        )
    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]
    out = []
    for doc, meta, dist in zip(docs, metas, dists):
        if meta and meta.get("symbol") and meta.get("symbol") != symbol.upper():
            continue
        out.append({
            "text": doc,
            "metadata": meta or {},
            "distance": round(float(dist), 4) if dist is not None else None,
        })
    return out


def retrieve_book_context(query: str, top_k: int = 4) -> list[dict[str, Any]]:
    try:
        db = books_collection()
        if db.count() == 0:
            return []
        result = db.query(
            query_embeddings=_safe_embed([query]),
            n_results=min(top_k, db.count()),
            include=["documents", "metadatas", "distances"],
        )
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        dists = (result.get("distances") or [[]])[0]
        return [
            {
                "text": doc,
                "source": (meta or {}).get("source"),
                "page": (meta or {}).get("page"),
                "distance": round(float(dist), 4) if dist is not None else None,
            }
            for doc, meta, dist in zip(docs, metas, dists)
        ]
    except Exception as exc:
        swallow("Book RAG retrieval failed", exc)
        return []


def append_insight(
    *,
    symbol: str,
    insight: dict[str, Any],
    provider: str,
    model: str,
    as_of: Optional[str] = None,
    kind: str = "genai_deep_research",
    extra_metadata: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    db = insights_collection()
    insight_id = str(uuid.uuid4())
    created = datetime.now(timezone.utc).isoformat()
    narrative = insight.get("executive_summary") or insight.get("narrative") or json.dumps(insight)[:1500]
    document = (
        f"SYMBOL: {symbol.upper()}\n"
        f"AS_OF: {as_of or 'n/a'}\n"
        f"PROVIDER: {provider} / {model}\n"
        f"CREATED: {created}\n"
        f"STANCE: {insight.get('stance')}\n"
        f"SUMMARY: {narrative}\n"
        f"FULL_JSON:\n{json.dumps(insight, ensure_ascii=False)[:6000]}"
    )
    metadata = {
        "symbol": symbol.upper(),
        "provider": provider,
        "model": model,
        "as_of": as_of or "",
        "created_at": created,
        "stance": str(insight.get("stance") or ""),
        "kind": kind,
    }
    if extra_metadata:
        metadata.update({k: str(v) for k, v in extra_metadata.items() if v is not None})
    db.add(
        ids=[insight_id],
        documents=[document],
        metadatas=[metadata],
        embeddings=_safe_embed([document]),
    )
    return {"id": insight_id, "created_at": created, "symbol": symbol.upper()}


def list_insight_history(symbol: str, limit: int = 10) -> list[dict[str, Any]]:
    db = insights_collection()
    if db.count() == 0:
        return []
    try:
        raw = db.get(where={"symbol": symbol.upper()}, include=["documents", "metadatas"])
    except Exception as exc:
        swallow(f"Insight history list failed for {symbol}", exc)
        return []
    rows = []
    for doc, meta in zip(raw.get("documents") or [], raw.get("metadatas") or []):
        rows.append({"text": doc, "metadata": meta or {}})
    rows.sort(key=lambda r: (r["metadata"] or {}).get("created_at") or "", reverse=True)
    return rows[:limit]


def parse_stored_document(text: str) -> dict[str, Any]:
    """Rebuild a UI-friendly insight object from an append-only Chroma document."""
    text = text or ""
    insight: dict[str, Any] = {}
    # Prefer embedded FULL_JSON block when present.
    marker = "FULL_JSON:\n"
    if marker in text:
        blob = text.split(marker, 1)[1].strip()
        try:
            parsed = json.loads(blob)
            if isinstance(parsed, dict):
                insight = parsed
        except json.JSONDecodeError:
            # Truncated JSON — fall through to SUMMARY extraction.
            pass
    if not insight.get("executive_summary"):
        for line in text.splitlines():
            if line.startswith("SUMMARY:"):
                insight["executive_summary"] = line[len("SUMMARY:"):].strip()
                break
    if not insight.get("stance"):
        for line in text.splitlines():
            if line.startswith("STANCE:"):
                insight["stance"] = line[len("STANCE:"):].strip()
                break
    insight.setdefault("executive_summary", text[:800] if text else "No summary stored.")
    insight.setdefault("stance", "neutral")
    insight.setdefault("not_advice_disclaimer", "Educational research only — not investment advice.")
    return insight


def latest_research_payload(symbol: str) -> dict[str, Any]:
    history_rows = list_insight_history(symbol, limit=8)
    if not history_rows:
        return {
            "symbol": symbol.upper(),
            "has_insight": False,
            "insight": None,
            "history": [],
            "message": "No GenAI insights stored yet for this symbol. Run deep analysis once.",
        }
    latest = history_rows[0]
    meta = latest.get("metadata") or {}
    insight = parse_stored_document(latest.get("text") or "")
    return {
        "symbol": symbol.upper(),
        "has_insight": True,
        "from_cache": True,
        "provider": meta.get("provider"),
        "model": meta.get("model"),
        "first_analysis": False,
        "prior_insights_used": max(len(history_rows) - 1, 0),
        "insight": insight,
        "stored": {
            "created_at": meta.get("created_at"),
            "symbol": meta.get("symbol"),
        },
        "history": [
            {
                "created_at": (h.get("metadata") or {}).get("created_at"),
                "provider": (h.get("metadata") or {}).get("provider"),
                "model": (h.get("metadata") or {}).get("model"),
                "stance": (h.get("metadata") or {}).get("stance"),
                "preview": _history_preview(h.get("text") or ""),
            }
            for h in history_rows
        ],
        "disclaimer": "Showing latest memo from Chroma. Run GenAI again to refresh with current market snapshot.",
    }


def _history_preview(text: str) -> str:
    for line in (text or "").splitlines():
        if line.startswith("SUMMARY:"):
            return line[len("SUMMARY:"):].strip()[:280]
    return (text or "")[:280]


def build_research_snapshot(
    *,
    symbol: str,
    technicals: dict[str, Any],
    ratings: dict[str, Any],
    quote: dict[str, Any] | None = None,
    investors: list[dict[str, Any]] | None = None,
    news: dict[str, Any] | None = None,
    behavior_psych: dict[str, Any] | None = None,
    forum_intel: dict[str, Any] | None = None,
    critical_signals: dict[str, Any] | None = None,
    extended: dict[str, Any] | None = None,
) -> dict[str, Any]:
    company = (quote or {}).get("company") or {}
    fundamentals = (quote or {}).get("fundamentals") or {}
    summary = (quote or {}).get("summary") or {}
    news_payload = news or {}
    headlines = (news_payload.get("headlines") or [])[:12]
    return {
        "symbol": symbol.upper(),
        "company_name": company.get("name"),
        "sector": company.get("sector"),
        "industry": company.get("industry"),
        "price": technicals.get("price") or summary.get("close") or company.get("live_price"),
        "as_of": technicals.get("as_of") or summary.get("date"),
        "technicals": {
            "momentum": technicals.get("momentum"),
            "trend": technicals.get("trend"),
            "moving_averages": {
                k: (technicals.get("moving_averages") or {}).get(k)
                for k in (
                    "sma_50", "sma_200", "ema_21", "golden_cross", "death_cross",
                    "price_vs_sma_200_pct", "ema_stack_bullish",
                )
            },
            "volatility": technicals.get("volatility"),
            "volume": technicals.get("volume"),
            "levels": technicals.get("levels"),
            "returns_pct": technicals.get("returns_pct"),
        },
        "ratings": {
            "composite_score": ratings.get("composite_score"),
            "composite_grade": ratings.get("composite_grade"),
            "composite_stance": ratings.get("composite_stance"),
            "best_horizon": ratings.get("best_horizon"),
            "horizons": {
                hid: {
                    "score": h.get("score"),
                    "grade": h.get("grade"),
                    "stance": h.get("stance"),
                    "horizon_return_pct": h.get("horizon_return_pct"),
                }
                for hid, h in ((ratings.get("horizons") or {}).items())
            },
        },
        "fundamentals": {
            "trailing_pe": company.get("trailing_pe"),
            "roe_pct": fundamentals.get("roe_pct"),
            "debt_to_equity": fundamentals.get("debt_to_equity"),
            "net_margin_pct": fundamentals.get("net_margin_pct"),
            "revenue_growth_yoy_pct": fundamentals.get("revenue_growth_yoy_pct"),
        },
        "investor_lenses": [
            {"name": i.get("name"), "stance": i.get("stance"), "label": i.get("label"), "score": i.get("score")}
            for i in (investors or [])
        ],
        "news_catalysts": {
            "headline_count": news_payload.get("headline_count", len(headlines)),
            "high_impact_count": news_payload.get("high_impact_count", 0),
            "tag_counts": news_payload.get("tag_counts") or {},
            "note": news_payload.get("note"),
            "headlines": [
                {
                    "title": h.get("title"),
                    "summary": (h.get("summary") or "")[:280] or None,
                    "published_at": h.get("published_at"),
                    "publisher": h.get("publisher"),
                    "catalyst_tag": h.get("catalyst_tag"),
                    "catalyst_label": h.get("catalyst_label"),
                    "source": h.get("source"),
                }
                for h in headlines
            ],
        },
        "behavior_psych": behavior_psych or {},
        "critical_signals": critical_signals or {},
        "forum_intel": {
            "thread_count": (forum_intel or {}).get("thread_count", 0),
            "rumor_count": (forum_intel or {}).get("rumor_count", 0),
            "note": (forum_intel or {}).get("note"),
            "disclaimer": (forum_intel or {}).get("disclaimer"),
            "threads": [
                {
                    "title": t.get("title"),
                    "summary": (t.get("summary") or "")[:280] or None,
                    "forum_label": t.get("forum_label"),
                    "thread_label": t.get("thread_label"),
                    "published_at": t.get("published_at"),
                    "url": t.get("url"),
                }
                for t in ((forum_intel or {}).get("threads") or [])[:10]
            ],
        },
        "extended_factors": {
            "summary": _extended_summary(extended),
            "coverage_pct": ((extended or {}).get("coverage") or {}).get("pct"),
            "patterns": ((extended or {}).get("patterns") or {}).get("active_patterns"),
            "regime": (((extended or {}).get("regime") or {}).get("regime") or {}).get("regime"),
            "quality_score": (((extended or {}).get("fundamentals") or {}).get("quality_scores") or {}).get("composite_quality"),
            "options_pcr": (extended or {}).get("options", {}).get("pcr_oi"),
            "insider_bias": (extended or {}).get("insider", {}).get("insider_bias"),
            "analyst_upgrade_bias": (extended or {}).get("analyst", {}).get("upgrade_bias"),
        } if extended else {},
    }


def _extended_summary(extended: dict[str, Any] | None) -> str:
    if not extended:
        return ""
    try:
        from analysis.bundle import extended_summary_for_agents
        return extended_summary_for_agents(extended)
    except Exception:
        return ""


RESEARCH_SCHEMA = {
    "stance": "bullish | constructive | neutral | cautious | bearish",
    "confidence": "0-100 integer",
    "executive_summary": "3-6 sentence research memo including material news/macro catalysts when present",
    "key_bull_points": ["..."],
    "key_bear_points": ["..."],
    "technical_read": "what the indicators imply now",
    "fundamental_read": "what fundamentals imply (or data gaps)",
    "behavior_psych_read": "how crowd/trader psychology may be showing up on this tape (FOMO, fear, anchoring, etc.); educational only",
    "psychological_barriers_read": "nearest round-number / 52w / moving-average barriers where crowd hesitation may appear",
    "price_distortion_read": "whether tape shows signs of artificial inflation (pump-like) or deflation (washout) from supplied critical_signals — include 5y history and recent pump/dump emphasis; educational only",
    "historical_distortion_read": "5-year pump/dump/pump-and-dump episode summary from price_history in critical_signals",
    "government_policy_read": "government/regulatory policy exposure from supplied headlines and sector context (budget, RBI/SEBI, subsidies, tariffs, etc.)",
    "corporate_foundation_read": "CEO/officer roster and group-structure governance flags from corporate_foundation — related-party/subsidiary headlines; not fraud accusations",
    "forum_intel_read": "summary of public forum discussion threads; flag unverified rumors; never present as confirmed insider facts",
    "news_catalyst_read": "how supplied headlines (war, supply constraints, rates, regulation, commodities, etc.) may affect this stock; say if none are material",
    "macro_risks": ["short list of macro/geopolitical/supply risks relevant to this name from the news"],
    "what_changed_vs_prior": "how this updates earlier cached insights; or 'first analysis'",
    "questions_to_monitor": ["..."],
    "forecast_7d": {
        "direction": "up | down | sideways",
        "target_price": "numeric baseline + 7d target",
        "price_band_low": "numeric low of educational band",
        "price_band_high": "numeric high of educational band",
        "expected_return_pct": "numeric expected % move from baseline over 7 days",
        "confidence": "0-100 integer",
        "key_drivers": ["2-4 bullets from supplied analysis only"],
        "risks_to_forecast": ["what could break this scenario"],
        "rationale": "2-4 sentences grounded in technicals, news, behaviour, forum intel",
        "expires_at": "YYYY-MM-DD (~7 calendar days from as_of)",
    },
    "forecast_accuracy_review": "if PRIOR FORECAST ACCURACY block supplied: explain hit/miss vs last 7d forecast and why",
    "not_advice_disclaimer": "Educational research only — not investment advice.",
}


def run_deep_research(
    *,
    symbol: str,
    technicals: dict[str, Any],
    ratings: dict[str, Any],
    quote: dict[str, Any] | None = None,
    investors: list[dict[str, Any]] | None = None,
    news: dict[str, Any] | None = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    extended: dict[str, Any] | None = None,
) -> dict[str, Any]:
    company = (quote or {}).get("company") or {}
    news_bundle = news or gather_news_catalysts(
        symbol,
        company_name=company.get("name"),
        sector=company.get("sector"),
        industry=company.get("industry"),
        existing_news=(quote or {}).get("news") or [],
    )
    psych_read = analyze_trader_behavior(technicals, ratings)
    forum_bundle = gather_forum_intel(symbol.upper(), company_name=company.get("name"))
    critical_signals = build_critical_signals(
        technicals=technicals,
        ratings=ratings,
        news=news_bundle,
        quote=quote,
    )
    snapshot = build_research_snapshot(
        symbol=symbol,
        technicals=technicals,
        ratings=ratings,
        quote=quote,
        investors=investors,
        news=news_bundle,
        behavior_psych=psych_read,
        forum_intel=forum_bundle,
        critical_signals=critical_signals,
        extended=extended,
    )
    current_price = float(snapshot.get("price") or 0)
    as_of = snapshot.get("as_of") or ""
    forecast_review = review_pending_forecasts(
        symbol=symbol.upper(),
        current_price=current_price,
        as_of=as_of,
        news_bundle=news_bundle,
        technicals=technicals,
        ratings=ratings,
    )
    forecast_lessons = retrieve_forecast_lessons(
        f"{symbol} forecast accuracy direction target news catalyst",
        symbol=symbol.upper(),
        top_k=5,
        include_global=True,
    )
    global_lessons = retrieve_forecast_lessons(
        "forecast miss accuracy lesson macro news wrong prediction",
        top_k=3,
        include_global=True,
    )
    seen_lessons: set[str] = set()
    merged_lessons = []
    for item in forecast_lessons + global_lessons:
        key = (item.get("lesson") or item.get("text") or "")[:80]
        if key in seen_lessons:
            continue
        seen_lessons.add(key)
        merged_lessons.append(item)
        if len(merged_lessons) >= 6:
            break
    query = (
        f"Deep equity research update for {symbol}: trend, momentum, valuation risk, "
        f"news catalysts (war, supply, rates, regulation), "
        f"and what changed since prior memo. Price {snapshot.get('price')} as of {snapshot.get('as_of')}."
    )
    prior = retrieve_prior_insights(symbol, query, top_k=6)
    books = retrieve_book_context(query, top_k=min(TOP_K, 4))

    prior_block = "\n\n".join(
        f"[Prior insight {i} · {(p.get('metadata') or {}).get('created_at')} · "
        f"{(p.get('metadata') or {}).get('provider')}/{(p.get('metadata') or {}).get('model')}]\n{p['text'][:1800]}"
        for i, p in enumerate(prior, start=1)
    ) or "(No prior GenAI insights in Chroma yet — this is the first analysis for this symbol.)"

    books_block = "\n\n".join(
        f"[Book {i}: {b.get('source')} p.{b.get('page')}]\n{(b.get('text') or '')[:900]}"
        for i, b in enumerate(books, start=1)
    ) or "(No book passages retrieved — books collection empty or unavailable.)"

    news_lines = []
    for i, h in enumerate((news_bundle.get("headlines") or [])[:12], start=1):
        news_lines.append(
            f"[{i}] ({h.get('catalyst_label') or 'General'} · {h.get('published_at') or 'n/a'} · "
            f"{h.get('publisher') or h.get('source') or 'news'})\n"
            f"TITLE: {h.get('title')}\n"
            f"SUMMARY: {(h.get('summary') or '')[:320]}"
        )
    news_block = "\n\n".join(news_lines) or "(No recent headlines retrieved.)"

    forum_lines = []
    for i, t in enumerate((forum_bundle.get("threads") or [])[:10], start=1):
        forum_lines.append(
            f"[{i}] ({t.get('thread_label') or 'Discussion'} · {t.get('forum_label') or 'forum'} · "
            f"{t.get('published_at') or 'n/a'})\n"
            f"TITLE: {t.get('title')}\n"
            f"SUMMARY: {(t.get('summary') or '')[:280]}"
        )
    forum_block = "\n\n".join(forum_lines) or "(No public forum threads retrieved.)"
    psych_block = json.dumps(psych_read, indent=2)[:2400]

    forecast_accuracy_block = "(No prior 7-day forecast to score yet.)"
    if forecast_review.get("reviews"):
        lines = []
        for i, rev in enumerate(forecast_review["reviews"][:3], start=1):
            sc = rev.get("score") or {}
            lines.append(
                f"[Review {i} · day {rev.get('days_old')} · {sc.get('maturity')}]\n"
                f"Predicted: {sc.get('predicted_direction')} → target {sc.get('target_price')} "
                f"from baseline {sc.get('baseline_price')}\n"
                f"Actual: {sc.get('actual_price')} ({fmt_signed_pct(sc.get('actual_return_pct'))}%) · "
                f"label={sc.get('label')} · accuracy={sc.get('accuracy_pct')}%\n"
                f"Mismatch: {((sc.get('mismatch') or {}).get('summary') or 'n/a')}"
            )
        forecast_accuracy_block = "\n\n".join(lines)
    lessons_block = format_lessons_block(merged_lessons)

    system = (
        "You are ScanBhav's GenAI research desk. Produce an educational, research-oriented "
        "equity memo grounded ONLY in the supplied JSON snapshot, news headlines, forum threads, "
        "behavioral read, prior Chroma insights, forecast accuracy lessons, and book passages. "
        "Pay special attention to news that may move the stock: war/geopolitics, supply constraints, "
        "commodity shocks, rates/inflation, regulation, government policy, weather, and corporate events. "
        "Use critical_signals in the snapshot for price_distortion_read, psychological_barriers_read, "
        "and government_policy_read — educational heuristics only, not manipulation accusations. "
        "For forum threads: treat as unverified public discussion — never present as confirmed insider facts. "
        "For behavior_psych_read: explain crowd psychology and trader biases educationally — not clinical advice. "
        "You MUST include forecast_7d: an educational 7-calendar-day scenario band from baseline price. "
        "Learn from PRIOR FORECAST ACCURACY and LESSONS when present. "
        "Never invent prices, financial figures, or headlines that are not supplied. "
        "If news or forum intel is thin or unrelated, say so. When prior insights exist, explicitly state what changed. "
        "Not personalized investment advice. Return JSON only."
    )
    user = (
        f"LIVE SNAPSHOT:\n{json.dumps(snapshot, indent=2)[:8500]}\n\n"
        f"PRIOR FORECAST ACCURACY (score before writing new 7d forecast):\n{forecast_accuracy_block}\n\n"
        f"FORECAST ACCURACY LESSONS FROM RAG (apply to this memo):\n{lessons_block}\n\n"
        f"BEHAVIORAL / CROWD PSYCHOLOGY READ:\n{psych_block}\n\n"
        f"FORUM & COMMUNITY THREADS (unverified discussion — use only these):\n{forum_block}\n\n"
        f"NEWS & MACRO CATALYSTS (use only these headlines):\n{news_block}\n\n"
        f"PRIOR CHROMA INSIGHTS (append-only memory):\n{prior_block}\n\n"
        f"BOOK RAG CONTEXT:\n{books_block}\n\n"
        f"Return JSON matching this schema:\n{json.dumps(RESEARCH_SCHEMA, indent=2)}"
    )

    llm = chat_completion(system=system, user=user, provider=provider, model=model)
    insight = parse_llm_json(llm)
    insight.setdefault("stance", "neutral")
    insight.setdefault("executive_summary", insight.get("narrative") or llm.text[:1200])
    insight.setdefault("not_advice_disclaimer", "Educational research only — not investment advice.")
    insight.setdefault("news_catalyst_read", "No separate news catalyst read produced.")
    insight.setdefault("behavior_psych_read", psych_read.get("plain_english") or "No behavioral read produced.")
    insight.setdefault("psychological_barriers_read", psych_read.get("psychological_barriers_read") or "No barrier scan produced.")
    dist = critical_signals.get("price_distortion") or {}
    pol = critical_signals.get("government_policy") or {}
    insight.setdefault("price_distortion_read", dist.get("primary_read") or "No price-distortion scan produced.")
    insight.setdefault("historical_distortion_read", (critical_signals.get("price_history") or {}).get("plain_english") or "No 5-year history scan produced.")
    insight.setdefault("government_policy_read", pol.get("plain_english") or "No government policy read produced.")
    found = critical_signals.get("corporate_foundation") or {}
    insight.setdefault("corporate_foundation_read", found.get("plain_english") or "No corporate foundation scan produced.")
    insight.setdefault("forum_intel_read", "No forum intel read produced.")
    insight.setdefault("forecast_accuracy_review", "No prior forecast to review.")
    insight.setdefault("macro_risks", [])

    raw_fc = insight.get("forecast_7d") or insight.get("forecast_15d")
    forecast_7d = normalize_forecast(
        raw_fc,
        baseline_price=current_price,
        as_of=as_of,
        technicals=technicals,
        ratings=ratings,
        news_bundle=news_bundle,
    )
    insight["forecast_7d"] = forecast_7d

    stored = append_insight(
        symbol=symbol,
        insight=insight,
        provider=llm.provider,
        model=llm.model,
        as_of=snapshot.get("as_of"),
    )
    forecast_ctx = {
        "composite_stance": ratings.get("composite_stance"),
        "best_horizon": ratings.get("best_horizon"),
        "rsi_14": (technicals.get("momentum") or {}).get("rsi_14"),
    }
    forecast_stored = prepare_forecast_filing(
        symbol=symbol.upper(),
        forecast=forecast_7d,
        provider=llm.provider,
        model=llm.model,
        as_of=as_of,
        memo_id=stored.get("id"),
        context=forecast_ctx,
    )
    forecast_table = forecast_stored.get("table") or build_forecast_table(
        symbol=symbol.upper(), latest_forecast=forecast_7d, drift=forecast_stored.get("drift"),
    )
    history = list_insight_history(symbol, limit=12)
    memo_history = [
        h for h in history
        if (h.get("metadata") or {}).get("kind", "genai_deep_research") in ("genai_deep_research", "")
    ]

    return {
        "symbol": symbol.upper(),
        "provider": llm.provider,
        "model": llm.model,
        "first_analysis": len(prior) == 0,
        "prior_insights_used": len(prior),
        "book_passages_used": len(books),
        "news_headlines_used": news_bundle.get("headline_count", 0),
        "forum_threads_used": forum_bundle.get("thread_count", 0),
        "news": news_bundle,
        "forum_intel": forum_bundle,
        "behavior_psych": psych_read,
        "critical_signals": critical_signals,
        "forecast_7d": forecast_7d,
        "forecast_table": forecast_table,
        "forecast_review": forecast_review,
        "forecast_lessons": merged_lessons,
        "forecast_stored": forecast_stored,
        "insight": insight,
        "stored": stored,
        "history": [
            {
                "created_at": (h.get("metadata") or {}).get("created_at"),
                "provider": (h.get("metadata") or {}).get("provider"),
                "model": (h.get("metadata") or {}).get("model"),
                "stance": (h.get("metadata") or {}).get("stance"),
                "preview": _history_preview(h.get("text") or ""),
            }
            for h in memo_history
        ],
        "providers": list_providers(),
        "disclaimer": "GenAI research is educational only and may be incomplete or wrong. Not investment advice.",
    }
