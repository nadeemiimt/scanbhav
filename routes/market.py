"""Market board routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from market_board import market_board
from markets_desk import build_markets_desk

router = APIRouter(tags=["market"])

@router.get("/api/market/board")
def market_board_route(
    limit: int = Query(500, ge=20, le=520),
    top_n: int = Query(10, ge=5, le=25),
    live_indices: bool = Query(True),
) -> dict[str, Any]:
    """Live/delayed index ticker + top winners/losers from local daily caches."""
    try:
        return market_board(limit_universe=limit, top_n=top_n, with_live_indices=live_indices)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Market board failed: {exc}") from exc


@router.get("/api/markets/desk")
def markets_desk_route(
    limit: int = Query(500, ge=20, le=520),
    top_n: int = Query(10, ge=5, le=25),
) -> dict[str, Any]:
    """Full markets desk: indices, breadth, sector board, regime, FII/DII, VIX."""
    try:
        return build_markets_desk(limit=limit, top_n=top_n)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Markets desk failed: {exc}") from exc
