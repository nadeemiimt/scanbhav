"""Technical analysis & screener routes."""
from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Query

from analysis.bundle import build_extended_analysis
from deep_dossier import build_deep_dossier
from fetch_stock_data import yahoo_symbol
from horizon_rank import rate_all_horizons
from indicator_guide import INDICATOR_GUIDE, build_reference
from investors import investor_perspectives
from news_catalysts import gather_news_catalysts
from peers import fetch_peers
from routes.helpers import (
    _cache_is_fresh,
    fetch_prices,
    fetch_prices_light,
    raw_path,
    response_data,
    rows_from_payload,
    warm_price_cache_batched,
)
from routes.schemas import TaAnalyzeRequest, TaScreenRequest
from routes.screen_job import screen_job_status, start_screen_job
from screener import load_cached_screen, screen_universe
from screen_contract import (
    CONTRACT_VERSION,
    SCREEN_DATA_PROVIDERS,
    ScreenPageContract,
    ScreenPageQueryContract,
    ScreenProvidersContract,
    SortDir,
    build_screen_page,
)
from desk_tools import event_watch, position_size, relative_strength, sector_heat_from_screen, session_levels
from technicals import compute_technicals
from universe import HORIZONS, universe_meta, universe_symbols
from universe_refresh import ensure_universe_fresh, refresh_meta

router = APIRouter(tags=["ta"])


def _benchmark_relative_strength(tech_returns: dict[str, Any]) -> dict[str, Any]:
    """NIFTY RS from on-disk benchmark cache only (no live fetch during analyze)."""
    for bench_sym in ("^NSEI", "NIFTY.NSE", "NIFTYBEES.NSE"):
        try:
            bench_path = raw_path(bench_sym)
            if not bench_path.exists():
                continue
            bench_payload = json.loads(bench_path.read_text(encoding="utf-8"))
            bench_tech = compute_technicals(rows_from_payload(bench_payload))
            return relative_strength(
                tech_returns,
                bench_tech.get("returns_pct") or {},
                bench_label="NIFTY",
            )
        except Exception:
            continue
    return {"benchmark": "NIFTY", "horizons": {}, "headline": None, "status": "cache_miss"}


@router.get("/api/ta/horizons")
def ta_horizons() -> dict[str, Any]:
    return {"horizons": HORIZONS}


@router.get("/api/ta/reference")
def ta_reference() -> dict[str, Any]:
    """Full indicator catalog + desk section guide for the Method / Reference page."""
    return build_reference()


@router.get("/api/ta/universe")
def ta_universe(
    limit: int = Query(500, ge=10, le=520),
    bucket: Optional[Literal["large", "mid", "small"]] = Query(None),
    check_fresh: bool = Query(False, description="Refresh NSE lists if not checked today"),
) -> dict[str, Any]:
    refresh_status = ensure_universe_fresh(force=False) if check_fresh else None
    symbols = universe_symbols(limit, bucket=bucket)
    return {
        "count": len(symbols),
        "symbols": symbols,
        "meta": universe_meta(),
        "bucket": bucket,
        "refresh": refresh_status,
    }


@router.post("/api/ta/universe/refresh")
def ta_universe_refresh(force: bool = Query(False)) -> dict[str, Any]:
    """Download NSE constituent CSVs (once per day unless force=true)."""
    return ensure_universe_fresh(force=force)


@router.get("/api/ta/universe/status")
def ta_universe_status() -> dict[str, Any]:
    return {"meta": universe_meta(), "refresh": refresh_meta()}


@router.post("/api/ta/analyze")
def ta_analyze(request: TaAnalyzeRequest) -> dict[str, Any]:
    """Full technical analysis + ratings across all horizons for one stock."""
    try:
        payload = fetch_prices(request.symbol, request.provider, force_refresh=request.force_refresh)
        rows = rows_from_payload(payload)
        tech = compute_technicals(rows)
        ratings = rate_all_horizons(tech)
        quote = response_data(payload, cached=(not request.force_refresh) and _cache_is_fresh(raw_path(request.symbol)))
        fundamentals = dict(quote.get("fundamentals") or {})
        company = quote.get("company") or {}
        # Normalize field names for investor personas (Yahoo-style + our statement ratios).
        investor_fundamentals = {
            **fundamentals,
            "debtToEquity": (
                (fundamentals.get("debt_to_equity") * 100)
                if isinstance(fundamentals.get("debt_to_equity"), (int, float))
                else company.get("debt_to_equity")
            ),
            "trailingPE": company.get("trailing_pe") or company.get("pe_ratio") or fundamentals.get("trailingPE"),
            "forwardPE": company.get("forward_pe"),
            "returnOnEquity": (
                (fundamentals.get("roe_pct") / 100.0)
                if isinstance(fundamentals.get("roe_pct"), (int, float))
                else company.get("return_on_equity")
            ),
            "profitMargins": (
                (fundamentals.get("net_margin_pct") / 100.0)
                if isinstance(fundamentals.get("net_margin_pct"), (int, float))
                else company.get("profit_margins")
            ),
            "operatingMargins": (
                (fundamentals.get("operating_margin_pct") / 100.0)
                if isinstance(fundamentals.get("operating_margin_pct"), (int, float))
                else None
            ),
            "revenueGrowth": (
                (fundamentals.get("revenue_growth_yoy_pct") / 100.0)
                if isinstance(fundamentals.get("revenue_growth_yoy_pct"), (int, float))
                else company.get("revenue_growth")
            ),
            "earningsGrowth": company.get("earnings_growth"),
            "pegRatio": company.get("peg_ratio"),
            "priceToBook": company.get("price_to_book"),
            "sector": company.get("sector"),
            "industry": company.get("industry"),
        }
        investors = investor_perspectives(tech, investor_fundamentals)
        cache_fresh = (not request.force_refresh) and _cache_is_fresh(raw_path(request.symbol))
        existing_news = quote.get("news") or []
        skip_rss = cache_fresh and len(existing_news) >= 4

        def _load_news() -> dict[str, Any]:
            try:
                return gather_news_catalysts(
                    request.symbol,
                    company_name=company.get("name"),
                    sector=company.get("sector"),
                    industry=company.get("industry"),
                    existing_news=existing_news,
                    limit=10,
                    skip_rss=skip_rss,
                )
            except Exception:
                return {"headline_count": 0, "high_impact_count": 0, "tag_counts": {}, "headlines": []}

        def _load_peers() -> list[dict[str, Any]]:
            try:
                return fetch_peers(yahoo_symbol(request.symbol), company.get("industry"))
            except Exception:
                return []

        with ThreadPoolExecutor(max_workers=3) as pool:
            f_news = pool.submit(_load_news)
            f_peers = pool.submit(_load_peers) if not quote.get("peers") else None
            f_rs = pool.submit(_benchmark_relative_strength, tech.get("returns_pct") or {})
            news = f_news.result()
            if f_peers is not None:
                quote["peers"] = f_peers.result()
            rs = f_rs.result()
        extended = build_extended_analysis(
            symbol=request.symbol,
            rows=rows,
            tech=tech,
            quote=quote,
            news=news,
            ratings=ratings,
            include_slow=True,
            fast_social=True,
        )
        ratings = extended.get("ratings_blended") or ratings
        dossier = build_deep_dossier(
            symbol=request.symbol,
            technicals=tech,
            ratings=ratings,
            quote=quote,
            indicator_guide=INDICATOR_GUIDE,
            news=news,
            extended=extended,
        )
        events = event_watch(news, dossier)
        sizing = None
        try:
            sizing = position_size(
                price=float(tech.get("price") or 0),
                atr=(tech.get("volatility") or {}).get("atr_14"),
                capital=100_000.0,
                risk_pct=1.0,
            )
        except Exception:
            sizing = None
        levels_pack = session_levels((tech.get("charts") or {}).get("candles") or [])
        plan_15d = None
        plan_session = None
        plan_7d = None
        try:
            from analysis.plan_15d import build_15d_trade_plan
            from analysis.plan_7d import build_7d_swing_summary
            from analysis.plan_session import build_session_trade_plan

            with ThreadPoolExecutor(max_workers=2) as pool:
                f_15 = pool.submit(build_15d_trade_plan, tech=tech, ratings=ratings)
                f_sess = pool.submit(build_session_trade_plan, tech=tech, ratings=ratings)
                plan_15d = f_15.result()
                plan_session = f_sess.result()
            plan_7d = build_7d_swing_summary(
                symbol=request.symbol,
                tech=tech,
                ratings=ratings,
                plan_15d=plan_15d,
                news=news,
            )
        except Exception:
            plan_15d = None
            plan_session = None
            plan_7d = None
        return {
            "symbol": request.symbol.upper(),
            "quote": quote,
            "technicals": tech,
            "ratings": ratings,
            "extended": extended,
            "investors": investors,
            "dossier": dossier,
            "news": news,
            "relative_strength": rs,
            "event_watch": events,
            "session_levels": levels_pack,
            "position_size_hint": sizing,
            "plan_15d": plan_15d,
            "plan_7d": plan_7d,
            "plan_session": plan_session,
            "indicator_guide": INDICATOR_GUIDE,
            "indicators_used": [
                "SMA 20/50/100/200", "EMA 9/12/21/26/50/200", "RSI 7/14", "MACD 12/26/9",
                "Stochastic 14/3/3", "CCI 20", "Williams %R", "ROC 12", "MFI 14",
                "Bollinger 20,2", "ATR 14", "ADX 14", "Supertrend 10,3",
                "OBV", "Relative Volume", "Pivot R1/S1/R2/S2", "52-week levels", "Horizon returns",
                "VWAP (chart window)", "Relative strength vs NIFTY", "Session levels / volume profile",
                "Ichimoku cloud", "Fibonacci retracements", "Keltner/Donchian", "Parabolic SAR",
                "CMF / A-D line", "Aroon / TSI / Hull MA", "RSI-MACD divergence", "Intraday 1h TA",
                "Candlestick & chart patterns", "Piotroski/Altman/Graham", "India shareholding",
                "Options PCR/OI", "FII/DII flows", "Macro FX/commodities", "Market regime",
            ],
        }
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Technical analysis failed: {exc}") from exc


@router.get("/api/ta/screen/status")
async def ta_screen_job_status() -> dict[str, Any]:
    """Background screen job progress (API stays responsive while scan runs)."""
    return screen_job_status()


def _run_sync_screen(request: TaScreenRequest) -> dict[str, Any]:
    ensure_universe_fresh(force=False)
    eff_limit = request.limit
    if request.bucket:
        eff_limit = {"large": 100, "mid": 150, "small": 250}.get(request.bucket, request.limit)
    elif eff_limit < 500:
        eff_limit = 500
    symbols = universe_symbols(eff_limit, bucket=request.bucket)
    warm_stats = warm_price_cache_batched(
        symbols,
        force_refresh=request.force_refresh,
        chunk_size=request.batch_size,
        pause_seconds=request.batch_pause_seconds,
        batch_strategy=request.batch_strategy,
    )

    def load_rows(symbol: str) -> list[dict[str, Any]]:
        if request.provider == "auto":
            bulk_provider = "auto"
            allow_nse = True
        else:
            bulk_provider = "yfinance" if request.provider == "yfinance" else request.provider
            allow_nse = request.provider == "nse"
        payload = fetch_prices_light(
            symbol,
            force_refresh=request.force_refresh,
            provider=bulk_provider,
            allow_nse_fallback=allow_nse,
            retries=3,
            retry_delay=2.5,
        )
        rows = rows_from_payload(payload)
        if len(rows) < 30:
            raise ValueError("insufficient history")
        return rows

    score_pause = 0.0 if warm_stats.get("requested", 0) == 0 else request.batch_pause_seconds
    result = screen_universe(
        load_rows=load_rows,
        limit=eff_limit,
        max_workers=request.max_workers,
        horizon=request.horizon,
        bucket=request.bucket,
        data_provider=request.provider,
        batch_size=request.batch_size,
        batch_pause_seconds=request.batch_pause_seconds,
        score_batch_pause_seconds=score_pause,
        retry_rounds=request.retry_rounds,
        retry_pause_seconds=request.retry_pause_seconds,
        batch_strategy=request.batch_strategy,
    )
    result["warm_cache"] = warm_stats
    result["contract_version"] = CONTRACT_VERSION
    return result


@router.post("/api/ta/screen")
async def ta_screen(
    request: TaScreenRequest,
    background: bool = Query(True),
    mode: Literal["fresh", "resume", "restart"] = Query("fresh"),
) -> dict[str, Any]:
    """Score Nifty 500 stocks — runs in background by default so UI/API stay live."""
    if background:
        # Fast path on the event loop — avoids thread-pool queue behind long sync routes.
        return start_screen_job(request, mode=mode)
    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: _run_sync_screen(request))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Screen failed: {exc}") from exc


@router.get("/api/ta/screen/providers")
def ta_screen_providers() -> dict[str, Any]:
    """Registered price-data providers for the screener (UI contract)."""
    from brokers.config import BROKER_LABELS
    from brokers.service import broker_status_overview

    providers = [p.model_copy(deep=True) for p in SCREEN_DATA_PROVIDERS]
    broker = broker_status_overview()
    adapters = broker.get("adapters") or {}
    live_broker = next(
        (bid for bid, ad in adapters.items() if bid != "stub" and ad.get("live")),
        None,
    )
    if live_broker:
        label = BROKER_LABELS.get(live_broker, live_broker)
        for p in providers:
            if p.id == "auto":
                p.label = f"Auto (Yahoo history · {label} LTP live)"
                p.description = (
                    f"Daily bars from Yahoo/NSE; live last price from {label} when connected."
                )

    live_quote: dict[str, Any] = {"source": "yahoo", "transport": "none"}
    try:
        from brokers.ltp_stream import ltp_stream_status

        stream = ltp_stream_status()
        live_quote = {
            "source": stream.get("broker") or "yahoo",
            "transport": stream.get("transport") or "none",
            "connected": (stream.get("stream") or {}).get("connected"),
            "message": stream.get("message"),
        }
    except Exception:
        pass

    broker_rows = [
        {
            "id": bid,
            "label": BROKER_LABELS.get(bid, bid),
            "configured": bool(ad.get("configured")),
            "live": bool(ad.get("live")),
            "message": ad.get("message"),
            "default": bid == broker.get("default_broker"),
        }
        for bid, ad in adapters.items()
        if bid != "stub"
    ]

    payload = ScreenProvidersContract(
        providers=providers,
        default_provider="auto",
        live_quote=live_quote,
        brokers=broker_rows,
    )
    return payload.model_dump()


@router.get("/api/ta/screen/page")
async def ta_screen_page(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=10, le=100),
    cap_view: Literal["all", "large", "mid", "small"] = "all",
    symbol: str = "",
    grade: str = "",
    stance: str = "",
    min_score: Optional[float] = Query(None),
    max_score: Optional[float] = Query(None),
    min_rsi: Optional[float] = Query(None),
    max_rsi: Optional[float] = Query(None),
    quality_ok: Optional[bool] = Query(None),
    debt_ok: Optional[bool] = Query(None),
    growth_ok: Optional[bool] = Query(None),
    min_quality: Optional[float] = Query(None),
    pattern_bias: str = "",
    sort_key: str = "display_rank",
    sort_dir: Literal["asc", "desc"] = "asc",
    sort_key2: str = "score",
    sort_dir2: SortDir = "desc",
    view: Literal["all", "scanned"] = Query("all"),
) -> dict[str, Any]:
    """Paginated screener rows from the cached run (stable UI contract)."""
    cached = load_cached_screen()
    if not cached:
        raise HTTPException(status_code=404, detail="No cached screen yet. Run the multi-stock screen first.")
    meta = universe_meta()
    expected = meta.get("total") or 500
    stale = (cached.get("universe_size") or 0) < expected or not cached.get("sections")
    query = ScreenPageQueryContract(
        page=page,
        page_size=page_size,
        cap_view=cap_view,
        symbol=symbol,
        grade=grade,
        stance=stance,
        min_score=min_score,
        max_score=max_score,
        min_rsi=min_rsi,
        max_rsi=max_rsi,
        quality_ok=quality_ok,
        debt_ok=debt_ok,
        growth_ok=growth_ok,
        min_quality=min_quality,
        pattern_bias=pattern_bias,
        sort_key=sort_key,
        sort_dir=sort_dir,
        sort_key2=sort_key2,
        sort_dir2=sort_dir2,
        view=view,
    )

    def _build() -> dict[str, Any]:
        from screen_page_cache import resolve_screen_page

        return resolve_screen_page(cached, query, stale=stale, expected=expected)

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _build)


@router.get("/api/ta/screen/page-default")
async def ta_screen_page_default() -> dict[str, Any]:
    """Instant default first page from disk cache (fallback when page build is queued)."""
    from screen_page_cache import _screen_mtime, load_precomputed_default_page, resolve_screen_page
    from screen_contract import ScreenPageQueryContract

    cached = load_cached_screen()
    if not cached:
        raise HTTPException(status_code=404, detail="No cached screen yet. Run the multi-stock screen first.")
    mtime = _screen_mtime()
    pre = load_precomputed_default_page(expected_mtime=mtime)
    if pre:
        return pre
    query = ScreenPageQueryContract(
        page=1,
        page_size=50,
        cap_view="all",
        view="all",
        sort_key="display_rank",
        sort_dir="asc",
        sort_key2="score",
        sort_dir2="desc",
    )
    meta = universe_meta()
    expected = meta.get("total") or 500
    stale = (cached.get("universe_size") or 0) < expected or not cached.get("sections")

    def _build() -> dict[str, Any]:
        return resolve_screen_page(cached, query, stale=stale, expected=expected)

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _build)


@router.get("/api/ta/screen/last")
def ta_screen_last() -> dict[str, Any]:
    cached = load_cached_screen()
    if not cached:
        raise HTTPException(status_code=404, detail="No cached screen yet. Run the multi-stock screen first.")
    meta = universe_meta()
    expected = meta.get("total") or 500
    cached_size = cached.get("universe_size") or 0
    cached["stale"] = cached_size < expected or not cached.get("sections")
    cached["expected_universe_size"] = expected
    cached["contract_version"] = CONTRACT_VERSION
    try:
        heat = sector_heat_from_screen(cached)
    except Exception:
        heat = {"buckets": [], "source": "none", "count": 0}
    return {**cached, "sector_heat": heat, "universe_meta": meta}


@router.get("/api/ta/universe/conviction/status")
def ta_universe_conviction_status() -> dict[str, Any]:
    from trading.deep_universe_scan import deep_scan_status
    return deep_scan_status()


@router.get("/api/ta/universe/conviction")
def ta_universe_conviction_top(
    top: int = Query(30, ge=1, le=100),
    min_score: Optional[float] = Query(None),
) -> dict[str, Any]:
    from trading.deep_universe_scan import query_top_conviction
    return query_top_conviction(top_n=top, min_score=min_score)


@router.post("/api/ta/universe/conviction/scan")
def ta_universe_conviction_scan(
    force: bool = False,
    limit: int = Query(500, ge=50, le=500),
    horizon: str = Query("1m"),
    batch_size: int = Query(50, ge=5, le=100),
    batch_pause_seconds: float = Query(4.0, ge=0, le=60),
    retry_rounds: int = Query(2, ge=0, le=5),
    retry_pause_seconds: float = Query(45.0, ge=0, le=300),
    max_workers: int = Query(4, ge=1, le=12),
    batch_strategy: Literal["round_robin", "sequential"] = Query("round_robin"),
) -> dict[str, Any]:
    from trading.deep_universe_scan import run_deep_universe_scan
    try:
        return run_deep_universe_scan(
            force=force,
            limit=limit,
            horizon=horizon,
            batch_size=batch_size,
            batch_pause_seconds=batch_pause_seconds,
            retry_rounds=retry_rounds,
            retry_pause_seconds=retry_pause_seconds,
            max_workers=max_workers,
            batch_strategy=batch_strategy,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Universe conviction scan failed: {exc}") from exc

