"""Two-layer quant + LLM pipeline API (Nifty 500) — Agents 0–9."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from quant_layer.agent0.etl import agent0_status, run_agent0_etl
from quant_layer.orchestrator import daily_pipeline
from quant_layer.pipeline import analyze_symbol_rows, build_universe_shortlist, load_cached_shortlist
from quant_layer.trade_journal import journal_stats
from quant_layer.backtest import backtest_trigger_catalog
from quant_layer.triggers import build_trigger_frame, TRIGGER_COLUMNS
from routes.helpers import fetch_prices_light, rows_from_payload
from trading.pre_live_gates import check_pre_live_gates

router = APIRouter(tags=["quant"])


class QuantScanRequest(BaseModel):
    limit: int = Field(500, ge=50, le=500)
    max_shortlist: int = Field(30, ge=5, le=100)
    max_workers: int = Field(8, ge=1, le=16)
    use_cache: bool = False


class QuantPipelineRequest(BaseModel):
    limit: int = Field(500, ge=50, le=500)
    max_shortlist: int = Field(30, ge=5, le=100)
    use_llm: bool = True
    provider: Optional[str] = None
    model: Optional[str] = None
    account_risk_inr: float = Field(3500, ge=500)
    max_notional_inr: float = Field(300000, ge=10000)


def _load_rows(symbol: str) -> list[dict[str, Any]]:
    payload = fetch_prices_light(symbol, force_refresh=False, provider="auto", allow_nse_fallback=True)
    rows = rows_from_payload(payload)
    if len(rows) < 30:
        raise ValueError("insufficient history")
    return rows


@router.post("/api/quant/agent0/etl")
def quant_agent0_etl(force: bool = False) -> dict[str, Any]:
    return run_agent0_etl(force=force)


@router.get("/api/quant/agent0/status")
def quant_agent0_status() -> dict[str, Any]:
    return agent0_status()


@router.post("/api/quant/scan")
def quant_scan(request: QuantScanRequest) -> dict[str, Any]:
    if request.use_cache:
        cached = load_cached_shortlist()
        if cached:
            return {"cached": True, **cached}
    try:
        return build_universe_shortlist(
            load_rows=_load_rows,
            limit=request.limit,
            max_shortlist=request.max_shortlist,
            max_workers=request.max_workers,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Quant scan failed: {exc}") from exc


@router.post("/api/quant/pipeline")
def quant_full_pipeline(request: QuantPipelineRequest) -> dict[str, Any]:
    """Full daily pipeline — Agents 0, 1, 2, 4, 5, 6, 7, 8, 9."""
    try:
        return daily_pipeline(
            load_rows=_load_rows,
            limit=request.limit,
            max_shortlist=request.max_shortlist,
            use_llm=request.use_llm,
            provider=request.provider,
            model=request.model,
            account_risk_inr=request.account_risk_inr,
            max_notional_inr=request.max_notional_inr,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Pipeline failed: {exc}") from exc


@router.post("/api/quant/synthesize")
def quant_synthesize(request: QuantPipelineRequest) -> dict[str, Any]:
    return quant_full_pipeline(request)


@router.get("/api/quant/shortlist")
def quant_shortlist_cached() -> dict[str, Any]:
    cached = load_cached_shortlist()
    if not cached:
        raise HTTPException(status_code=404, detail="No quant shortlist yet. POST /api/quant/scan first.")
    return cached


@router.get("/api/quant/digest")
def quant_digest() -> dict[str, Any]:
    """Latest composite report snapshot for UI."""
    from config import BASE_DIR
    import json
    from datetime import datetime, timezone

    snap_dir = BASE_DIR / "data" / "quant_cache" / "features"
    if not snap_dir.exists():
        raise HTTPException(status_code=404, detail="No digest yet")
    snaps = sorted(snap_dir.glob("daily_snapshot_*.json"), reverse=True)
    if not snaps:
        cached = load_cached_shortlist()
        if not cached:
            raise HTTPException(status_code=404, detail="No digest yet")
        return {"shortlist": cached, "generated_at": datetime.now(timezone.utc).isoformat()}
    try:
        return json.loads(snaps[0].read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/quant/analyze/{symbol}")
def quant_analyze_symbol(symbol: str) -> dict[str, Any]:
    sym = symbol.upper()
    if not sym.endswith(".NSE") and not sym.endswith(".BSE"):
        sym = f"{sym}.NSE"
    try:
        rows = _load_rows(sym)
        return analyze_symbol_rows(sym, rows)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/quant/backtest/{symbol}")
def quant_backtest_symbol(symbol: str, trigger: str = Query("rsi_oversold_bounce")) -> dict[str, Any]:
    sym = symbol.upper()
    if not sym.endswith(".NSE"):
        sym = f"{sym}.NSE"
    col = trigger if trigger.startswith("trigger_") else f"trigger_{trigger}"
    try:
        rows = _load_rows(sym)
        df = build_trigger_frame(rows)
        from quant_layer.backtest import run_backtest, backtest_stats
        trades = run_backtest(df, col)
        return {"symbol": sym, "trigger": col, "stats": backtest_stats(trades), "trades": trades.head(20).to_dict("records")}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/quant/journal/stats")
def quant_journal_stats(min_entries: int = 10) -> dict[str, Any]:
    return journal_stats(min_entries=min_entries)


@router.get("/api/quant/pre-live-gates")
def quant_pre_live_gates(reconcile: bool = False) -> dict[str, Any]:
    return check_pre_live_gates(run_reconcile=reconcile)
