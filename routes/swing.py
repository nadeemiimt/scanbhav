"""Swing-trading desk routes."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException

from desk_tools import event_watch, position_size, relative_strength
from deep_dossier import build_deep_dossier
from horizon_rank import rate_all_horizons
from indicator_guide import INDICATOR_GUIDE
from market_signals import build_critical_signals
from news_catalysts import gather_news_catalysts
from remaining_desk import earnings_calendar_from_yahoo
from routes.helpers import _cache_is_fresh, fetch_prices, raw_path, rows_from_payload
from routes.schemas import SwingPlanRequest, SwingPnlRequest, SwingRecalcRequest, SwingSetupRequest
from swing_tools import build_swing_setup, build_trade_plan_payload, recalc_swing_size
from technicals import compute_technicals

router = APIRouter(tags=["swing"])


def _relative_strength_for(tech: dict[str, Any]) -> dict[str, Any] | None:
    for bench_sym in ("^NSEI", "NIFTY.NSE", "NIFTYBEES.NSE"):
        try:
            bench_path = raw_path(bench_sym)
            if not bench_path.exists():
                continue
            bench_payload = json.loads(bench_path.read_text(encoding="utf-8"))
            bench_tech = compute_technicals(rows_from_payload(bench_payload))
            return relative_strength(
                tech.get("returns_pct") or {},
                bench_tech.get("returns_pct") or {},
                bench_label="NIFTY",
            )
        except Exception:
            continue
    return None


def _enrich_setup_context(
    *,
    symbol: str,
    payload: dict[str, Any],
    rows: list[dict[str, Any]],
    tech: dict[str, Any],
    ratings: dict[str, Any],
    with_dossier: bool,
) -> dict[str, Any]:
    company = payload.get("Company Data") or {}
    quote = {
        "company": company,
        "fundamentals": payload.get("Fundamentals"),
        "peers": payload.get("Peers"),
        "rows": rows,
    }
    news = None
    try:
        news = gather_news_catalysts(
            symbol,
            company_name=company.get("name"),
            sector=company.get("sector"),
            industry=company.get("industry"),
            existing_news=payload.get("News") or [],
            limit=8,
        )
    except Exception:
        news = None

    dossier = None
    if with_dossier:
        try:
            dossier = build_deep_dossier(
                symbol=symbol,
                technicals=tech,
                ratings=ratings,
                quote=quote,
                indicator_guide=INDICATOR_GUIDE,
                news=news,
            )
        except Exception:
            dossier = None

    events = event_watch(news, dossier)
    earnings = None
    try:
        earnings = earnings_calendar_from_yahoo(symbol)
    except Exception:
        earnings = None

    critical = None
    try:
        critical = build_critical_signals(
            technicals=tech,
            ratings=ratings,
            news=news,
            quote=quote,
        )
    except Exception:
        critical = None

    candles = (tech.get("charts") or {}).get("candles") or []
    chart_candles = [
        {
            "date": c.get("date"),
            "open": c.get("open"),
            "high": c.get("high"),
            "low": c.get("low"),
            "close": c.get("close"),
        }
        for c in candles[-60:]
    ]

    dossier_snippet = None
    if dossier:
        conv = dossier.get("conviction") or {}
        dossier_snippet = {
            "conviction_score": conv.get("conviction_score"),
            "grade": conv.get("grade"),
            "plain_english": conv.get("plain_english"),
            "factors": (conv.get("factors") or [])[:6],
        }
    elif critical:
        dossier_snippet = {
            "conviction_score": None,
            "grade": None,
            "plain_english": (critical.get("price_distortion") or {}).get("plain_english"),
            "factors": [],
        }

    return {
        "events": events,
        "earnings": earnings,
        "critical_signals": critical,
        "chart_candles": chart_candles,
        "dossier_snippet": dossier_snippet,
        "news_headline_count": len((news or {}).get("headlines") or []),
    }


@router.post("/api/swing/setup")
def swing_setup(request: SwingSetupRequest) -> dict[str, Any]:
    """Swing setup score (1W + 1M blend) with entry/stop/target hints."""
    try:
        payload = fetch_prices(request.symbol, request.provider, force_refresh=request.force_refresh)
        rows = rows_from_payload(payload)
        tech = compute_technicals(rows)
        ratings = rate_all_horizons(tech)
        rs = _relative_strength_for(tech)
        ctx = _enrich_setup_context(
            symbol=request.symbol,
            payload=payload,
            rows=rows,
            tech=tech,
            ratings=ratings,
            with_dossier=request.with_dossier,
        )
        setup = build_swing_setup(
            symbol=request.symbol,
            tech=tech,
            ratings=ratings,
            dossier={"conviction": ctx.get("dossier_snippet") or {}} if ctx.get("dossier_snippet") else None,
            relative_strength_pack=rs,
            capital=request.capital,
            risk_pct=request.risk_pct,
            atr_stop_mult=request.atr_stop_mult,
            reward_r=request.reward_r,
        )
        setup["metadata"] = {
            "cached": (not request.force_refresh) and _cache_is_fresh(raw_path(request.symbol)),
            "provider": request.provider,
            "force_refresh": request.force_refresh,
        }
        setup["events"] = ctx["events"]
        setup["earnings"] = ctx["earnings"]
        setup["critical_signals"] = ctx["critical_signals"]
        setup["chart_candles"] = ctx["chart_candles"]
        setup["dossier_snippet"] = ctx["dossier_snippet"]
        if rs:
            setup["relative_strength"] = rs
        return setup
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Swing setup failed: {exc}") from exc


@router.post("/api/swing/plan")
def swing_plan(request: SwingPlanRequest) -> dict[str, Any]:
    """Validate and normalize a swing trade plan."""
    try:
        plan = build_trade_plan_payload(
            symbol=request.symbol,
            entry=request.entry,
            stop=request.stop,
            targets=request.targets,
            shares=request.shares,
            thesis=request.thesis,
            horizon=request.horizon,
            capital=request.capital,
            risk_pct=request.risk_pct,
            trailing_stop=request.trailing_stop,
            atr_stop_mult=request.atr_stop_mult,
            reward_r=request.reward_r,
        )
        plan["disclaimer"] = "Educational trade plan — wire your broker API to execute."
        return plan
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/swing/recalc")
def swing_recalc(request: SwingRecalcRequest) -> dict[str, Any]:
    """Recalculate share count and targets from entry/stop/capital/risk."""
    try:
        if request.stop:
            out = recalc_swing_size(
                entry=request.entry,
                stop=request.stop,
                capital=request.capital,
                risk_pct=request.risk_pct,
                reward_r=request.reward_r,
            )
        else:
            out = position_size(
                price=request.entry,
                atr=request.atr,
                capital=request.capital,
                risk_pct=request.risk_pct,
                atr_stop_mult=request.atr_stop_mult,
                reward_r=request.reward_r,
            )
        return out
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/swing/pnl")
def swing_pnl(request: SwingPnlRequest) -> dict[str, Any]:
    """Batch last prices — broker live quotes when configured, else Yahoo cache."""
    from brokers.config import load_broker_env
    from brokers.service import get_live_quotes

    env = load_broker_env()
    broker_quotes: dict[str, Any] = {}
    broker_errors: list[str] = []
    if env.default_broker != "stub":
        try:
            bq = get_live_quotes(env.default_broker, request.symbols[:24])
            broker_quotes = bq.get("quotes") or {}
            broker_errors = list(bq.get("errors") or [])
        except Exception as exc:
            broker_errors.append(str(exc))

    quotes: dict[str, Any] = {}
    errors: list[str] = list(broker_errors)
    for sym in request.symbols[:24]:
        key = sym.strip().upper()
        if not key:
            continue
        if key in broker_quotes and broker_quotes[key].get("price") is not None:
            quotes[key] = {**broker_quotes[key], "source": env.default_broker}
            continue
        try:
            payload = fetch_prices(key, request.provider, force_refresh=False)
            tech = compute_technicals(rows_from_payload(payload))
            price = tech.get("price")
            quotes[key] = {
                "price": price,
                "as_of": tech.get("as_of"),
                "change_pct": (tech.get("returns_pct") or {}).get("1d"),
                "source": "cached_eod",
            }
        except Exception as exc:
            errors.append(f"{key}: {exc}")
    return {"quotes": quotes, "errors": errors, "broker": env.default_broker}
