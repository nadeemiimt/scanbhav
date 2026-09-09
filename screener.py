"""Batch technical screener for the Nifty 500 universe (Large / Mid / Small)."""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from config import BASE_DIR
from horizon_rank import rate_all_horizons
from technicals import compute_technicals
from universe import CAP_SECTIONS, HORIZONS, bucket_for_symbol, round_robin_batches, round_robin_batches_from_symbols, universe_meta, universe_symbols

SCREEN_CACHE = BASE_DIR / "data" / "screen_cache" / "last_screen.json"


def analyze_symbol_rows(symbol: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    tech = compute_technicals(rows)
    ratings = rate_all_horizons(tech)
    try:
        from analysis.bundle import build_extended_analysis
        extended = build_extended_analysis(
            symbol=symbol,
            rows=rows,
            tech=tech,
            quote=None,
            news=None,
            ratings=ratings,
            include_slow=False,
            screen_mode=True,
        )
        ratings = extended.get("ratings_blended") or ratings
    except Exception:
        extended = None
    return {
        "symbol": symbol,
        "bucket": bucket_for_symbol(symbol) or "large",
        "price": tech["price"],
        "as_of": tech["as_of"],
        "bars": tech["bars"],
        "technicals": tech,
        "ratings": ratings,
        "extended": extended,
    }


def _slim_row(item: dict[str, Any], horizon: str) -> dict[str, Any]:
    horizons = ((item.get("ratings") or {}).get("horizons") or {})
    rating = horizons.get(horizon) or {}
    ext = item.get("extended") or {}
    fund = ext.get("fundamentals") or {}
    flags = fund.get("fundamental_screener_flags") or {}
    qs = (fund.get("quality_scores") or {}).get("composite_quality")
    pat = ext.get("patterns") or {}
    plan_fields: dict[str, Any] = {}
    levels = (item["technicals"].get("levels") or {})
    try:
        from analysis.plan_session import build_session_trade_plan, session_plan_target_day, slim_session_fields

        plan = build_session_trade_plan(tech=item["technicals"], ratings=item.get("ratings"))
        plan_fields = slim_session_fields(plan)
        plan_fields["plan_target_day"] = plan.get("target_day") or session_plan_target_day()
    except Exception:
        plan_fields = {}
    return {
        "rank": item.get("rank"),
        "section_rank": item.get("section_rank"),
        "bucket": item.get("bucket"),
        "symbol": item["symbol"],
        "price": item["price"],
        "as_of": item["as_of"],
        "score": item.get("rank_score"),
        "grade": rating.get("grade"),
        "stance": rating.get("stance"),
        "composite_score": (item.get("ratings") or {}).get("composite_score"),
        "horizon_return_pct": rating.get("horizon_return_pct"),
        "rsi_14": item["technicals"]["momentum"]["rsi_14"],
        "atr_14": (item["technicals"].get("volatility") or {}).get("atr_14"),
        "atr_pct": (item["technicals"].get("volatility") or {}).get("atr_pct"),
        "macd_hist": item["technicals"]["momentum"]["macd_hist"],
        "adx_14": item["technicals"]["trend"]["adx_14"],
        "supertrend_dir": item["technicals"]["trend"]["supertrend_dir"],
        "golden_cross": item["technicals"]["moving_averages"]["golden_cross"],
        "price_vs_sma_200_pct": item["technicals"]["moving_averages"]["price_vs_sma_200_pct"],
        "quality_score": qs,
        "quality_ok": flags.get("quality_ok"),
        "debt_ok": flags.get("debt_ok"),
        "growth_ok": flags.get("growth_ok"),
        "pattern_bias": pat.get("composite_bias"),
        "pivot_s1": levels.get("s1"),
        "pivot_r1": levels.get("r1"),
        "pivot_r2": levels.get("r2"),
        "pivot_pivot": levels.get("pivot"),
        **plan_fields,
    }


def _sort_key(item: dict[str, Any], horizon: str) -> float:
    horizons = ((item.get("ratings") or {}).get("horizons") or {})
    rating = horizons.get(horizon) or {}
    return float(rating.get("score") or (item.get("ratings") or {}).get("composite_score") or 0)


def screen_universe(
    *,
    load_rows: Callable[[str], list[dict[str, Any]]],
    limit: int = 500,
    max_workers: int = 8,
    horizon: str = "1m",
    bucket: str | None = None,
    data_provider: str = "auto",
    batch_size: int = 50,
    batch_pause_seconds: float = 4.0,
    score_batch_pause_seconds: float | None = None,
    retry_rounds: int = 2,
    retry_pause_seconds: float = 45.0,
    batch_strategy: str = "round_robin",
    on_progress: Optional[Callable[[int, int], None]] = None,
    initial_results: Optional[list[dict[str, Any]]] = None,
    initial_error_map: Optional[dict[str, str]] = None,
    on_checkpoint: Optional[Callable[[list[dict[str, Any]], dict[str, str]], None]] = None,
) -> dict[str, Any]:
    symbols = universe_symbols(limit=limit, bucket=bucket)
    results: list[dict[str, Any]] = list(initial_results or [])
    error_map: dict[str, str] = dict(initial_error_map or {})
    started = time.time()
    succeeded: set[str] = {str(r.get("symbol") or "").upper() for r in results if r.get("symbol")}
    for sym in list(error_map):
        if sym.upper() in succeeded:
            error_map.pop(sym, None)

    def work(symbol: str) -> dict[str, Any]:
        rows = load_rows(symbol)
        return analyze_symbol_rows(symbol, rows)

    def run_batch(sym_list: list[str]) -> None:
        if not sym_list:
            return
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(work, symbol): symbol for symbol in sym_list}
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    results.append(future.result())
                    succeeded.add(symbol.upper())
                    error_map.pop(symbol, None)
                except Exception as exc:
                    if symbol.upper() not in succeeded:
                        error_map[symbol] = str(exc)
                if on_progress:
                    on_progress(len(results), len(error_map))
                if on_checkpoint:
                    on_checkpoint(results, error_map)

    eff_batch = max(1, batch_size) if batch_size > 0 else len(symbols)
    remaining = [s for s in symbols if s.upper() not in succeeded]
    if batch_strategy == "round_robin":
        batches = round_robin_batches_from_symbols(remaining, batch_size=eff_batch) if remaining else []
    else:
        batches = [remaining[i : i + eff_batch] for i in range(0, len(remaining), eff_batch)]

    eff_score_pause = batch_pause_seconds if score_batch_pause_seconds is None else score_batch_pause_seconds

    for i, chunk in enumerate(batches):
        run_batch(chunk)
        if i + 1 < len(batches) and eff_score_pause > 0:
            time.sleep(eff_score_pause)

    for _round in range(max(0, retry_rounds)):
        failed = [s for s in error_map if s not in succeeded]
        if not failed:
            break
        if retry_pause_seconds > 0:
            time.sleep(retry_pause_seconds)
        retry_batches = (
            round_robin_batches_from_symbols(failed, batch_size=eff_batch)
            if batch_strategy == "round_robin"
            else [failed[i : i + eff_batch] for i in range(0, len(failed), eff_batch)]
        )
        for j, chunk in enumerate(retry_batches):
            run_batch(chunk)
            if j + 1 < len(retry_batches) and eff_score_pause > 0:
                time.sleep(eff_score_pause)

    errors = [{"symbol": sym, "error": msg} for sym, msg in error_map.items()]

    def _error_category(msg: str) -> str:
        lower = str(msg).lower()
        if "503" in lower or "service unavailable" in lower:
            return "nse_rate_limit"
        if "429" in lower or "too many" in lower or "rate limit" in lower:
            return "yahoo_rate_limit"
        if "insufficient history" in lower:
            return "insufficient_history"
        if "no yahoo" in lower or "no data" in lower:
            return "no_data"
        if "timeout" in lower or "timed out" in lower:
            return "timeout"
        return "other"

    error_summary: dict[str, int] = {}
    for item in errors:
        cat = _error_category(item.get("error") or "")
        error_summary[cat] = error_summary.get(cat, 0) + 1

    overall = sorted(results, key=lambda item: _sort_key(item, horizon), reverse=True)
    for index, item in enumerate(overall, start=1):
        item["rank"] = index
        item["rank_horizon"] = horizon
        item["rank_score"] = _sort_key(item, horizon)

    sections: dict[str, Any] = {}
    for section in CAP_SECTIONS:
        key = section["id"]
        bucket_rows = [r for r in overall if r.get("bucket") == key]
        bucket_rows = sorted(bucket_rows, key=lambda item: _sort_key(item, horizon), reverse=True)
        for index, item in enumerate(bucket_rows, start=1):
            item["section_rank"] = index
        sections[key] = {
            **section,
            "count": len(bucket_rows),
            "scored": len(bucket_rows),
            "top": [_slim_row(item, horizon) for item in bucket_rows],
        }

    meta = universe_meta()
    failed_symbols = [e["symbol"] for e in errors if e.get("symbol")]
    payload = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "universe_size": len(symbols),
        "scored": len(overall),
        "failed": len(errors),
        "failed_symbols": failed_symbols[:500],
        "error_summary": error_summary,
        "horizon": horizon,
        "data_provider": data_provider,
        "horizons": HORIZONS,
        "elapsed_seconds": round(time.time() - started, 2),
        "batch_size": eff_batch,
        "batch_strategy": batch_strategy,
        "batch_pause_seconds": batch_pause_seconds,
        "retry_rounds": retry_rounds,
        "meta": meta,
        "sections": sections,
        "top": [_slim_row(item, horizon) for item in overall],
        "results": overall,
        "errors": errors[:200],
        "disclaimer": (
            "Educational Nifty 500 technical screen across SMA/EMA/RSI/MACD/Bollinger/"
            "ATR/Stochastic/ADX/Supertrend/volume and horizon returns, ranked within "
            "Large / Mid / Small sections. Not investment advice."
        ),
    }
    SCREEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    slim = {
        **payload,
        "results": [],
        "sections": {
            key: {**val, "top": val["top"]}
            for key, val in sections.items()
        },
    }
    SCREEN_CACHE.write_text(json.dumps(slim, indent=2), encoding="utf-8")
    try:
        from trading.json_cache import invalidate_json_cache
        invalidate_json_cache(SCREEN_CACHE)
    except Exception:
        pass
    try:
        from screen_page_cache import invalidate_screen_page_cache, warm_default_screen_page

        invalidate_screen_page_cache()
        meta = universe_meta()
        expected = meta.get("total") or 500
        stale = (payload.get("universe_size") or 0) < expected or not payload.get("sections")
        warm_default_screen_page(payload, stale=stale, expected=expected)
    except Exception:
        pass
    try:
        from routes.screen_checkpoint import clear_checkpoint
        clear_checkpoint()
    except Exception:
        pass
    return payload


def load_cached_screen() -> Optional[dict[str, Any]]:
    from trading.json_cache import load_json_cached

    if not SCREEN_CACHE.exists():
        return None
    cached = load_json_cached(SCREEN_CACHE, default={})
    if not cached:
        return None
    if not cached.get("run_at"):
        try:
            mtime = SCREEN_CACHE.stat().st_mtime
            cached["run_at"] = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        except OSError:
            meta_as_of = (cached.get("meta") or {}).get("as_of")
            if meta_as_of:
                cached["run_at"] = f"{meta_as_of}T00:00:00+00:00"
    if not cached.get("failed_symbols") and cached.get("errors"):
        cached["failed_symbols"] = [
            str(e.get("symbol") or "").upper()
            for e in cached["errors"]
            if e.get("symbol")
        ]
    return cached
