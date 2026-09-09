"""Research desk tool routes."""
from __future__ import annotations

import re
from typing import Any, Literal, Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from desk_tools import market_breadth, scan_watch_alerts, sector_heat_from_screen
from remaining_desk import (
    account_bundle_export,
    account_bundle_import,
    build_pdf_bytes,
    csv_export,
    csv_import,
    curriculum,
    earnings_calendar_from_yahoo,
    export_pdf_html,
    extract_pdf_import,
    intraday_levels_from_rows,
    mf_universe,
    notify_dispatch,
    options_pulse,
    portfolio_correlation,
    sector_relative_strength,
)
from routes.helpers import (
    _ensure_loaded,
    _fetch_intraday_rows,
    fetch_prices,
    rows_from_payload,
)
from routes.schemas import (
    AccountImportRequest,
    BacktestRequest,
    BacktestSweepRequest,
    CorrelationRequest,
    ExportCsvRequest,
    ExportHtmlRequest,
    ExportPdfRequest,
    ImportCsvRequest,
    NotifyRequest,
    OptionsPulseRequest,
    PositionSizeRequest,
    SipRequest,
    WatchScanRequest,
)
from screener import load_cached_screen
from strategy_backtest import run_backtest, run_backtest_sweep
from desk_tools import position_size, sip_projection
from technicals import compute_technicals

router = APIRouter(tags=["desk"])

@router.post("/api/desk/position-size")
def desk_position_size(request: PositionSizeRequest) -> dict[str, Any]:
    try:
        return position_size(
            price=request.price,
            atr=request.atr,
            capital=request.capital,
            risk_pct=request.risk_pct,
            atr_stop_mult=request.atr_stop_mult,
            reward_r=request.reward_r,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/desk/sip")
def desk_sip(request: SipRequest) -> dict[str, Any]:
    return sip_projection(
        monthly=request.monthly,
        years=request.years,
        expected_annual_return_pct=request.expected_annual_return_pct,
    )


@router.post("/api/desk/backtest")
def desk_backtest(request: BacktestRequest) -> dict[str, Any]:
    try:
        payload = _ensure_loaded(request.symbol, request.provider)
        rows = rows_from_payload(payload)
        return run_backtest(
            request.symbol,
            rows,
            strategy=request.strategy,
            capital=request.capital,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Backtest failed: {exc}") from exc


@router.post("/api/desk/watch-scan")
def desk_watch_scan(request: WatchScanRequest) -> dict[str, Any]:
    items = []
    default_rules = request.rules or {"rsi_above": 70, "rsi_below": 30, "supertrend_flip": True}
    for sym in request.symbols[:20]:
        try:
            payload = fetch_prices(sym, request.provider, force_refresh=False)
            tech = compute_technicals(rows_from_payload(payload))
            items.append({"symbol": sym.upper(), "technicals": tech, "rules": default_rules})
        except Exception:
            continue
    return scan_watch_alerts(items)


@router.get("/api/desk/breadth")
def desk_breadth() -> dict[str, Any]:
    try:
        from analysis.breadth import compute_market_breadth
        full = compute_market_breadth(limit=500)
    except Exception:
        full = {"status": "unavailable"}
    try:
        cached = load_cached_screen()
    except Exception:
        cached = None
    rows = (cached or {}).get("top") or []
    legacy = market_breadth(rows)
    heat = sector_heat_from_screen(cached) if cached else {"buckets": [], "count": 0}
    return {**legacy, **full, "sector_heat": heat}


@router.get("/api/desk/sector-heat")
def desk_sector_heat() -> dict[str, Any]:
    try:
        cached = load_cached_screen()
    except Exception:
        cached = None
    if not cached:
        return {"buckets": [], "source": "none", "count": 0, "hint": "Run Screener once to populate heat."}
    heat = sector_heat_from_screen(cached)
    heat["breadth"] = market_breadth(cached.get("top") or [])
    return heat


@router.post("/api/desk/options-pulse")
def desk_options_pulse(request: OptionsPulseRequest) -> dict[str, Any]:
    vix = request.vix
    if vix is None:
        try:
            vix_payload = fetch_prices("^INDIAVIX", "yfinance", force_refresh=False)
            vix_rows = rows_from_payload(vix_payload)
            if vix_rows:
                vix = float(vix_rows[-1].get("5. adjusted close") or vix_rows[-1].get("4. close") or 0) or None
        except Exception:
            pass
    price = request.price
    atr = request.atr
    if price is None or atr is None:
        try:
            payload = _ensure_loaded(request.symbol, "auto")
            tech_rows = rows_from_payload(payload)
            tech = compute_technicals(tech_rows)
            if price is None:
                price = tech.get("price")
            if atr is None:
                atr = (tech.get("volatility") or {}).get("atr_14")
        except Exception:
            pass
    return options_pulse(
        request.symbol,
        vix_level=vix,
        atr=atr,
        price=price,
        spot=price,
    )


@router.get("/api/desk/earnings/{symbol}")
def desk_earnings(symbol: str) -> dict[str, Any]:
    try:
        return earnings_calendar_from_yahoo(symbol)
    except Exception as exc:
        return {
            "symbol": symbol.upper(),
            "events": [],
            "count": 0,
            "note": str(exc),
            "disclaimer": "Unofficial Yahoo calendar — verify on exchange/NSE before acting.",
        }


@router.get("/api/desk/intraday/{symbol}")
def desk_intraday(
    symbol: str,
    provider: Literal["auto", "yfinance", "nse"] = "auto",
) -> dict[str, Any]:
    rows, prior_close, note = _fetch_intraday_rows(symbol, provider)
    levels = intraday_levels_from_rows(rows, prior_close=prior_close)
    return {
        "symbol": symbol.upper(),
        "bar_count": len(rows),
        "rows_sample": rows[-6:] if rows else [],
        "levels": levels,
        "note": note,
    }


@router.post("/api/desk/correlation")
def desk_correlation(request: CorrelationRequest) -> dict[str, Any]:
    series_map: dict[str, list[float]] = {}
    errors: list[str] = []
    for sym in request.symbols[:12]:
        try:
            payload = _ensure_loaded(sym, request.provider)
            rows = rows_from_payload(payload)
            closes = [
                float(r.get("5. adjusted close") or r.get("4. close") or 0)
                for r in rows
                if float(r.get("5. adjusted close") or r.get("4. close") or 0) > 0
            ]
            if len(closes) >= 5:
                series_map[sym.upper()] = closes
            else:
                errors.append(f"{sym}: insufficient history")
        except Exception as exc:
            errors.append(f"{sym}: {exc}")
    result = portfolio_correlation(series_map)
    result["errors"] = errors
    return result


@router.get("/api/desk/sector-rs")
def desk_sector_rs() -> dict[str, Any]:
    bench_return = None
    try:
        bench_payload = _ensure_loaded("^NSEI", "yfinance")
        bench_rows = rows_from_payload(bench_payload)
        bench_tech = compute_technicals(bench_rows)
        bench_return = (bench_tech.get("returns_pct") or {}).get("1m")
    except Exception:
        pass
    try:
        cached = load_cached_screen()
    except Exception:
        cached = None
    rows = (cached or {}).get("top") or (cached or {}).get("results") or []
    if not rows:
        return {
            **sector_relative_strength([], bench_return_1m=bench_return),
            "hint": "Run Screener once to populate sector RS.",
        }
    return sector_relative_strength(rows, bench_return_1m=bench_return)


@router.post("/api/desk/notify")
def desk_notify(request: NotifyRequest) -> dict[str, Any]:
    return notify_dispatch(
        request.alerts,
        webhook_url=request.webhook_url,
        telegram_bot_token=request.telegram_bot_token,
        telegram_chat_id=request.telegram_chat_id,
    )


@router.post("/api/desk/export-html")
def desk_export_html(request: ExportHtmlRequest) -> dict[str, Any]:
    html = export_pdf_html(request.title, request.sections)
    return {"title": request.title, "html": html, "section_count": len(request.sections or [])}


@router.post("/api/desk/export-pdf")
def desk_export_pdf(request: ExportPdfRequest):
    try:
        pdf_bytes = build_pdf_bytes(request.title, request.sections)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF build failed: {exc}") from exc
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", (request.title or "brief")[:60]) or "brief"
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe}.pdf"'},
    )


@router.post("/api/desk/export-csv")
def desk_export_csv(request: ExportCsvRequest) -> dict[str, Any]:
    try:
        text = csv_export(request.kind, request.rows, symbol=request.symbol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "kind": request.kind,
        "csv": text,
        "filename": f"scan_bhav_{request.kind}.csv",
        "row_count": max(0, text.count("\n") - 1),
    }


@router.post("/api/desk/import-csv")
def desk_import_csv(request: ImportCsvRequest) -> dict[str, Any]:
    try:
        return csv_import(request.kind, request.csv_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/desk/import-pdf")
async def desk_import_pdf(file: UploadFile = File(...)) -> dict[str, Any]:
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty PDF upload")
    if len(raw) > 8_000_000:
        raise HTTPException(status_code=400, detail="PDF too large (max 8MB)")
    try:
        return extract_pdf_import(raw)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"PDF import failed: {exc}") from exc


@router.get("/api/desk/mf-universe")
def desk_mf_universe() -> dict[str, Any]:
    return mf_universe()


@router.get("/api/desk/curriculum")
def desk_curriculum() -> dict[str, Any]:
    return curriculum()


@router.post("/api/desk/account/export")
def desk_account_export(body: Dict[str, Any]) -> dict[str, Any]:
    return account_bundle_export(body)


@router.post("/api/desk/account/import")
def desk_account_import(request: AccountImportRequest) -> dict[str, Any]:
    return account_bundle_import(request.model_dump())


@router.post("/api/desk/backtest-sweep")
def desk_backtest_sweep(request: BacktestSweepRequest) -> dict[str, Any]:
    try:
        payload = _ensure_loaded(request.symbol, request.provider)
        rows = rows_from_payload(payload)
        return run_backtest_sweep(
            request.symbol,
            rows,
            request.strategy,
            request.capital,
            fast_periods=request.fast_periods,
            slow_periods=request.slow_periods,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Backtest sweep failed: {exc}") from exc
