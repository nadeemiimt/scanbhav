"""First-run / external-user prerequisite helpers."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(tags=["setup"])


class SetupAction(BaseModel):
    prefer_package_manager: bool = Field(default=True)


@router.get("/api/setup/status")
def setup_status() -> dict[str, Any]:
    from setup_prereqs import prerequisites_report

    return prerequisites_report()


@router.post("/api/setup/seen")
def setup_seen() -> dict[str, Any]:
    from setup_prereqs import mark_setup_seen

    return mark_setup_seen()


@router.post("/api/setup/install-ollama")
def setup_install_ollama(body: SetupAction | None = None) -> dict[str, Any]:
    from setup_prereqs import install_or_open_ollama

    prefer = True if body is None else bool(body.prefer_package_manager)
    return install_or_open_ollama(prefer_package_manager=prefer)


@router.post("/api/setup/open-vc-redist")
def setup_open_vc_redist() -> dict[str, Any]:
    from setup_prereqs import open_vc_redist

    return open_vc_redist()


@router.post("/api/setup/open-url")
def setup_open_url(body: dict[str, str]) -> dict[str, Any]:
    from setup_prereqs import open_url

    url = str((body or {}).get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return {"ok": False, "reason": "Only http(s) URLs are allowed."}
    return open_url(url)
