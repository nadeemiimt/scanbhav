"""Personal advisor routes."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from advisor import advise_portfolio, market_snapshot_from_analysis_input
from config import BASE_DIR
from profiles import (
    create_profile,
    delete_profile,
    get_profile,
    list_profiles,
    merge_holdings,
    normalize_email,
    save_profile,
)
from routes.helpers import _ensure_loaded, analysis_input
from routes.schemas import AdvisorRunRequest, PortfolioJsonIngestRequest, ProfileCreateRequest
from vision_ingest import cleanse_holdings_payload, extract_holdings_from_screenshot, save_upload

router = APIRouter(tags=["advisor"])

@router.get("/api/advisor/profiles")
def advisor_list_profiles(email: str = Query(..., min_length=5, max_length=254)) -> dict[str, Any]:
    try:
        normalized = normalize_email(email)
        return {"email": normalized, "profiles": list_profiles(normalized)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/advisor/profiles")
def advisor_create_profile(request: ProfileCreateRequest) -> dict[str, Any]:
    try:
        return create_profile(request.email, request.name, request.risk_tolerance)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/advisor/profiles/{profile_id}")
def advisor_get_profile(profile_id: str, email: str = Query(..., min_length=5, max_length=254)) -> dict[str, Any]:
    try:
        return get_profile(email, profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/api/advisor/profiles/{profile_id}")
def advisor_delete_profile(profile_id: str, email: str = Query(..., min_length=5, max_length=254)) -> dict[str, str]:
    try:
        delete_profile(email, profile_id)
        return {"status": "deleted"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/advisor/ingest/json")
def advisor_ingest_json(request: PortfolioJsonIngestRequest) -> dict[str, Any]:
    try:
        profile = get_profile(request.email, request.profile_id)
        cleansed = cleanse_holdings_payload(request.portfolio)
        updated = merge_holdings(profile, cleansed["holdings"], source="json")
        return {"profile": updated, "cleansed": cleansed}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"JSON ingest failed: {exc}") from exc


@router.post("/api/advisor/ingest/screenshot")
async def advisor_ingest_screenshot(
    email: str = Form(...),
    profile_id: str = Form(...),
    provider: Optional[str] = Form(None),
    model: Optional[str] = Form(None),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    try:
        normalize_email(email)
        profile = get_profile(email, profile_id)
        raw = await file.read()
        saved = save_upload(raw, file.filename or "portfolio.png", email, profile_id)
        extracted = extract_holdings_from_screenshot(
            raw,
            file.filename or "portfolio.png",
            provider=provider,
            model=model,
        )
        updated = merge_holdings(profile, extracted["holdings"], source=f"screenshot:{saved.name}")
        return {"profile": updated, "extracted": extracted, "saved_as": str(saved.relative_to(BASE_DIR))}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Screenshot ingest failed: {exc}") from exc


@router.post("/api/advisor/run")
def advisor_run(request: AdvisorRunRequest) -> dict[str, Any]:
    try:
        profile = get_profile(request.email, request.profile_id)

        def load_market(symbol: str) -> dict[str, Any]:
            payload = _ensure_loaded(symbol, request.provider)
            stock = analysis_input(symbol, payload)
            return market_snapshot_from_analysis_input(stock)

        advice = advise_portfolio(profile, load_market=load_market, with_ai=request.with_ai)
        profile["last_advice"] = {
            "at": advice.get("totals"),
            "exit_count": len(advice.get("exit_candidates") or []),
            "headline": (advice.get("ai") or {}).get("headline"),
        }
        save_profile(profile)
        return advice
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Advisor run failed: {exc}") from exc
