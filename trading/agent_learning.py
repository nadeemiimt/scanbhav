"""
Agent auto-pick learning layer — RAG, timing profiles, and pick_log learning curve.

Brings curated-desk parity: timing learn at pre-market, per-symbol lessons in ranking,
and progressive win/loss adjustments from closed trades.
"""
from __future__ import annotations

from typing import Any

from trading.config_store import load_trading_config


def agent_learning_cfg() -> dict[str, Any]:
    ap = load_trading_config().get("autopilot") or {}
    return {
        "enabled": bool(ap.get("agent_learning_enabled", True)),
        "timing_learn_top_n": int(ap.get("agent_timing_learn_top_n") or 30),
        "deep_analyze_top_n": int(ap.get("agent_deep_analyze_top_n") or 20),
        "rag_top_k": int(ap.get("agent_rag_top_k") or 5),
        "curated_overlap_boost": float(ap.get("agent_curated_overlap_boost") or 18.0),
        "timing_window_boost": float(ap.get("agent_timing_window_boost") or 8.0),
        "timing_window_penalty": float(ap.get("agent_timing_window_penalty") or 6.0),
        "learning_curve_weight": float(ap.get("agent_learning_curve_weight") or 1.0),
        "min_pick_log_trades": int(ap.get("agent_min_pick_log_trades") or 2),
    }


def _symbol_base(symbol: str) -> str:
    return str(symbol or "").upper().replace(".NSE", "")


def timing_profile_score(symbol: str, *, window_id: str | None = None) -> tuple[float, list[str]]:
    """Boost when the current IST window matches learned favorable windows."""
    from trading.timing_intelligence import _load_profiles, current_session_window

    sym = _symbol_base(symbol)
    profile = (_load_profiles().get("symbols") or {}).get(sym) or {}
    if not profile:
        return 0.0, []

    cfg = agent_learning_cfg()
    window = current_session_window()
    wid = window_id or window.get("id") or ""
    fav = profile.get("favorable_windows") or []
    reasons: list[str] = []
    score = 0.0

    gap_rate = float(profile.get("gap_continuation_rate") or 0)
    if gap_rate >= 0.55:
        score += 3.0
        reasons.append(f"gap_cont_{gap_rate:.2f}")

    if fav and wid:
        if wid in fav:
            score += cfg["timing_window_boost"]
            reasons.append(f"timing_fav_{wid}")
        elif wid in {"midday", "power_hour"} and "morning_trend" in fav:
            score += cfg["timing_window_boost"] * 0.35
            reasons.append("timing_proxy_morning")
        else:
            score -= cfg["timing_window_penalty"]
            reasons.append(f"timing_unfav_{wid}")

    return round(score, 2), reasons


def learning_curve_adjustment(symbol: str) -> tuple[float, dict[str, Any]]:
    """Progressive score from pick_log win rate and recent P/L."""
    from trading.pick_learning import symbol_pick_stats

    cfg = agent_learning_cfg()
    sym = _symbol_base(symbol)
    stats = symbol_pick_stats(sym)
    total = int(stats.get("total") or 0)
    meta = {"pick_log": stats}

    if total < cfg["min_pick_log_trades"]:
        return 0.0, meta

    wr = float(stats.get("win_rate") or 0.5)
    pnl = float(stats.get("total_pnl_inr") or 0)
    weight = cfg["learning_curve_weight"]

    adj = (wr - 0.5) * 14.0 * weight
    if total >= 3:
        adj += max(-8.0, min(8.0, pnl / 2500.0))

    if wr <= 0.33 and total >= 3:
        adj -= 6.0 * weight
    elif wr >= 0.65 and total >= 2:
        adj += 4.0 * weight

    return round(max(-12.0, min(12.0, adj)), 2), meta


def rag_learning_adjustment(symbol: str, *, top_k: int | None = None) -> tuple[float, list[str], list[dict[str, Any]]]:
    """RAG lessons: trade outcomes, timing profiles, operational rules, session digests."""
    from trading.pick_learning import retrieve_agent_lessons

    cfg = agent_learning_cfg()
    sym = _symbol_base(symbol)
    lessons = retrieve_agent_lessons(sym, top_k=top_k or cfg["rag_top_k"])
    if not lessons:
        return 0.0, [], []

    adj = 0.0
    reasons: list[str] = []
    for row in lessons:
        stance = str(row.get("stance") or "").lower()
        kind = str(row.get("kind") or "")
        if stance == "win":
            adj += 3.0 if kind == "autopilot_session_symbol_digest" else 2.5
            reasons.append(f"rag_win_{kind[:12]}")
        elif stance == "loss":
            adj -= 4.0 if kind in {"autopilot_operational_lesson", "autopilot_session_symbol_digest"} else 3.0
            reasons.append(f"rag_loss_{kind[:12]}")
        elif kind == "timing_profile":
            if stance in {"constructive", "favorable", "strong_favorable"}:
                adj += 2.0
                reasons.append("rag_timing_ok")
            else:
                adj -= 1.0

    return round(max(-12.0, min(12.0, adj)), 2), reasons, lessons


def agent_learning_score(
    row: dict[str, Any],
    *,
    curated_symbols: set[str] | None = None,
    ist_mins: int | None = None,
) -> tuple[float, dict[str, Any], list[str]]:
    """Combined learning score added to intraday edge ranking."""
    cfg = agent_learning_cfg()
    sym = str(row.get("symbol") or "").upper()
    sym_base = _symbol_base(sym)
    reasons: list[str] = []
    meta: dict[str, Any] = {"learning_enabled": cfg["enabled"]}

    if not cfg["enabled"]:
        return 0.0, meta, reasons

    total = 0.0
    curated = {_symbol_base(s) for s in (curated_symbols or set())}
    if sym_base in curated or sym in curated:
        total += cfg["curated_overlap_boost"]
        reasons.append("curated_overlap")

    timing_adj, timing_reasons = timing_profile_score(sym)
    total += timing_adj
    reasons.extend(timing_reasons)
    meta["timing_adj"] = timing_adj

    curve_adj, curve_meta = learning_curve_adjustment(sym)
    total += curve_adj
    reasons.extend([f"curve_{curve_adj:+.1f}"] if curve_adj else [])
    meta["learning_curve"] = curve_meta

    rag_adj, rag_reasons, rag_lessons = rag_learning_adjustment(sym)
    total += rag_adj
    reasons.extend(rag_reasons)
    meta["rag_adj"] = rag_adj
    meta["rag_lessons"] = rag_lessons[:3]

    news_score = row.get("news_score")
    pattern_score = row.get("pattern_score")
    if news_score is not None and pattern_score is not None:
        try:
            ns, ps = float(news_score), float(pattern_score)
            if ns >= 60 and ps >= 62:
                total += 5.0
                reasons.append("news_pattern_confluence")
                meta["confluence"] = True
            elif ns >= 55 and ps >= 58:
                total += 2.5
                reasons.append("news_pattern_align")
        except (TypeError, ValueError):
            pass

    return round(total, 2), meta, reasons


def enrich_agent_candidate_rows(
    rows: list[dict[str, Any]],
    *,
    market_provider: str = "auto",
    top_n: int | None = None,
) -> list[dict[str, Any]]:
    """
    Deep-analyze top scan rows missing technicals — same path curated uses for missing symbols.
    """
    cfg = agent_learning_cfg()
    if not cfg["enabled"]:
        return rows

    n = top_n or cfg["deep_analyze_top_n"]
    ranked = sorted(
        rows,
        key=lambda r: float(r.get("composite_score") or 0),
        reverse=True,
    )
    by_sym = {str(r.get("symbol") or "").upper(): dict(r) for r in rows}
    enriched = 0

    for row in ranked[:n]:
        sym = str(row.get("symbol") or "").upper()
        if not sym:
            continue
        needs = (
            row.get("atr_pct") is None
            or row.get("horizon_return_pct") is None
            or float(row.get("composite_score") or 0) <= 0
        )
        if not needs:
            continue
        try:
            from trading.scheduler import _analyze_symbol

            a = _analyze_symbol(sym, market_provider)
            merged = {**row, **{
                k: v for k, v in a.items()
                if v is not None and (row.get(k) is None or k in {"atr_pct", "horizon_return_pct", "composite_score", "stance", "rsi_14"})
            }}
            by_sym[sym] = merged
            enriched += 1
        except Exception:
            continue

    out = list(by_sym.values())
    out.sort(key=lambda r: float(r.get("composite_score") or 0), reverse=True)

    try:
        from trading.market_news_intel import batch_enrich_rows_with_news
        from trading.intraday_patterns import batch_attach_pattern_scores

        out, _news_meta = batch_enrich_rows_with_news(out, top_n=n)
        out = batch_attach_pattern_scores(out, top_n=n)
    except Exception:
        pass

    out.sort(key=lambda r: float(r.get("composite_score") or 0), reverse=True)
    return out


def agent_premarket_learn(
    rows: list[dict[str, Any]],
    *,
    curated_symbols: list[str] | None = None,
    top_n: int | None = None,
) -> dict[str, Any]:
    """Learn timing profiles + RAG for top agent candidates (curated parity)."""
    from trading.agent_selection import rank_rows_for_agent, ist_minutes_now
    from trading.timing_intelligence import learn_timing_batch

    cfg = agent_learning_cfg()
    n = top_n or cfg["timing_learn_top_n"]
    curated_set = {_symbol_base(s) for s in (curated_symbols or []) if s}

    ranked = rank_rows_for_agent(
        rows,
        min_composite=50,
        held=set(),
        top_n=n,
        target_pct=2.0,
        ist_mins=ist_minutes_now(),
        curated_symbols=curated_set,
    )
    symbols = list(dict.fromkeys(
        [_symbol_base(r.get("symbol")) for r in ranked if r.get("symbol")]
        + [_symbol_base(s) for s in (curated_symbols or []) if s]
    ))[: max(n, len(curated_set))]

    if not symbols:
        return {"skipped": True, "reason": "no_symbols", "learned": 0}

    timing = learn_timing_batch(symbols, feed_rag=True)
    return {
        "symbols": symbols,
        "symbol_count": len(symbols),
        "timing_learn": timing,
        "top_ranked": [r.get("symbol") for r in ranked[:10]],
    }


def attach_rag_to_pick(pick: dict[str, Any]) -> dict[str, Any]:
    """Attach RAG context to a pick before execution (for decision logging)."""
    sym = str(pick.get("symbol") or "")
    if not sym:
        return pick
    _, meta, reasons = agent_learning_score(
        pick.get("screen_row") or pick,
        curated_symbols=set(),
    )
    lessons = meta.get("rag_lessons") or []
    if lessons or reasons:
        return {
            **pick,
            "agent_learning": meta,
            "learning_reasons": reasons,
            "rag_lessons": lessons,
        }
    return pick
