"""Consolidated broker holdings, sell-all, payout account."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from brokers.consolidated import fetch_consolidated_holdings, sell_all_execute, sell_all_preview
from brokers.payout_account import payout_summary, save_payout_account
from routes.schemas import BrokerSellAllRequest, PayoutAccountRequest

router = APIRouter(tags=["broker"])


@router.get("/api/broker/holdings/consolidated")
def broker_holdings_consolidated() -> dict[str, Any]:
    """Zerodha + Groww + FYERS holdings with live price & P&L when connected."""
    return fetch_consolidated_holdings()


@router.get("/api/broker/payout-account")
def broker_payout_get() -> dict[str, Any]:
    return payout_summary()


@router.post("/api/broker/payout-account")
def broker_payout_save(request: PayoutAccountRequest) -> dict[str, Any]:
    try:
        saved = save_payout_account(request.model_dump())
        return {"ok": True, "account": saved}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/broker/sell-all/preview")
def broker_sell_all_preview(request: BrokerSellAllRequest) -> dict[str, Any]:
    return sell_all_preview(
        tax_bracket_rate_pct=request.tax_bracket_rate_pct,
        include_mf=request.include_mf,
    )


@router.post("/api/broker/sell-all/execute")
def broker_sell_all_execute(request: BrokerSellAllRequest) -> dict[str, Any]:
    if not request.confirm:
        raise HTTPException(status_code=400, detail="Set confirm=true to place live sell orders.")
    payout = payout_summary()
    if not payout.get("configured"):
        raise HTTPException(
            status_code=400,
            detail="Add payout bank account first (POST /api/broker/payout-account).",
        )
    try:
        return sell_all_execute(
            include_mf=request.include_mf,
            dry_run=request.dry_run,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
