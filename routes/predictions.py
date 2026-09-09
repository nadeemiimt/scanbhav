from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from prediction_tracker import (
    add_prediction,
    fetch_mark_prices,
    list_tracked,
    rate_prediction,
    refresh_prices as refresh_tracked_prices,
    remove_prediction,
)
from routes.schemas import PredictionRateRequest, PredictionRefreshRequest, PredictionTrackRequest

router = APIRouter(tags=["predictions"])


@router.get("/api/predictions/track")
def predictions_list() -> dict[str, Any]:
    return list_tracked()


@router.post("/api/predictions/track")
def predictions_add(request: PredictionTrackRequest) -> dict[str, Any]:
    try:
        item = add_prediction(
            symbol=request.symbol,
            name=request.name,
            entry_price=request.entry_price,
            as_of=request.as_of,
            predicted_stance=request.predicted_stance,
            predicted_horizon=request.predicted_horizon,
            composite_score=request.composite_score,
            conviction_score=request.conviction_score,
            summary=request.summary,
        )
        return {"item": item, "track": list_tracked()}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/predictions/track/{prediction_id}")
def predictions_delete(prediction_id: str) -> dict[str, Any]:
    return remove_prediction(prediction_id)


@router.post("/api/predictions/track/refresh")
def predictions_refresh(request: PredictionRefreshRequest) -> dict[str, Any]:
    track = list_tracked()
    syms = [
        str(i.get("symbol") or "").upper()
        for i in (track.get("items") or [])
        if i.get("status") == "open" and i.get("symbol")
    ]
    price_map = fetch_mark_prices(syms, provider=request.provider)
    out = refresh_tracked_prices(price_map)
    out["price_sources"] = len(price_map)
    return out


@router.post("/api/predictions/track/{prediction_id}/rate")
def predictions_rate(prediction_id: str, request: PredictionRateRequest) -> dict[str, Any]:
    try:
        track = list_tracked()
        item = next((i for i in (track.get("items") or []) if i.get("id") == prediction_id), None)
        if item and item.get("symbol"):
            try:
                sym = str(item["symbol"]).upper()
                fresh = fetch_mark_prices([sym], provider="auto")
                if fresh.get(sym):
                    refresh_tracked_prices(fresh)
            except Exception:
                pass
        return rate_prediction(
            prediction_id=prediction_id,
            rating=request.rating,
            notes=request.notes,
            outcome_label=request.outcome_label,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
