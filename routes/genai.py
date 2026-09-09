"""GenAI deep research routes."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from analysis.bundle import build_extended_analysis, extended_summary_for_agents
from genai_agent_loop import investors_from_quote, run_agentic_research
from genai_research import latest_research_payload, run_deep_research
from horizon_rank import rate_all_horizons
from investors import investor_perspectives
from llm_providers import list_providers
from news_catalysts import gather_news_catalysts
from routes.helpers import (
    _cache_is_fresh,
    fetch_prices,
    raw_path,
    response_data,
    rows_from_payload,
)
from routes.schemas import GenaiResearchRequest
from technicals import compute_technicals

router = APIRouter(tags=["genai"])

@router.get("/api/genai/providers")
def genai_providers() -> dict[str, Any]:
    return list_providers()


@router.get("/api/genai/history/{symbol}")
def genai_history(symbol: str, limit: int = Query(10, ge=1, le=50)) -> dict[str, Any]:
    try:
        payload = latest_research_payload(symbol.upper())
        # Keep limit on history list for lighter payloads.
        payload["history"] = (payload.get("history") or [])[:limit]
        payload["count"] = len(payload.get("history") or [])
        return payload
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Insight history failed: {exc}") from exc


@router.post("/api/genai/research")
def genai_research(request: GenaiResearchRequest) -> dict[str, Any]:
    """Deep GenAI research with Chroma append-only insight memory."""
    try:
        payload = fetch_prices(request.symbol, request.market_provider, force_refresh=request.force_refresh)
        rows = rows_from_payload(payload)
        tech = compute_technicals(rows)
        ratings = rate_all_horizons(tech)
        quote = response_data(
            payload,
            cached=(not request.force_refresh) and _cache_is_fresh(raw_path(request.symbol)),
        )
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
        investors = investor_perspectives(tech, investor_fundamentals)
        news = gather_news_catalysts(
            request.symbol,
            company_name=company.get("name"),
            sector=company.get("sector"),
            industry=company.get("industry"),
            existing_news=quote.get("news") or [],
        )
        extended = build_extended_analysis(
            symbol=request.symbol,
            rows=rows,
            tech=tech,
            quote=quote,
            news=news,
            ratings=ratings,
            include_slow=True,
        )
        ratings = extended.get("ratings_blended") or ratings
        research = run_deep_research(
            symbol=request.symbol,
            technicals=tech,
            ratings=ratings,
            quote=quote,
            investors=investors,
            news=news,
            provider=request.provider,
            model=request.model,
            extended=extended,
        )
        return research
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"GenAI research failed: {exc}") from exc


@router.post("/api/genai/research/stream")
def genai_research_stream(request: GenaiResearchRequest) -> StreamingResponse:
    """SSE agentic floor: specialists talk, work, then open the briefcase."""

    def _prepare() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
        payload = fetch_prices(request.symbol, request.market_provider, force_refresh=request.force_refresh)
        rows = rows_from_payload(payload)
        tech = compute_technicals(rows)
        ratings = rate_all_horizons(tech)
        quote = response_data(
            payload,
            cached=(not request.force_refresh) and _cache_is_fresh(raw_path(request.symbol)),
        )
        investors = investors_from_quote(tech, quote)
        company = quote.get("company") or {}
        news = gather_news_catalysts(
            request.symbol,
            company_name=company.get("name"),
            sector=company.get("sector"),
            industry=company.get("industry"),
            existing_news=quote.get("news") or [],
        )
        extended = build_extended_analysis(
            symbol=request.symbol,
            rows=rows,
            tech=tech,
            quote=quote,
            news=news,
            ratings=ratings,
            include_slow=True,
        )
        ratings = extended.get("ratings_blended") or ratings
        return tech, ratings, quote, investors, news, extended

    def event_gen():
        try:
            tech, ratings, quote, investors, news, extended = _prepare()
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'text': str(exc), 'agent': {'id': 'lead', 'name': 'Arjun Mehta', 'role': 'Desk Lead', 'initials': 'AM', 'accent': '#e8b84a'}})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'text': 'stopped'})}\n\n"
            return
        try:
            for event in run_agentic_research(
                symbol=request.symbol,
                technicals=tech,
                ratings=ratings,
                quote=quote,
                investors=investors,
                news=news,
                extended=extended,
                provider=request.provider,
                model=request.model,
                execute_trades=request.execute_trades,
                trade_quantity=request.trade_quantity,
                autonomous_picks=request.autonomous_picks,
                max_autonomous_picks=request.max_autonomous_picks,
                market_provider=request.market_provider,
            ):
                yield f"data: {json.dumps(event, default=str)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'text': f'Agent loop failed: {exc}', 'agent': {'id': 'lead', 'name': 'Arjun Mehta', 'role': 'Desk Lead', 'initials': 'AM', 'accent': '#e8b84a'}})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'text': 'stopped'})}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
