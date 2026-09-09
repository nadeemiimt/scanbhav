"""Morning Nifty 500 batch scan → local cache + Chroma RAG for agent readiness."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from config import BASE_DIR
from genai_research import append_insight, insights_collection
from screener import load_cached_screen, screen_universe
from universe import universe_meta

SCAN_PATH = BASE_DIR / "data" / "trading" / "morning_scan.json"
RAG_BATCH_SIZE = 25


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ist_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=5, minutes=30)))


def _today_ist() -> str:
    return _ist_now().strftime("%Y-%m-%d")


def load_morning_scan() -> Optional[dict[str, Any]]:
    if not SCAN_PATH.exists():
        return None
    try:
        return json.loads(SCAN_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def morning_scan_status() -> dict[str, Any]:
    data = load_morning_scan() or {}
    return {
        "last_run_at": data.get("run_at"),
        "trade_date_ist": data.get("trade_date_ist"),
        "scored": data.get("scored"),
        "rag_chunks": data.get("rag_chunks"),
        "top_bullish": (data.get("top_bullish") or [])[:5],
        "ready": bool(data.get("rows")),
    }


def _compact_row(row: dict[str, Any]) -> dict[str, Any]:
    base = {
        "symbol": row.get("symbol"),
        "price": row.get("price"),
        "composite_score": row.get("composite_score"),
        "stance": row.get("stance"),
        "grade": row.get("grade"),
        "score": row.get("score"),
        "rsi_14": row.get("rsi_14"),
        "macd_hist": row.get("macd_hist"),
        "supertrend_dir": row.get("supertrend_dir"),
        "golden_cross": row.get("golden_cross"),
        "horizon_return_pct": row.get("horizon_return_pct"),
        "bucket": row.get("bucket"),
        "quality_score": row.get("quality_score"),
        "quality_ok": row.get("quality_ok"),
        "pattern_bias": row.get("pattern_bias"),
        "news_score": row.get("news_score"),
        "news_headline_count": row.get("news_headline_count"),
        "pattern_score": row.get("pattern_score"),
        "pattern_ids": row.get("pattern_ids"),
    }
    return base


def _insight_from_row(row: dict[str, Any], *, trade_date: str) -> dict[str, Any]:
    sym = str(row.get("symbol") or "")
    composite = row.get("composite_score")
    stance = row.get("stance") or "neutral"
    return {
        "stance": stance,
        "executive_summary": (
            f"Morning scan {trade_date}: {sym} composite {composite}, stance {stance}, "
            f"price {row.get('price')}, RSI {row.get('rsi_14')}, bucket {row.get('bucket')}."
        ),
        "technical_read": (
            f"MACD hist {row.get('macd_hist')}, supertrend {row.get('supertrend_dir')}, "
            f"golden_cross {row.get('golden_cross')}, horizon ret {row.get('horizon_return_pct')}%."
        ),
        "morning_scan_row": _compact_row(row),
        "what_changed_vs_prior": "Pre-market Nifty 500 technical screen for agent RAG.",
        "not_advice_disclaimer": "Educational morning scan memory — not investment advice.",
    }


def _feed_rag(rows: list[dict[str, Any]], *, trade_date: str, top_n_individual: int = 60) -> dict[str, Any]:
    """Write morning scan into Chroma — leaders individually + batched rest."""
    stored_ids: list[str] = []
    bullish = [
        r for r in rows
        if str(r.get("stance") or "").lower() in {"favorable", "strong_favorable", "bullish", "constructive"}
    ]
    bullish.sort(key=lambda x: float(x.get("composite_score") or 0), reverse=True)

    for row in bullish[:top_n_individual]:
        sym = str(row.get("symbol") or "")
        if not sym:
            continue
        res = append_insight(
            symbol=sym,
            insight=_insight_from_row(row, trade_date=trade_date),
            provider="morning_scan",
            model="nifty500_batch",
            as_of=trade_date,
            kind="morning_scan",
            extra_metadata={"trade_date_ist": trade_date, "composite": str(row.get("composite_score") or "")},
        )
        stored_ids.append(res.get("id", ""))

    # Batch remaining symbols into chunk documents for RAG retrieval
    compact_all = [_compact_row(r) for r in rows]
    batch_count = 0
    for i in range(0, len(compact_all), RAG_BATCH_SIZE):
        chunk = compact_all[i : i + RAG_BATCH_SIZE]
        batch_count += 1
        summary = {
            "stance": "market_scan",
            "executive_summary": (
                f"Morning Nifty 500 batch {batch_count} ({trade_date}): "
                f"{len(chunk)} symbols with composite/stance/technicals precomputed."
            ),
            "morning_scan_batch": chunk,
            "what_changed_vs_prior": "Batch morning scan chunk for agent retrieval.",
            "not_advice_disclaimer": "Educational — not investment advice.",
        }
        res = append_insight(
            symbol="NIFTY500",
            insight=summary,
            provider="morning_scan",
            model="nifty500_batch",
            as_of=trade_date,
            kind="morning_scan_batch",
            extra_metadata={"trade_date_ist": trade_date, "batch": str(batch_count)},
        )
        stored_ids.append(res.get("id", ""))

    # Market summary for self-learning context
    top5 = bullish[:5]
    summary_insight = {
        "stance": "constructive" if top5 else "neutral",
        "executive_summary": (
            f"Morning market map {trade_date}: {len(rows)} Nifty 500 names scored. "
            f"Top bullish: {', '.join(str(r.get('symbol')) for r in top5)}."
        ),
        "morning_scan_summary": {
            "trade_date_ist": trade_date,
            "scored": len(rows),
            "bullish_count": len(bullish),
            "top_bullish": [_compact_row(r) for r in top5],
        },
        "what_changed_vs_prior": "Daily pre-market summary for agent desk and calibration.",
        "not_advice_disclaimer": "Educational — not investment advice.",
    }
    res = append_insight(
        symbol="MARKET",
        insight=summary_insight,
        provider="morning_scan",
        model="nifty500_summary",
        as_of=trade_date,
        kind="morning_scan_summary",
    )
    stored_ids.append(res.get("id", ""))

    return {"rag_ids": stored_ids, "individual": min(top_n_individual, len(bullish)), "batches": batch_count + 1}


def retrieve_morning_scan_context(
    query: str,
    *,
    symbol: Optional[str] = None,
    top_k: int = 6,
) -> list[dict[str, Any]]:
    """Pull morning-scan RAG memos for agent desk."""
    from genai_research import _safe_embed

    db = insights_collection()
    if db.count() == 0:
        return []
    q = query if symbol else query
    if symbol:
        q = f"{symbol} {query} morning scan composite stance"
    try:
        where = {"kind": {"$in": ["morning_scan", "morning_scan_batch", "morning_scan_summary"]}}
        if symbol:
            result = db.query(
                query_embeddings=_safe_embed([q]),
                n_results=min(top_k, db.count()),
                where={"symbol": symbol.upper()},
                include=["documents", "metadatas", "distances"],
            )
        else:
            result = db.query(
                query_embeddings=_safe_embed([q]),
                n_results=min(top_k, db.count()),
                where=where,
                include=["documents", "metadatas", "distances"],
            )
    except Exception:
        result = db.query(
            query_embeddings=_safe_embed([q]),
            n_results=min(top_k, db.count()),
            include=["documents", "metadatas", "distances"],
        )
    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]
    out = []
    for doc, meta, dist in zip(docs, metas, dists):
        kind = (meta or {}).get("kind", "")
        if kind not in {"morning_scan", "morning_scan_batch", "morning_scan_summary", ""}:
            continue
        out.append({"text": doc, "metadata": meta or {}, "distance": dist})
    return out


def rows_from_morning_scan(symbols: Optional[list[str]] = None) -> list[dict[str, Any]]:
    """Fast lookup rows from latest morning scan (or screen cache fallback)."""
    data = load_morning_scan()
    rows = list(data.get("rows") or []) if data else []
    if not rows:
        cached = load_cached_screen()
        rows = list((cached or {}).get("top") or [])
    if symbols:
        want = {s.upper() for s in symbols}
        rows = [r for r in rows if str(r.get("symbol", "")).upper() in want]
    return rows


def should_run_morning_scan(cfg: Optional[dict[str, Any]] = None) -> bool:
    from trading.config_store import load_trading_config

    c = cfg or load_trading_config()
    ap = c.get("autopilot") or {}
    if not ap.get("morning_scan_enabled", True):
        return False
    hour = int(ap.get("morning_scan_hour_ist") or 9)
    minute = int(ap.get("morning_scan_minute_ist") or 5)
    now = _ist_now()
    if now.weekday() >= 5:
        return False
    data = load_morning_scan()
    if data and data.get("trade_date_ist") == _today_ist():
        return False
    mins = now.hour * 60 + now.minute
    target = hour * 60 + minute
    return target <= mins <= target + 45


def run_morning_scan(
    *,
    force: bool = False,
    horizon: str = "1d",
    load_rows_fn: Optional[Callable[[str], list[dict[str, Any]]]] = None,
) -> dict[str, Any]:
    """
    Score full Nifty 500, persist locally, feed Chroma RAG for agent/autopilot.
    """
    trade_date = _today_ist()
    existing = load_morning_scan()
    if not force and existing and existing.get("trade_date_ist") == trade_date:
        return {"skipped": True, "reason": "already_ran_today", **morning_scan_status()}

    rows_slim: list[dict[str, Any]] = []
    screen_meta: dict[str, Any] = {}

    if load_rows_fn is None:
        cached = load_cached_screen()
        if cached and cached.get("scored", 0) >= 400:
            rows_slim = list(cached.get("top") or [])
            screen_meta = {"source": "screen_cache", "as_of": (cached.get("meta") or {}).get("as_of")}
        else:
            from routes.helpers import fetch_prices_light, rows_from_payload

            def _load(sym: str) -> list[dict[str, Any]]:
                payload = fetch_prices_light(sym, force_refresh=False, provider="auto")
                rows = rows_from_payload(payload)
                if len(rows) < 30:
                    raise ValueError("insufficient history")
                return rows

            load_rows_fn = _load

    if not rows_slim and load_rows_fn:
        result = screen_universe(load_rows=load_rows_fn, limit=500, horizon=horizon, max_workers=8)
        rows_slim = [_compact_row(r) if "composite_score" in r else _compact_row(_slim_from_full(r)) for r in result.get("top") or []]
        if not rows_slim:
            rows_slim = [_slim_from_full(r) for r in result.get("results") or []]
        screen_meta = {"source": "live_screen", "elapsed": result.get("elapsed_seconds")}

    if not rows_slim:
        return {"error": "No screen rows produced", "trade_date_ist": trade_date}

    rows_slim.sort(key=lambda x: float(x.get("composite_score") or 0), reverse=True)

    intel_meta: dict[str, Any] = {}
    try:
        from trading.intraday_patterns import batch_attach_pattern_scores

        rows_slim = batch_attach_pattern_scores(rows_slim)
        intel_meta = {"patterns_attached": True}
    except Exception as exc:
        intel_meta = {"intel_error": str(exc)[:120]}

    bullish = [
        r for r in rows_slim
        if str(r.get("stance") or "").lower() in {"favorable", "strong_favorable", "bullish", "constructive"}
    ]

    from trading.config_store import load_trading_config
    ap = (load_trading_config().get("autopilot") or {})
    quant_meta: dict[str, Any] = {}
    if ap.get("quant_layer_enabled", True):
        try:
            from quant_layer.pipeline import ensure_quant_shortlist

            if load_rows_fn is None:
                from routes.helpers import fetch_prices_light, rows_from_payload

                def _load(sym: str) -> list[dict[str, Any]]:
                    payload = fetch_prices_light(sym, force_refresh=False, provider="auto")
                    rows = rows_from_payload(payload)
                    if len(rows) < 30:
                        raise ValueError("insufficient history")
                    return rows

                load_rows_fn = _load
            quant_meta = ensure_quant_shortlist(
                load_rows=load_rows_fn,
                limit=500,
                max_shortlist=int(ap.get("quant_shortlist_max") or 30),
            )
        except Exception as exc:
            quant_meta = {"quant_scan_error": str(exc)[:120]}
        rows_slim = _merge_quant_shortlist(rows_slim)
    rag_result = _feed_rag(rows_slim, trade_date=trade_date, top_n_individual=int(ap.get("morning_scan_rag_top") or 60))

    payload = {
        "run_at": _now(),
        "trade_date_ist": trade_date,
        "horizon": horizon,
        "scored": len(rows_slim),
        "bullish_count": len(bullish),
        "top_bullish": bullish[:20],
        "rows": rows_slim,
        "screen_meta": screen_meta,
        "universe_meta": universe_meta(),
        "rag_chunks": rag_result,
        "intel_meta": intel_meta,
        "quant_meta": quant_meta,
        "learning": {
            "note": "Agent picks vs outcomes feed scoreboard; re-run calibration after closes.",
            "pick_source": "morning_scan_v1",
        },
    }
    SCAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCAN_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def _merge_quant_shortlist(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach Layer-1 trigger metadata from cached quant shortlist when available."""
    try:
        from quant_layer.pipeline import load_cached_shortlist

        cached = load_cached_shortlist()
        if not cached:
            return rows
        by_sym = {str(x.get("symbol") or "").upper(): x for x in (cached.get("shortlist") or [])}
        out: list[dict[str, Any]] = []
        for row in rows:
            sym = str(row.get("symbol") or "").upper()
            hit = by_sym.get(sym)
            if not hit:
                out.append(row)
                continue
            merged = dict(row)
            merged["quant_triggers"] = hit.get("triggers_fired") or []
            merged["quant_trigger_count"] = hit.get("trigger_count") or 0
            merged["quant_regime_hint"] = hit.get("regime_hint")
            merged["quant_triggered"] = True
            merged["quant_trigger_boost"] = min(15.0, 3.0 * float(hit.get("trigger_count") or 0))
            out.append(merged)
        return out
    except Exception:
        return rows


def _slim_from_full(item: dict[str, Any]) -> dict[str, Any]:
    ratings = item.get("ratings") or {}
    tech = item.get("technicals") or {}
    mom = tech.get("momentum") or {}
    tr = tech.get("trend") or {}
    ma = tech.get("moving_averages") or {}
    h = (ratings.get("horizons") or {}).get("1d") or {}
    return {
        "symbol": item.get("symbol"),
        "price": item.get("price"),
        "composite_score": ratings.get("composite_score"),
        "stance": ratings.get("composite_stance"),
        "grade": ratings.get("composite_grade"),
        "score": item.get("rank_score"),
        "rsi_14": mom.get("rsi_14"),
        "macd_hist": mom.get("macd_hist"),
        "supertrend_dir": tr.get("supertrend_dir"),
        "golden_cross": ma.get("golden_cross"),
        "horizon_return_pct": h.get("horizon_return_pct"),
        "bucket": item.get("bucket"),
    }
