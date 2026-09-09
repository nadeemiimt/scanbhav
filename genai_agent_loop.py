"""Interactive GenAI agentic research loop.

Specialist “desk humans” run real work (technicais, news, memory, LLM write),
and emit conversational events for a live floor UI + briefcase result.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Generator, Optional

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
from genai_research import (
    RESEARCH_SCHEMA,
    append_insight,
    build_research_snapshot,
    list_insight_history,
    retrieve_book_context,
    retrieve_prior_insights,
    _history_preview,
)
from investors import investor_perspectives
from llm_providers import chat_completion, list_providers, parse_llm_json
from market_signals import build_critical_signals
from news_catalysts import gather_news_catalysts
from utils.numbers import fmt_signed_pct


AGENTS: dict[str, dict[str, str]] = {
    "lead": {
        "id": "lead",
        "name": "Arjun Mehta",
        "role": "Desk Lead",
        "title": "Runs the floor",
        "accent": "#e8b84a",
        "initials": "AM",
    },
    "tech": {
        "id": "tech",
        "name": "Naina Kapoor",
        "role": "Technical Analyst",
        "title": "Charts & horizons",
        "accent": "#2ecf8a",
        "initials": "NK",
    },
    "psych": {
        "id": "psych",
        "name": "Dr. Ananya Rao",
        "role": "Market Psychologist",
        "title": "Crowd behaviour & bias",
        "accent": "#e8a4c8",
        "initials": "AR",
    },
    "forums": {
        "id": "forums",
        "name": "Kabir Malhotra",
        "role": "Forum Scout",
        "title": "Reddit · ValuePickr · Traderji",
        "accent": "#7ec8e3",
        "initials": "KM",
    },
    "news": {
        "id": "news",
        "name": "Vikram Sethi",
        "role": "News & Macro Scout",
        "title": "War · supply · rates",
        "accent": "#f07178",
        "initials": "VS",
    },
    "memory": {
        "id": "memory",
        "name": "Meera Iyer",
        "role": "Memory Librarian",
        "title": "Chroma insight vault",
        "accent": "#9ec3e8",
        "initials": "MI",
    },
    "writer": {
        "id": "writer",
        "name": "Rohan Desai",
        "role": "Research Writer",
        "title": "Synthesizes the memo",
        "accent": "#c6b6e8",
        "initials": "RD",
    },
    "clerk": {
        "id": "clerk",
        "name": "Sara Almeida",
        "role": "Briefcase Clerk",
        "title": "Files the result",
        "accent": "#e8b84a",
        "initials": "SA",
    },
}


def agent_roster() -> list[dict[str, str]]:
    return list(AGENTS.values())


def _evt(
    kind: str,
    agent_id: str,
    text: str = "",
    *,
    to_agent_id: Optional[str] = None,
    progress: Optional[float] = None,
    payload: Optional[dict[str, Any]] = None,
    speaking_to: str = "you",
) -> dict[str, Any]:
    agent = AGENTS[agent_id]
    out: dict[str, Any] = {
        "type": kind,
        "ts": datetime.now(timezone.utc).isoformat(),
        "agent": agent,
        "text": text,
        "speaking_to": speaking_to,
    }
    if to_agent_id:
        out["to_agent"] = AGENTS[to_agent_id]
    if progress is not None:
        out["progress"] = round(float(progress), 3)
    if payload is not None:
        out["payload"] = payload
    return out


def _pause(seconds: float = 0.9) -> None:
    """Beat between floor lines so the UI can breathe (frontend also paces)."""
    time.sleep(max(0.0, seconds))


def _pause_for_read(text: str = "", *, base: float = 0.85) -> None:
    """Longer beat after a spoken line — scales lightly with length."""
    chars = len(text or "")
    # ~28 chars/sec reading assist; capped so LLM steps still dominate runtime
    extra = min(2.8, chars / 28.0)
    time.sleep(base + extra * 0.45)


def run_agentic_research(
    *,
    symbol: str,
    technicals: dict[str, Any],
    ratings: dict[str, Any],
    quote: dict[str, Any] | None = None,
    investors: list[dict[str, Any]] | None = None,
    news: dict[str, Any] | None = None,
    extended: dict[str, Any] | None = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    execute_trades: bool = False,
    trade_quantity: int = 1,
    autonomous_picks: bool = False,
    max_autonomous_picks: int = 1,
    market_provider: str = "auto",
) -> Generator[dict[str, Any], None, None]:
    """Yield floor events, then a briefcase result payload."""
    sym = symbol.upper()
    company = (quote or {}).get("company") or {}
    name = company.get("name") or sym
    price = technicals.get("price") or (quote or {}).get("summary", {}).get("close")

    yield _evt("roster", "lead", payload={"agents": agent_roster(), "symbol": sym}, progress=0.02)
    yield _evt(
        "say",
        "lead",
        f"Hey — I’m Arjun. We’re opening a live desk on {name} ({sym}). "
        f"I’ll pull Naina for charts, Dr. Ananya for crowd behaviour, Kabir for forum chatter, "
        f"Vikram for news shocks, Meera for memory, then Rohan writes the memo and Sara files your briefcase.",
        progress=0.05,
    )
    _pause(1.25)
    yield _evt(
        "handoff",
        "lead",
        "Naina, you’re up — read the tape and horizons for me.",
        to_agent_id="tech",
        speaking_to="Naina Kapoor",
        progress=0.08,
    )
    _pause(1.05)

    # --- Technical agent (real work already done upstream; narrate it) ---
    yield _evt("status", "tech", "On it — pulling momentum, trend, and horizon grades…", progress=0.12)
    _pause(1.15)
    momentum = (technicals.get("momentum") or {})
    trend = (technicals.get("trend") or {})
    rsi = momentum.get("rsi_14")
    best = ratings.get("best_horizon")
    best_score = ((ratings.get("horizons") or {}).get(best or "") or {}).get("score")
    stance = ratings.get("composite_stance") or "mixed"
    ext_line = ""
    if extended:
        try:
            from analysis.bundle import extended_summary_for_agents
            ext_line = extended_summary_for_agents(extended)
        except Exception:
            ext_line = ""
    yield _evt(
        "say",
        "tech",
        f"Arjun, tape check: price around {price}, RSI14={rsi}, trend lean looks "
        f"{trend.get('adx_trend') or trend.get('direction') or 'mixed'}. "
        f"Composite stance is {stance}; best horizon is {(best or 'n/a').upper()}"
        f"{f' at {best_score}' if best_score is not None else ''}. "
        f"{'Extended: ' + ext_line[:220] + ('…' if len(ext_line) > 220 else '') + ' ' if ext_line else ''}"
        "Handing you the snapshot — not a buy/sell call.",
        speaking_to="Arjun Mehta",
        progress=0.22,
        payload={"technicals_summary": {"rsi_14": rsi, "best_horizon": best, "stance": stance, "price": price}, "extended": extended},
    )
    _pause(1.35)
    yield _evt(
        "handoff",
        "lead",
        "Ananya — read the room. How might traders be behaving on this tape?",
        to_agent_id="psych",
        speaking_to="Dr. Ananya Rao",
        progress=0.24,
    )
    _pause(1.05)

    # --- Market psychologist ---
    yield _evt("status", "psych", "Observing crowd mood — RSI extremes, anchoring, FOMO vs fear…", progress=0.26)
    psych_read = analyze_trader_behavior(technicals, ratings)
    barrier_headline = psych_read.get("psychological_barriers_read") or ""
    bias_bits = "; ".join((psych_read.get("biases") or [])[:2]) or psych_read.get("plain_english", "")
    yield _evt(
        "say",
        "psych",
        f"Arjun — {psych_read.get('headline', 'Behaviour read ready.')} "
        f"{bias_bits[:200]}{'…' if len(bias_bits) > 200 else ''} "
        f"{barrier_headline[:160]}{'…' if len(barrier_headline) > 160 else ''} "
        "This is educational crowd psychology, not clinical advice.",
        speaking_to="Arjun Mehta",
        progress=0.32,
        payload={"behavior_psych": psych_read},
    )
    _pause(1.25)
    yield _evt(
        "handoff",
        "lead",
        "Kabir — sweep the forums. Reddit, ValuePickr, Traderji — anything whispered about this name.",
        to_agent_id="forums",
        speaking_to="Kabir Malhotra",
        progress=0.34,
    )
    _pause(1.05)

    # --- Forum scout ---
    yield _evt("status", "forums", "Scanning public forum threads and community RSS…", progress=0.36)
    forum_bundle = gather_forum_intel(sym, company_name=company.get("name"))
    threads = forum_bundle.get("threads") or []
    rumor_n = forum_bundle.get("rumor_count") or 0
    loudest = forum_bundle.get("loudest_thread") or "quiet on the forums today"
    yield _evt(
        "say",
        "forums",
        f"Desk — {forum_bundle.get('thread_count', 0)} public threads in, {rumor_n} tagged unverified rumor/tip. "
        f"Loudest: “{loudest[:100]}”. "
        "Treat as discussion only — not confirmed insider information.",
        speaking_to="Arjun Mehta",
        progress=0.42,
        payload={"forum_preview": threads[:3]},
    )
    _pause(1.25)
    yield _evt(
        "handoff",
        "lead",
        "Good. Vikram — scan for war, supply squeezes, rates, regulation. Anything that can move this name.",
        to_agent_id="news",
        speaking_to="Vikram Sethi",
        progress=0.44,
    )
    _pause(1.05)

    # --- News scout ---
    yield _evt("status", "news", "I’m on the wires — company feed plus macro sweep…", progress=0.46)
    news_bundle = news or gather_news_catalysts(
        sym,
        company_name=company.get("name"),
        sector=company.get("sector"),
        industry=company.get("industry"),
        existing_news=(quote or {}).get("news") or [],
    )
    critical_signals = build_critical_signals(
        technicals=technicals,
        ratings=ratings,
        news=news_bundle,
        quote=quote,
    )
    policy_read = critical_signals.get("government_policy") or {}
    distortion_read = critical_signals.get("price_distortion") or {}
    hi = news_bundle.get("high_impact_count") or 0
    tags = news_bundle.get("tag_counts") or {}
    tag_bits = ", ".join(f"{k.replace('_', ' ')}×{v}" for k, v in list(tags.items())[:4]) or "mostly general"
    top = (news_bundle.get("high_impact_headlines") or news_bundle.get("headlines") or [])[:2]
    top_line = top[0]["title"] if top else "nothing loud enough to shout about"
    policy_line = ""
    if policy_read.get("policy_exposure") in {"moderate", "high"}:
        policy_line = f" Government-policy exposure is {policy_read['policy_exposure']} for {policy_read.get('sector_label', 'this sector')}."
    hist = critical_signals.get("price_history") or {}
    hist_line = ""
    if hist.get("recent_episodes") or hist.get("pump_and_dump_count_5y", 0) > 0:
        hist_line = (
            f" 5y distortion history: {hist.get('pump_count_5y', 0)} pumps, {hist.get('dump_count_5y', 0)} dumps, "
            f"{hist.get('pump_and_dump_count_5y', 0)} pump→dump pairs."
        )
        if hist.get("recent_pump_dump_emphasis"):
            hist_line += f" {hist['recent_pump_dump_emphasis'][:120]}"
    found = critical_signals.get("corporate_foundation") or {}
    found_line = ""
    if found.get("foundation_exposure") in {"moderate", "high"}:
        found_line = f" Foundation scan: {found.get('foundation_exposure')} stress — {found.get('headline', '')[:100]}"
    ext_macro = ""
    if extended:
        ext = extended.get("external") or {}
        reg = ((extended.get("regime") or {}).get("regime") or {}).get("regime")
        sent = (ext.get("nlp_sentiment") or {}).get("label")
        fii = ((extended.get("india") or {}).get("fii_dii_flows_market") or {}).get("status")
        opt_pcr = (extended.get("options") or {}).get("pcr_oi")
        parts = [p for p in [
            f"regime {reg}" if reg else None,
            f"sentiment {sent}" if sent else None,
            f"FII/DII feed {fii}" if fii else None,
            f"PCR {opt_pcr}" if opt_pcr else None,
        ] if p]
        if parts:
            ext_macro = f" Extended desk: {', '.join(parts)}."
    yield _evt(
        "say",
        "news",
        f"Desk — {news_bundle.get('headline_count', 0)} headlines in, {hi} tagged high-impact "
        f"({tag_bits}). Loudest one I’m seeing: “{top_line[:110]}”. "
        f"{policy_line}"
        f"Price-distortion scan: inflation risk {distortion_read.get('inflation_risk', 'n/a')}, "
        f"deflation risk {distortion_read.get('deflation_risk', 'n/a')}.{hist_line}{found_line}{ext_macro} "
        "I’ll leave the full clip pack for Rohan.",
        speaking_to="Arjun Mehta",
        progress=0.52,
        payload={"news_preview": top[:3], "critical_signals": critical_signals, "extended_macro": extended},
    )
    _pause(1.35)
    yield _evt(
        "handoff",
        "lead",
        "Meera, check the vault — what did we write last time on this symbol?",
        to_agent_id="memory",
        speaking_to="Meera Iyer",
        progress=0.54,
    )
    _pause(1.05)

    # --- Memory librarian ---
    yield _evt("status", "memory", "Opening Chroma stock_insights… searching prior memos.", progress=0.56)
    snapshot = build_research_snapshot(
        symbol=sym,
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
    current_price = float(snapshot.get("price") or price or 0)
    as_of = snapshot.get("as_of") or ""
    forecast_review = review_pending_forecasts(
        symbol=sym,
        current_price=current_price,
        as_of=as_of,
        news_bundle=news_bundle,
        technicals=technicals,
        ratings=ratings,
    )
    forecast_lessons = retrieve_forecast_lessons(
        f"{sym} forecast accuracy direction target news catalyst",
        symbol=sym,
        top_k=5,
        include_global=True,
    )
    from trading.morning_scan import morning_scan_status, retrieve_morning_scan_context
    from trading.deep_universe_scan import deep_scan_status, retrieve_conviction_context
    from trading.latency_compensation import retrieve_latency_compensation_context

    ms_ctx = retrieve_morning_scan_context(
        f"{sym} morning scan composite bullish trend",
        symbol=sym,
        top_k=4,
    )
    ms_market = retrieve_morning_scan_context("Nifty 500 morning market map top bullish", top_k=2)
    ms_status = morning_scan_status()
    conviction_ctx = retrieve_conviction_context(
        f"{sym} highest conviction composite dossier",
        top_k=6,
    )
    conviction_market = retrieve_conviction_context("top 30 highest conviction Nifty 500 stocks", top_k=8)
    conviction_status = deep_scan_status()
    latency_ctx = retrieve_latency_compensation_context(sym, top_k=3)
    global_lessons = retrieve_forecast_lessons(
        "forecast miss accuracy lesson macro news wrong prediction",
        symbol=None,
        top_k=3,
        include_global=True,
    )
    # Dedupe lessons by text prefix
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
        f"Deep equity research update for {sym}: trend, momentum, valuation risk, "
        f"news catalysts (war, supply, rates, regulation), "
        f"and what changed since prior memo. Price {snapshot.get('price')} as of {snapshot.get('as_of')}."
    )
    prior = retrieve_prior_insights(sym, query, top_k=6)
    books = retrieve_book_context(query, top_k=4)
    if prior:
        preview = _history_preview(prior[0].get("text") or "")
        yield _evt(
            "say",
            "memory",
            f"Found {len(prior)} prior insight(s). Latest preview: “{preview[:160]}”. "
            "I’ll pass the stack to Rohan so he can say what changed.",
            speaking_to="Rohan Desai",
            progress=0.62,
        )
    else:
        yield _evt(
            "say",
            "memory",
            "Vault’s empty for this symbol — first memo. Rohan, you’re writing on a clean slate.",
            speaking_to="Rohan Desai",
            progress=0.62,
        )
    final_reviews = [r for r in (forecast_review.get("reviews") or []) if (r.get("score") or {}).get("maturity") == "final"]
    interim_reviews = [r for r in (forecast_review.get("reviews") or []) if (r.get("score") or {}).get("maturity") == "interim"]
    if final_reviews:
        r0 = final_reviews[0]
        sc = r0.get("score") or {}
        yield _evt(
            "say",
            "memory",
            f"7-day forecast check — prior call was {sc.get('label')} "
            f"({sc.get('accuracy_pct')}% accuracy): predicted {sc.get('predicted_direction')} "
            f"to {sc.get('target_price')}, actual {fmt_signed_pct(sc.get('actual_return_pct'))}%. "
            f"{((sc.get('mismatch') or {}).get('summary') or '')[:140]}",
            speaking_to="Rohan Desai",
            progress=0.63,
        )
    elif interim_reviews:
        r0 = interim_reviews[0]
        sc = r0.get("score") or {}
        yield _evt(
            "say",
            "memory",
            f"Prior 7-day forecast still in progress (day {r0.get('days_old', '?')}): "
            f"MTM {fmt_signed_pct(sc.get('actual_return_pct'))}% vs baseline — not final yet.",
            speaking_to="Rohan Desai",
            progress=0.63,
        )
    if merged_lessons:
        yield _evt(
            "say",
            "memory",
            f"Pulled {len(merged_lessons)} forecast accuracy lesson(s) from the vault — "
            "Rohan should learn from prior misses on this desk.",
            speaking_to="Rohan Desai",
            progress=0.635,
        )
    if ms_ctx or ms_market:
        yield _evt(
            "say",
            "memory",
            f"Morning Nifty 500 RAG ready ({ms_status.get('trade_date_ist') or 'not run today'}) — "
            f"{ms_status.get('scored') or 0} names pre-scored, {len(ms_ctx)} memos for {sym}.",
            speaking_to="Rohan Desai",
            progress=0.638,
        )
    if conviction_ctx or conviction_market:
        yield _evt(
            "say",
            "memory",
            f"Universe conviction RAG ({conviction_status.get('trade_date_ist') or 'not scanned'}) — "
            f"{len(conviction_market)} top-conviction memos available for ranking queries.",
            speaking_to="Rohan Desai",
            progress=0.6385,
        )
    if latency_ctx:
        yield _evt(
            "say",
            "memory",
            "Latency compensation RAG loaded — our feed is ~2–15s behind pro desks; "
            "pre-emptive entry when momentum + session patterns align.",
            speaking_to="Rohan Desai",
            progress=0.639,
        )
    if books:
        yield _evt(
            "say",
            "memory",
            f"Also pulled {len(books)} book passage(s) for grounding — educational only.",
            speaking_to="Rohan Desai",
            progress=0.64,
        )
    _pause(1.15)
    yield _evt(
        "handoff",
        "lead",
        f"Rohan — synthesize technicals, behaviour, forum chatter, news, and memory into one memo via "
        f"{provider or 'configured LLM'}. Talk to me when the draft’s ready.",
        to_agent_id="writer",
        speaking_to="Rohan Desai",
        progress=0.66,
    )
    _pause(1.05)

    # --- Writer (LLM) ---
    yield _evt(
        "status",
        "writer",
        "Got it. Drafting the research memo now — this is the heavy lift…",
        progress=0.68,
    )
    yield _evt(
        "say",
        "writer",
        "I’ll stay with the supplied facts only — no invented prices or fake headlines.",
        speaking_to="you",
        progress=0.7,
    )

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
    for i, t in enumerate(threads[:10], start=1):
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
            fc = rev.get("forecast") or {}
            lines.append(
                f"[Review {i} · day {rev.get('days_old')} · {sc.get('maturity')}]\n"
                f"Predicted: {sc.get('predicted_direction')} → target {sc.get('target_price')} "
                f"from baseline {sc.get('baseline_price')}\n"
                f"Actual: {sc.get('actual_price')} ({fmt_signed_pct(sc.get('actual_return_pct'))}%) · "
                f"label={sc.get('label')} · accuracy={sc.get('accuracy_pct')}%\n"
                f"Mismatch: {((sc.get('mismatch') or {}).get('summary') or 'n/a')}\n"
                f"Events: {', '.join(((sc.get('mismatch') or {}).get('likely_events') or [])[:3]) or 'none listed'}"
            )
        forecast_accuracy_block = "\n\n".join(lines)

    lessons_block = format_lessons_block(merged_lessons)

    ms_block = "\n\n".join(
        f"[Morning scan {i}]\n{(h.get('text') or '')[:900]}"
        for i, h in enumerate((ms_ctx or [])[:4], start=1)
    ) or "(No morning scan memos for this symbol.)"

    conviction_block = "\n\n".join(
        f"[Conviction RAG {i} · {(h.get('metadata') or {}).get('symbol') or 'market'}]\n{(h.get('text') or '')[:1200]}"
        for i, h in enumerate((conviction_ctx or [])[:4] + (conviction_market or [])[:6], start=1)
    ) or "(No universe conviction scan memos — run deep conviction scan on Multi Screen.)"

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
        "You MUST include forecast_7d: an educational 7-calendar-day scenario band from baseline price "
        "(direction, target, band, drivers, risks). Learn from PRIOR FORECAST ACCURACY and LESSONS when present. "
        "Never invent prices, financial figures, or headlines that are not supplied. "
        "If news or forum intel is thin or unrelated, say so. When prior insights exist, explicitly state what changed. "
        "Not personalized investment advice. Return JSON only."
    )
    user = (
        f"LIVE SNAPSHOT:\n{json.dumps(snapshot, indent=2)[:8500]}\n\n"
        f"LATENCY COMPENSATION (feed delay + pre-emptive entry patterns):\n{latency_ctx[:2000]}\n\n"
        f"MORNING SCAN RAG:\n{ms_block}\n\n"
        f"UNIVERSE CONVICTION RAG (top Nifty 500 by conviction score):\n{conviction_block}\n\n"
        f"PRIOR FORECAST ACCURACY (score before writing new 7d forecast):\n{forecast_accuracy_block}\n\n"
        f"FORECAST ACCURACY LESSONS FROM RAG (apply to this memo):\n{lessons_block}\n\n"
        f"BEHAVIORAL / CROWD PSYCHOLOGY READ:\n{psych_block}\n\n"
        f"FORUM & COMMUNITY THREADS (unverified discussion — use only these):\n{forum_block}\n\n"
        f"NEWS & MACRO CATALYSTS (use only these headlines):\n{news_block}\n\n"
        f"PRIOR CHROMA INSIGHTS (append-only memory):\n{prior_block}\n\n"
        f"BOOK RAG CONTEXT:\n{books_block}\n\n"
        f"Return JSON matching this schema:\n{json.dumps(RESEARCH_SCHEMA, indent=2)}"
    )

    try:
        llm = chat_completion(system=system, user=user, provider=provider, model=model)
        insight = parse_llm_json(llm)
    except Exception as exc:
        yield _evt(
            "say",
            "writer",
            f"Arjun — I hit a wall writing the memo: {exc}. Stopping the loop so we don’t file a bad brief.",
            speaking_to="Arjun Mehta",
            progress=0.85,
        )
        yield _evt("error", "lead", str(exc), progress=1.0)
        return

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

    trade_result = None
    agent_picks_result = None
    if autonomous_picks:
        from trading.agent_picker import run_autonomous_stock_picks

        yield _evt(
            "say",
            "lead",
            "Autonomy mode — I’m scanning the watchlist and liquid names for the strongest trend + composite + news setup…",
            speaking_to="you",
            progress=0.84,
        )
        _pause(0.8)
        agent_picks_result = run_autonomous_stock_picks(
            execute=execute_trades,
            quantity=trade_quantity,
            max_picks=max_autonomous_picks,
            seed_symbol=sym,
            market_provider=market_provider,
        )
        budget = agent_picks_result.get("budget") or {}
        picks = agent_picks_result.get("picks") or []
        yield _evt(
            "say",
            "lead",
            f"Nifty 500 scan — budget left ₹{budget.get('remaining_budget_inr', 0):,.0f} "
            f"(cap ₹{budget.get('max_per_order_inr', 0):,.0f}/order). "
            f"{agent_picks_result.get('affordable_candidates', 0)} affordable candidates.",
            speaking_to="you",
            progress=0.845,
        )
        if picks:
            top = picks[0]
            yield _evt(
                "say",
                "tech",
                f"Best fit: {top.get('symbol')} — qty {top.get('quantity')} @ ₹{top.get('price')} "
                f"(₹{top.get('notional_inr'):,.0f}, est. profit ₹{top.get('expected_profit_inr')}). "
                f"Composite {top.get('composite_score')}, {top.get('stance')}.",
                speaking_to="you",
                progress=0.855,
            )
        else:
            yield _evt(
                "say",
                "tech",
                "No names cleared the autonomous filter today (composite/stance/risk minimums).",
                speaking_to="you",
                progress=0.855,
            )
        if execute_trades:
            for tr in agent_picks_result.get("trades") or []:
                if tr.get("skipped"):
                    yield _evt(
                        "say",
                        "clerk",
                        f"{tr.get('symbol')}: skipped — {tr.get('reason') or tr.get('message', 'risk/rules')}.",
                        speaking_to="you",
                        progress=0.86,
                    )
                else:
                    yield _evt(
                        "say",
                        "clerk",
                        f"Autonomous buy: {tr.get('symbol')} qty {tr.get('quantity')} — "
                        f"{tr.get('mode', 'paper')} ₹{tr.get('notional_inr', '—')} "
                        f"(est. profit ₹{tr.get('expected_profit_inr', '—')}).",
                        speaking_to="you",
                        progress=0.86,
                    )
    elif execute_trades:
        from trading.agent_picker import run_given_stock_trades

        yield _evt(
            "say",
            "lead",
            "Watchlist mode — scoring your given symbols against budget caps (morning scan data if ready)…",
            speaking_to="you",
            progress=0.84,
        )
        _pause(0.6)
        agent_picks_result = run_given_stock_trades(
            execute=True,
            quantity=trade_quantity,
            max_picks=max_autonomous_picks,
            seed_symbol=sym,
            market_provider=market_provider,
        )
        if agent_picks_result.get("error"):
            yield _evt("say", "clerk", agent_picks_result["error"], speaking_to="you", progress=0.86)
        for tr in agent_picks_result.get("trades") or []:
            if tr.get("skipped"):
                yield _evt(
                    "say",
                    "clerk",
                    f"{tr.get('symbol')}: skipped — {tr.get('reason') or tr.get('message', 'risk/rules')}.",
                    speaking_to="you",
                    progress=0.86,
                )
            else:
                yield _evt(
                    "say",
                    "clerk",
                    f"Watchlist buy: {tr.get('symbol')} qty {tr.get('quantity')} — {tr.get('mode', 'paper')}.",
                    speaking_to="you",
                    progress=0.86,
                )
        trade_result = (agent_picks_result.get("trades") or [None])[0]

    summary = (insight.get("executive_summary") or "")[:220]
    fc_line = (
        f" 7-day scenario: {forecast_7d.get('direction')} to {forecast_7d.get('target_price')} "
        f"({fmt_signed_pct(forecast_7d.get('expected_return_pct'), digits=1)}%)."
    )
    yield _evt(
        "say",
        "writer",
        f"Draft’s ready. Stance: {insight.get('stance')}.{fc_line} "
        f"One-liner for the floor: “{summary}”. Sara — please file it.",
        speaking_to="Sara Almeida",
        progress=0.88,
    )
    _pause(1.05)
    yield _evt(
        "handoff",
        "writer",
        "Briefcase please — stamp it educational-only.",
        to_agent_id="clerk",
        speaking_to="Sara Almeida",
        progress=0.9,
    )
    _pause(0.95)

    # --- Clerk ---
    yield _evt("status", "clerk", "Filing into Chroma and packing your briefcase…", progress=0.93)
    stored = append_insight(
        symbol=sym,
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
        symbol=sym,
        forecast=forecast_7d,
        provider=llm.provider,
        model=llm.model,
        as_of=as_of,
        memo_id=stored.get("id"),
        context=forecast_ctx,
    )
    forecast_table = forecast_stored.get("table") or build_forecast_table(
        symbol=sym, latest_forecast=forecast_7d, drift=forecast_stored.get("drift"),
    )
    history = list_insight_history(sym, limit=12)
    memo_history = [
        h for h in history
        if (h.get("metadata") or {}).get("kind", "genai_deep_research") in ("genai_deep_research", "")
    ]
    drift_note = ""
    if forecast_stored.get("drift", {}).get("highlight"):
        drift_note = f" Drift: {forecast_stored['drift'].get('reason_short')}."
    result = {
        "symbol": sym,
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
        "agent_trade": trade_result,
        "agent_picks": agent_picks_result,
        "briefcase": {
            "title": f"{sym} research brief",
            "filed_at": stored.get("created_at"),
            "file_id": stored.get("id"),
            "label": "RESULT FILE",
        },
    }
    yield _evt(
        "say",
        "clerk",
        f"Done. Your result file is packed — open the Briefcase tab. "
        f"7-day forecast filed ({forecast_7d.get('direction')} → {forecast_7d.get('target_price')})."
        f"{drift_note} "
        f"Filed as {stored.get('id', 'memo')[:8]}… Not advice, just the desk’s homework.",
        speaking_to="you",
        progress=0.97,
    )
    yield _evt(
        "briefcase",
        "clerk",
        "Briefcase unlocked.",
        progress=0.99,
        payload={"result": result},
    )
    yield _evt(
        "say",
        "lead",
        "Floor’s clear. Read the brief in the Briefcase whenever you’re ready — ask us to run again anytime.",
        speaking_to="you",
        progress=1.0,
    )
    yield _evt("done", "lead", "Agent loop complete.", progress=1.0, payload={"symbol": sym})


def investors_from_quote(tech: dict[str, Any], quote: dict[str, Any]) -> list[dict[str, Any]]:
    company = quote.get("company") or {}
    fundamentals = dict(quote.get("fundamentals") or {})
    investor_fundamentals = {
        **fundamentals,
        "debtToEquity": (
            (fundamentals.get("debt_to_equity") * 100)
            if isinstance(fundamentals.get("debt_to_equity"), (int, float))
            else company.get("debt_to_equity")
        ),
        "trailingPE": company.get("trailing_pe") or company.get("pe_ratio"),
        "returnOnEquity": (
            (fundamentals.get("roe_pct") / 100.0)
            if isinstance(fundamentals.get("roe_pct"), (int, float))
            else None
        ),
        "profitMargins": (
            (fundamentals.get("net_margin_pct") / 100.0)
            if isinstance(fundamentals.get("net_margin_pct"), (int, float))
            else None
        ),
        "revenueGrowth": (
            (fundamentals.get("revenue_growth_yoy_pct") / 100.0)
            if isinstance(fundamentals.get("revenue_growth_yoy_pct"), (int, float))
            else None
        ),
        "sector": company.get("sector"),
        "industry": company.get("industry"),
    }
    return investor_perspectives(tech, investor_fundamentals)
