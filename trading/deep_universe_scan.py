"""Deep Nifty 500 conviction scan — dossier-grade scores cached + RAG for agent retrieval."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from config import BASE_DIR
from deep_dossier import (
    build_competitive_moat,
    build_conviction_ensemble,
    build_extended_board_rows,
    build_technical_board,
)
from genai_research import append_insight, insights_collection
from screener import load_cached_screen, screen_universe

SCAN_PATH = BASE_DIR / "data" / "trading" / "universe_conviction.json"
RAG_BATCH_SIZE = 25


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ist_today() -> str:
    return datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d")


def load_deep_scan() -> Optional[dict[str, Any]]:
    if not SCAN_PATH.exists():
        return None
    try:
        return json.loads(SCAN_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def deep_scan_status() -> dict[str, Any]:
    data = load_deep_scan() or {}
    top = (data.get("rows") or [])[:5]
    return {
        "ready": bool(data.get("rows")),
        "last_run_at": data.get("run_at"),
        "trade_date_ist": data.get("trade_date_ist"),
        "scored": data.get("scored"),
        "rag_chunks": data.get("rag_chunks"),
        "top_conviction": [
            {"symbol": r.get("symbol"), "conviction_score": r.get("conviction_score"), "confidence": r.get("confidence")}
            for r in top
        ],
    }


def conviction_from_item(item: dict[str, Any]) -> dict[str, Any]:
    """Build conviction ensemble from an existing screener row (no extra price fetch)."""
    tech = item.get("technicals") or {}
    ratings = item.get("ratings") or {}
    extended = item.get("extended") or {}
    sym = str(item.get("symbol") or "")
    board = build_technical_board(tech)
    board.extend(build_extended_board_rows(extended))
    moat = build_competitive_moat(symbol=sym, quote=None, tech=tech)
    conv = build_conviction_ensemble(
        tech=tech,
        ratings=ratings,
        moat=moat,
        board=board,
        news=None,
        critical=None,
        extended=extended,
    )
    return conv


def _compact_conviction_row(item: dict[str, Any], conv: dict[str, Any]) -> dict[str, Any]:
    ratings = item.get("ratings") or {}
    tech = item.get("technicals") or {}
    mom = tech.get("momentum") or {}
    tr = tech.get("trend") or {}
    ma = tech.get("moving_averages") or {}
    ext = item.get("extended") or {}
    fund = (ext.get("fundamentals") or {}).get("quality_scores") or {}
    return {
        "symbol": item.get("symbol"),
        "price": item.get("price"),
        "as_of": item.get("as_of"),
        "bucket": item.get("bucket"),
        "conviction_score": conv.get("conviction_score"),
        "confidence": conv.get("confidence"),
        "conviction_band": conv.get("band"),
        "composite_score": ratings.get("composite_score"),
        "grade": ratings.get("composite_grade"),
        "stance": ratings.get("composite_stance"),
        "best_horizon": ratings.get("best_horizon"),
        "rsi_14": mom.get("rsi_14"),
        "macd_hist": mom.get("macd_hist"),
        "supertrend_dir": tr.get("supertrend_dir"),
        "golden_cross": ma.get("golden_cross"),
        "quality_score": fund.get("composite_quality"),
        "pattern_bias": (ext.get("patterns") or {}).get("composite_bias"),
        "parameters_applied": len(conv.get("factors") or []) + 20,
        "factors": conv.get("factors"),
    }


def _insight_from_row(row: dict[str, Any], *, trade_date: str) -> dict[str, Any]:
    sym = str(row.get("symbol") or "")
    cs = row.get("conviction_score")
    return {
        "stance": row.get("conviction_band") or row.get("stance") or "neutral",
        "executive_summary": (
            f"Universe conviction scan {trade_date}: {sym} conviction {cs}/100 "
            f"(confidence {row.get('confidence')}), composite {row.get('composite_score')}, "
            f"grade {row.get('grade')}, stance {row.get('stance')}."
        ),
        "technical_read": (
            f"RSI {row.get('rsi_14')}, MACD hist {row.get('macd_hist')}, "
            f"supertrend {row.get('supertrend_dir')}, golden_cross {row.get('golden_cross')}, "
            f"pattern {row.get('pattern_bias')}."
        ),
        "conviction_pack": row,
        "what_changed_vs_prior": "Batch deep conviction scan for Nifty 500 RAG retrieval.",
        "not_advice_disclaimer": "Educational conviction memory — not investment advice.",
    }


def _feed_rag(rows: list[dict[str, Any]], *, trade_date: str, top_n_individual: int = 200) -> dict[str, Any]:
    stored_ids: list[str] = []
    ranked = sorted(rows, key=lambda r: float(r.get("conviction_score") or 0), reverse=True)

    for row in ranked[:top_n_individual]:
        sym = str(row.get("symbol") or "")
        if not sym:
            continue
        res = append_insight(
            symbol=sym,
            insight=_insight_from_row(row, trade_date=trade_date),
            provider="universe_scan",
            model="conviction_v1",
            as_of=trade_date,
            kind="universe_conviction",
            extra_metadata={
                "trade_date_ist": trade_date,
                "conviction_score": str(row.get("conviction_score") or ""),
                "composite_score": str(row.get("composite_score") or ""),
            },
        )
        stored_ids.append(res.get("id", ""))

    compact_all = ranked
    batch_count = 0
    for i in range(0, len(compact_all), RAG_BATCH_SIZE):
        chunk = compact_all[i : i + RAG_BATCH_SIZE]
        batch_count += 1
        summary = {
            "stance": "universe_scan",
            "executive_summary": (
                f"Universe conviction batch {batch_count} ({trade_date}): "
                f"{len(chunk)} symbols ranked by conviction score."
            ),
            "conviction_batch": chunk,
            "what_changed_vs_prior": "Batch conviction chunk for top-N retrieval.",
            "not_advice_disclaimer": "Educational — not investment advice.",
        }
        res = append_insight(
            symbol="NIFTY500",
            insight=summary,
            provider="universe_scan",
            model="conviction_batch",
            as_of=trade_date,
            kind="universe_conviction_batch",
            extra_metadata={"trade_date_ist": trade_date, "batch": str(batch_count)},
        )
        stored_ids.append(res.get("id", ""))

    top30 = ranked[:30]
    summary_insight = {
        "stance": "constructive" if top30 and float(top30[0].get("conviction_score") or 0) >= 65 else "neutral",
        "executive_summary": (
            f"Top conviction leaders {trade_date}: "
            + ", ".join(f"{r.get('symbol')} ({r.get('conviction_score')})" for r in top30[:10])
        ),
        "top_conviction_30": top30,
        "what_changed_vs_prior": "Daily top-30 conviction summary for agent queries.",
        "not_advice_disclaimer": "Educational — not investment advice.",
    }
    res = append_insight(
        symbol="MARKET",
        insight=summary_insight,
        provider="universe_scan",
        model="conviction_top30",
        as_of=trade_date,
        kind="universe_conviction_summary",
    )
    stored_ids.append(res.get("id", ""))

    return {"rag_ids": stored_ids, "individual": min(top_n_individual, len(ranked)), "batches": batch_count + 1}


def query_top_conviction(*, top_n: int = 30, min_score: Optional[float] = None) -> dict[str, Any]:
    data = load_deep_scan() or {}
    rows = list(data.get("rows") or [])
    if min_score is not None:
        rows = [r for r in rows if float(r.get("conviction_score") or 0) >= min_score]
    rows = rows[: max(1, min(top_n, 500))]
    data = load_deep_scan() or {}
    return {
        "ready": bool(rows),
        "trade_date_ist": data.get("trade_date_ist"),
        "last_run_at": data.get("run_at"),
        "total_scored": data.get("scored"),
        "count": len(rows),
        "rows": rows,
    }


def retrieve_conviction_context(
    query: str,
    *,
    top_k: int = 8,
    min_conviction: Optional[float] = None,
) -> list[dict[str, Any]]:
    """Pull conviction RAG memos — semantic search + local top-N fallback."""
    q_lower = (query or "").lower()
    want_top = any(w in q_lower for w in ("highest", "top", "best", "lead", "conviction", "30", "rank"))

    if want_top:
        cached = query_top_conviction(top_n=min(top_k, 30), min_score=min_conviction)
        if cached.get("rows"):
            return [
                {
                    "text": (
                        f"SYMBOL: {r.get('symbol')}\n"
                        f"CONVICTION: {r.get('conviction_score')} confidence {r.get('confidence')}\n"
                        f"COMPOSITE: {r.get('composite_score')} grade {r.get('grade')}\n"
                        f"STANCE: {r.get('stance')}\n"
                        f"FACTORS: {json.dumps(r.get('factors') or [])[:800]}"
                    ),
                    "metadata": {"kind": "universe_conviction", "symbol": r.get("symbol"), "source": "cache_rank"},
                    "distance": 0.0,
                }
                for r in cached["rows"]
            ]

    from genai_research import _safe_embed

    db = insights_collection()
    if db.count() == 0:
        return []
    try:
        where = {"kind": {"$in": ["universe_conviction", "universe_conviction_batch", "universe_conviction_summary"]}}
        result = db.query(
            query_embeddings=_safe_embed([query]),
            n_results=min(top_k, db.count()),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
    except Exception:
        result = db.query(
            query_embeddings=_safe_embed([query]),
            n_results=min(top_k, db.count()),
            include=["documents", "metadatas", "distances"],
        )
    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]
    out = []
    for doc, meta, dist in zip(docs, metas, dists):
        kind = (meta or {}).get("kind", "")
        if kind not in {"universe_conviction", "universe_conviction_batch", "universe_conviction_summary", ""}:
            continue
        if min_conviction is not None:
            try:
                if float((meta or {}).get("conviction_score") or 0) < min_conviction:
                    continue
            except (TypeError, ValueError):
                pass
        out.append({"text": doc, "metadata": meta or {}, "distance": dist})
    return out


def run_deep_universe_scan(
    *,
    force: bool = False,
    limit: int = 500,
    horizon: str = "1m",
    max_workers: int = 4,
    load_rows_fn: Optional[Callable[[str], list[dict[str, Any]]]] = None,
    rag_top_n: int = 200,
    batch_size: int = 50,
    batch_pause_seconds: float = 4.0,
    retry_rounds: int = 2,
    retry_pause_seconds: float = 45.0,
    provider: str = "yfinance",
    batch_strategy: str = "round_robin",
) -> dict[str, Any]:
    """Score full universe with conviction ensemble; persist + RAG."""
    trade_date = _ist_today()
    existing = load_deep_scan()
    if not force and existing and existing.get("trade_date_ist") == trade_date and (existing.get("scored") or 0) >= 400:
        return {"skipped": True, "reason": "already_ran_today", **deep_scan_status()}

    full_items: list[dict[str, Any]] = []
    screen_meta: dict[str, Any] = {}

    from routes.helpers import fetch_prices_light, rows_from_payload, warm_price_cache_batched
    from universe import universe_symbols

    symbols = universe_symbols(limit=limit)
    warm_stats = warm_price_cache_batched(
        symbols,
        force_refresh=force,
        chunk_size=batch_size,
        pause_seconds=batch_pause_seconds,
        batch_strategy=batch_strategy,
    )

    if load_rows_fn is None:
        def _load(sym: str) -> list[dict[str, Any]]:
            payload = fetch_prices_light(
                sym,
                force_refresh=force,
                provider=provider,
                retries=3,
                retry_delay=2.5,
            )
            rows = rows_from_payload(payload)
            if len(rows) < 30:
                raise ValueError("insufficient history")
            return rows

        load_rows_fn = _load

    result = screen_universe(
        load_rows=load_rows_fn,
        limit=limit,
        horizon=horizon,
        max_workers=max_workers,
        data_provider=provider,
        batch_size=batch_size,
        batch_pause_seconds=batch_pause_seconds,
        retry_rounds=retry_rounds,
        retry_pause_seconds=retry_pause_seconds,
        batch_strategy=batch_strategy,
    )
    full_items = list(result.get("results") or [])
    screen_meta = {
        "source": "batched_screen",
        "elapsed": result.get("elapsed_seconds"),
        "scored": result.get("scored"),
        "failed": result.get("failed"),
        "warm_cache": warm_stats,
        "batch_size": batch_size,
        "retry_rounds": retry_rounds,
    }

    if not full_items:
        return {"error": "No screener rows to score", "trade_date_ist": trade_date}

    rows_out: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    def work(item: dict[str, Any]) -> dict[str, Any]:
        conv = conviction_from_item(item)
        return _compact_conviction_row(item, conv)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(work, item): item for item in full_items}
        for future in as_completed(futures):
            item = futures[future]
            try:
                rows_out.append(future.result())
            except Exception as exc:
                errors.append({"symbol": str(item.get("symbol") or ""), "error": str(exc)[:120]})

    rows_out.sort(key=lambda r: float(r.get("conviction_score") or 0), reverse=True)
    rag_result = _feed_rag(rows_out, trade_date=trade_date, top_n_individual=rag_top_n)

    payload = {
        "run_at": _now(),
        "trade_date_ist": trade_date,
        "horizon": horizon,
        "scored": len(rows_out),
        "failed": len(errors),
        "screen_fetch_failed": screen_meta.get("failed"),
        "rows": rows_out,
        "top_30": rows_out[:30],
        "screen_meta": screen_meta,
        "rag_chunks": rag_result,
        "errors": errors[:40],
        "disclaimer": "Educational conviction scan — not investment advice.",
    }
    SCAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCAN_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
