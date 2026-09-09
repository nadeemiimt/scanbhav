"""Stock search, fetch, analyze, compare, paper trade, agent, RAG."""
from __future__ import annotations

import json
import re
import time
from typing import Any

import requests
from fastapi import APIRouter, HTTPException, Query

from agents import ask_rag, run_research_desk
from analyzer import analyze_stock
from compare import compare_stocks, scorecard_only
from paper_trade import ai_paper_lesson, compare_paper_trades, simulate_hold
from routes.helpers import (
    _SEARCH_CACHE,
    _SEARCH_TTL_SECONDS,
    _cache_is_fresh,
    _display_symbol,
    _ensure_loaded,
    analysis_input,
    fetch_prices,
    raw_path,
    response_data,
    rows_from_payload,
)
from routes.schemas import (
    AgentResearchRequest,
    CompareRequest,
    FetchRequest,
    PaperTradeRequest,
    RagAskRequest,
)
from utils.errors import swallow

router = APIRouter(tags=["stocks"])

@router.get("/api/search")
def search_stocks(q: str = Query(..., min_length=1, max_length=80)) -> dict[str, list[dict[str, str]]]:
    """Provider search for UI suggestions; direct symbol entry remains supported.

    Uses Yahoo's lightweight HTTP search endpoint (faster than yfinance.Search),
    with a short in-memory cache so repeated keystrokes feel instant.
    Indian Yahoo suffixes (.NS / .BO) are normalized to this project's
    .NSE / .BSE spelling so Load stock works without manual rewriting.
    """
    needle = q.strip().lower()
    cache_key = needle
    cached = _SEARCH_CACHE.get(cache_key)
    if cached and (time.time() - cached[0]) < _SEARCH_TTL_SECONDS:
        return {"results": cached[1]}

    results: list[dict[str, str]] = []
    try:
        response = requests.get(
            "https://query1.finance.yahoo.com/v1/finance/search",
            params={"q": q.strip(), "quotesCount": 12, "newsCount": 0, "listsCount": 0},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=6,
        )
        response.raise_for_status()
        quotes = response.json().get("quotes") or []
        seen: set[str] = set()
        for item in quotes:
            raw_symbol = (item.get("symbol") or "").strip()
            if not raw_symbol:
                continue
            name = item.get("shortname") or item.get("longname") or ""
            quote_type = (item.get("quoteType") or item.get("typeDisp") or "").upper()
            haystack = f"{raw_symbol} {name}".lower()
            if needle not in haystack:
                continue
            if quote_type and quote_type not in {"EQUITY", "ETF", "MUTUALFUND", ""}:
                continue
            symbol = _display_symbol(raw_symbol)
            if symbol in seen:
                continue
            seen.add(symbol)
            results.append({
                "symbol": symbol,
                "name": name,
                "exchange": item.get("exchange", "") or "",
            })
    except Exception:
        # Fallback to yfinance if the lightweight endpoint is blocked.
        try:
            import yfinance as yf

            quotes = yf.Search(q, max_results=12, news_count=0).quotes
            seen = set()
            for item in quotes:
                raw_symbol = (item.get("symbol") or "").strip()
                if not raw_symbol:
                    continue
                name = item.get("shortname") or item.get("longname") or ""
                if needle not in f"{raw_symbol} {name}".lower():
                    continue
                symbol = _display_symbol(raw_symbol)
                if symbol in seen:
                    continue
                seen.add(symbol)
                results.append({
                    "symbol": symbol,
                    "name": name,
                    "exchange": item.get("exchange", "") or "",
                })
        except Exception:
            results = []

    # If Yahoo returned nothing useful, try a couple of common Indian suffixes.
    if len(results) < 2 and re.fullmatch(r"[A-Za-z][A-Za-z0-9&.-]{1,20}", q.strip()):
        root = q.strip().upper().replace(".NSE", "").replace(".BSE", "").replace(".NS", "").replace(".BO", "")
        for suffix, exchange in ((".NSE", "NSE"), (".BSE", "BSE")):
            candidate = f"{root}{suffix}"
            if any(item["symbol"] == candidate for item in results):
                continue
            results.append({"symbol": candidate, "name": f"Try {candidate}", "exchange": exchange})

    typed = q.upper().strip()
    has_exchange_suffix = bool(re.search(r"\.(NSE|BSE|NS|BO|NYSE|NASDAQ|L|T|HK)$", typed))
    if has_exchange_suffix and typed and not any(item["symbol"].upper() == _display_symbol(typed) for item in results):
        results.insert(0, {"symbol": _display_symbol(typed), "name": "Use typed symbol", "exchange": ""})
    elif not results and re.fullmatch(r"[A-Z0-9][A-Z0-9._-]{1,24}", typed):
        root = typed.replace(".NSE", "").replace(".BSE", "").replace(".NS", "").replace(".BO", "")
        results = [
            {"symbol": f"{root}.NSE", "name": f"Try {root}.NSE", "exchange": "NSE"},
            {"symbol": f"{root}.BSE", "name": f"Try {root}.BSE", "exchange": "BSE"},
        ]
    results = results[:10]
    _SEARCH_CACHE[cache_key] = (time.time(), results)
    return {"results": results}



@router.post("/api/stocks/fetch")
def fetch_stock(request: FetchRequest) -> dict[str, Any]:
    try:
        path = raw_path(request.symbol)
        used_cache = (not request.force_refresh) and _cache_is_fresh(path)
        payload = fetch_prices(request.symbol, request.provider, force_refresh=request.force_refresh)
        return response_data(payload, cached=used_cache)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not fetch {request.symbol}: {exc}") from exc


@router.get("/api/stocks/{symbol}")
def saved_stock(symbol: str, limit: int = Query(1300, ge=2, le=2000)) -> dict[str, Any]:
    path = raw_path(symbol)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"No saved data for {symbol}. Fetch it from the dashboard first.")
    return response_data(json.loads(path.read_text(encoding="utf-8")), limit)


@router.post("/api/stocks/{symbol}/insights")
def stock_insights(symbol: str) -> dict[str, Any]:
    path = raw_path(symbol)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"No saved data for {symbol}. Load it from the dashboard first.")
    try:
        stock = analysis_input(symbol, json.loads(path.read_text(encoding="utf-8")))
        return {"stock_input": stock, "insights": analyze_stock(stock)}
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/analyze")
def analyze(stock: dict[str, Any]) -> dict[str, Any]:
    try:
        return analyze_stock(stock)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/compare")
def compare(request: CompareRequest) -> dict[str, Any]:
    """Side-by-side metric scorecard + optional RAG-backed GenAI comparison."""
    try:
        left_payload = _ensure_loaded(request.left_symbol, request.provider)
        right_payload = _ensure_loaded(request.right_symbol, request.provider)
        left = analysis_input(request.left_symbol, left_payload)
        right = analysis_input(request.right_symbol, right_payload)
        if not request.with_ai:
            return scorecard_only(left, right)
        return compare_stocks(left, right)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Compare failed: {exc}") from exc


@router.post("/api/paper-trade")
def paper_trade(request: PaperTradeRequest) -> dict[str, Any]:
    """Simulate a ~2-week buy-and-hold paper trade for one or more symbols."""
    try:
        simulations = []
        for symbol in request.symbols:
            payload = _ensure_loaded(symbol, request.provider)
            rows = rows_from_payload(payload)
            sim = simulate_hold(
                symbol,
                rows,
                capital=request.capital,
                trading_days=request.trading_days,
                entry=request.entry,
            )
            simulations.append(sim)

        ranking = compare_paper_trades(simulations) if len(simulations) > 1 else {
            "winner_symbol": simulations[0]["symbol"],
            "winner_pnl_pct": simulations[0]["pnl_pct"],
            "spread_pct": 0.0,
            "ranked": [{
                "symbol": simulations[0]["symbol"],
                "pnl": simulations[0]["pnl"],
                "pnl_pct": simulations[0]["pnl_pct"],
                "max_drawdown_pct": simulations[0]["max_drawdown_pct"],
                "outcome": simulations[0]["outcome"],
            }],
        }

        lessons = []
        if request.with_ai:
            for sim in simulations:
                try:
                    stock = analysis_input(sim["symbol"], _ensure_loaded(sim["symbol"], request.provider))
                except Exception:
                    stock = {"ticker": sim["symbol"]}
                lessons.append({"symbol": sim["symbol"], "ai": ai_paper_lesson(sim, stock)})

        return {
            "capital": request.capital,
            "trading_days": request.trading_days,
            "entry": request.entry,
            "simulations": simulations,
            "ranking": ranking,
            "lessons": lessons,
            "disclaimer": (
                "Educational paper trade using historical closes with a small assumed fee. "
                "Not a broker backtest and not a prediction of future returns."
            ),
        }
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Paper trade failed: {exc}") from exc


@router.post("/api/agent/research")
def agent_research(request: AgentResearchRequest) -> dict[str, Any]:
    """Run the multi-agent research desk (fundamental + technical + risk → synthesis)."""
    try:
        payload = _ensure_loaded(request.symbol, request.provider)
        stock = analysis_input(request.symbol, payload)
        return run_research_desk(stock)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Agent research failed: {exc}") from exc


@router.post("/api/rag/ask")
def rag_ask(request: RagAskRequest) -> dict[str, Any]:
    """Ask a free-form research question grounded in the local book knowledge base."""
    try:
        stock = None
        if request.symbol:
            payload = _ensure_loaded(request.symbol, request.provider)
            stock = analysis_input(request.symbol, payload)
        return ask_rag(request.question, stock)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"RAG ask failed: {exc}") from exc
