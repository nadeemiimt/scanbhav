"""Screenshot / JSON cleansing for portfolio ingest via configurable vision models.

Providers:
- openai          → OpenAI Chat Completions vision (default cloud)
- openai_compatible → any OpenAI-compatible base URL (Cursor-gateway style, Groq, etc.)
- ollama          → local Ollama vision model (e.g. llava, llama3.2-vision)
- cursor          → alias for openai_compatible using VISION_BASE_URL / CURSOR_API settings
"""
from __future__ import annotations

import base64
import json
import mimetypes
import re
from pathlib import Path
from typing import Any, Optional

import requests

from config import (
    LLM_MODEL,
    OLLAMA_HOST,
    OLLAMA_KEEP_ALIVE,
    VISION_API_KEY,
    VISION_BASE_URL,
    VISION_MODEL,
    VISION_PROVIDER,
)
from profiles import normalize_holding
from rag import ollama_client

EXTRACT_SCHEMA = {
    "holdings": [
        {
            "asset_type": "stock | mutual_fund",
            "symbol": "ticker if visible, else null",
            "name": "instrument or scheme name",
            "quantity": "number or null",
            "avg_cost": "number or null",
            "invested_value": "number or null",
            "current_value": "number or null",
            "current_price": "number or null",
            "currency": "INR | USD | …",
            "notes": "optional short note",
        }
    ],
    "warnings": ["OCR / readability issues"],
}


def _parse_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {"holdings": [], "warnings": ["Unable to parse model output as JSON."], "raw": text}
        return json.loads(match.group())


def cleanse_holdings_payload(raw: dict[str, Any] | list[Any]) -> dict[str, Any]:
    """Normalize user JSON or vision output into holdings the advisor can store."""
    if isinstance(raw, list):
        items = raw
        warnings: list[str] = []
    elif isinstance(raw, dict):
        items = raw.get("holdings") or raw.get("investments") or raw.get("portfolio") or []
        warnings = list(raw.get("warnings") or [])
        if not items and (raw.get("symbol") or raw.get("name") or raw.get("ticker")):
            items = [raw]
    else:
        raise ValueError("Portfolio JSON must be an object or an array of holdings.")

    if not isinstance(items, list):
        raise ValueError("holdings must be a list.")

    holdings = []
    for item in items:
        cleaned = normalize_holding(item if isinstance(item, dict) else {})
        if cleaned:
            holdings.append(cleaned)
        else:
            warnings.append(f"Skipped incomplete holding: {item!r}")

    # Second-pass LLM cleanse for symbol normalization when local LLM is available.
    if holdings:
        holdings = _llm_normalize_symbols(holdings, warnings)

    return {"holdings": holdings, "warnings": warnings, "count": len(holdings)}


def _llm_normalize_symbols(holdings: list[dict[str, Any]], warnings: list[str]) -> list[dict[str, Any]]:
    """Ask the text LLM to fill missing NSE/BSE-style symbols when names are present."""
    try:
        schema = {"holdings": holdings}
        prompt = (
            "Normalize this investment list for an Indian/global portfolio tracker. "
            "For stocks, prefer Yahoo-style symbols like RELIANCE.NS or AAPL when obvious from the name. "
            "For mutual funds, keep name and leave symbol null if unknown. "
            "Do not invent quantities or prices. Return JSON only with key holdings.\n\n"
            f"{json.dumps(schema, indent=2)}"
        )
        response = ollama_client().chat(
            model=LLM_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You cleanse portfolio holdings JSON. Never invent money amounts. "
                        "Only adjust symbol/name/asset_type for clarity. Return JSON only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            format="json",
            options={"temperature": 0.1, "num_ctx": 4096},
            keep_alive=OLLAMA_KEEP_ALIVE,
        )
        parsed = _parse_json(response["message"]["content"])
        cleaned = []
        for item in parsed.get("holdings") or holdings:
            norm = normalize_holding(item)
            if norm:
                cleaned.append(norm)
        return cleaned or holdings
    except Exception as exc:
        warnings.append(f"Symbol normalization skipped: {exc}")
        return holdings


def _data_url(image_bytes: bytes, filename: str) -> str:
    mime = mimetypes.guess_type(filename)[0] or "image/png"
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def extract_holdings_from_screenshot(
    image_bytes: bytes,
    filename: str = "portfolio.png",
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> dict[str, Any]:
    """Use a configurable vision model to read a brokerage/mutual-fund screenshot."""
    if not image_bytes:
        raise ValueError("Empty screenshot upload.")
    if len(image_bytes) > 12 * 1024 * 1024:
        raise ValueError("Screenshot must be 12MB or smaller.")

    chosen = (provider or VISION_PROVIDER or "openai").strip().lower()
    chosen_model = (model or VISION_MODEL or "").strip()
    prompt = (
        "You are extracting a personal investment portfolio from a brokerage or mutual-fund app screenshot. "
        "Return JSON only matching this schema:\n"
        f"{json.dumps(EXTRACT_SCHEMA, indent=2)}\n"
        "Rules: read only what is visible; use null for missing fields; never invent holdings; "
        "classify each row as stock or mutual_fund; strip currency symbols from numbers."
    )

    if chosen in {"openai", "openai_compatible", "cursor"}:
        raw = _openai_vision(image_bytes, filename, prompt, chosen, chosen_model)
    elif chosen == "ollama":
        raw = _ollama_vision(image_bytes, prompt, chosen_model)
    else:
        raise ValueError(
            f"Unknown VISION_PROVIDER '{chosen}'. Use openai, openai_compatible, cursor, or ollama."
        )

    cleansed = cleanse_holdings_payload(raw)
    cleansed["provider"] = chosen
    cleansed["model"] = chosen_model or VISION_MODEL
    cleansed["vision_warnings"] = list(raw.get("warnings") or [])
    return cleansed


def _openai_vision(
    image_bytes: bytes,
    filename: str,
    prompt: str,
    provider: str,
    model: str,
) -> dict[str, Any]:
    api_key = VISION_API_KEY
    if not api_key:
        raise RuntimeError(
            "VISION_API_KEY is not set. Add it to .env for OpenAI / Cursor-compatible vision extraction."
        )
    base = (VISION_BASE_URL or "https://api.openai.com/v1").rstrip("/")
    if provider == "cursor" and not VISION_BASE_URL:
        # Cursor does not expose a public vision HTTP API; require an explicit compatible gateway.
        raise RuntimeError(
            "VISION_PROVIDER=cursor requires VISION_BASE_URL pointing at an OpenAI-compatible gateway."
        )
    use_model = model or "gpt-4o-mini"
    url = f"{base}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {
        "model": use_model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": _data_url(image_bytes, filename)}},
                ],
            }
        ],
    }
    response = requests.post(url, headers=headers, json=body, timeout=120)
    if response.status_code >= 400:
        raise RuntimeError(f"Vision API error {response.status_code}: {response.text[:400]}")
    content = response.json()["choices"][0]["message"]["content"]
    return _parse_json(content)


def _ollama_vision(image_bytes: bytes, prompt: str, model: str) -> dict[str, Any]:
    use_model = model or "llava"
    encoded = base64.b64encode(image_bytes).decode("ascii")
    # Prefer the Ollama HTTP chat API with images for broad vision-model support.
    response = requests.post(
        f"{OLLAMA_HOST.rstrip('/')}/api/chat",
        json={
            "model": use_model,
            "stream": False,
            "format": "json",
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [encoded],
                }
            ],
        },
        timeout=180,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Ollama vision error {response.status_code}: {response.text[:400]}")
    content = response.json().get("message", {}).get("content") or "{}"
    return _parse_json(content)


def save_upload(image_bytes: bytes, filename: str, email: str, profile_id: str) -> Path:
    """Persist the raw screenshot next to the profile for auditability."""
    from profiles import normalize_email

    safe_email = re.sub(r"[^a-z0-9._@+-]", "_", normalize_email(email))
    folder = Path(__file__).resolve().parent / "data" / "profiles" / safe_email / "uploads" / profile_id
    folder.mkdir(parents=True, exist_ok=True)
    suffix = Path(filename).suffix.lower() or ".png"
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        suffix = ".png"
    target = folder / f"upload_{Path(filename).stem[:40]}{suffix}"
    # Avoid clobbering: add counter if needed.
    counter = 1
    while target.exists():
        target = folder / f"upload_{Path(filename).stem[:40]}_{counter}{suffix}"
        counter += 1
    target.write_bytes(image_bytes)
    return target
