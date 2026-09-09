"""Finnhub inbound webhook receiver."""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Request

from analysis.finnhub_webhook_store import append_event, recent_events
from config import FINNHUB_WEBHOOK_PUBLIC_URL, FINNHUB_WEBHOOK_SECRET

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])


def _verify_secret(header: Optional[str]) -> None:
    expected = (FINNHUB_WEBHOOK_SECRET or "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Finnhub webhook secret not configured")
    if not header or header.strip() != expected:
        raise HTTPException(status_code=401, detail="Invalid Finnhub webhook secret")


def _persist(payload: dict[str, Any]) -> None:
    try:
        append_event(payload)
        logger.info("Finnhub webhook stored: keys=%s", list(payload.keys())[:8])
    except Exception:
        logger.exception("Finnhub webhook persist failed")


@router.post("/api/webhooks/finnhub")
async def finnhub_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_finnhub_secret: Optional[str] = Header(default=None, alias="X-Finnhub-Secret"),
) -> dict[str, bool]:
    """Ack Finnhub events immediately; persist asynchronously."""
    _verify_secret(x_finnhub_secret)
    try:
        payload = await request.json()
    except Exception:
        payload = {"raw": (await request.body()).decode("utf-8", errors="replace")[:4000]}
    if not isinstance(payload, dict):
        payload = {"data": payload}
    background_tasks.add_task(_persist, payload)
    return {"received": True}


@router.get("/api/webhooks/finnhub/recent")
def finnhub_webhook_recent(limit: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
    """Recent stored Finnhub webhook payloads (local debug)."""
    return {
        "endpoint": FINNHUB_WEBHOOK_PUBLIC_URL or "/api/webhooks/finnhub",
        "events": recent_events(limit=limit),
    }
