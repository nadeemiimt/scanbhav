"""Unified daily Nifty 500 job — one scheduler run, all PDF pipeline outputs preserved."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from config import BASE_DIR

MANIFEST_PATH = BASE_DIR / "data" / "trading" / "daily_universe.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_daily_universe(
    *,
    force: bool = False,
    use_llm: bool = False,
    run_conviction: bool = False,
    load_rows: Optional[Callable[[str], list[dict[str, Any]]]] = None,
) -> dict[str, Any]:
    """
    Single pre-market pass for Nifty 500 (does not remove individual scan APIs):

    1. Agent 0 ETL (PDF Agent 0)
    2. Layer-1 quant shortlist (PDF Layer 1)
    3. Optional full quant+LLM pipeline digest (PDF Agents 1/2/7/8)
    4. Morning scan + RAG (existing autopilot feed)
    5. Optional conviction universe scan (research — kept, not deleted)
    """
    from trading.config_store import load_trading_config

    ap = load_trading_config().get("autopilot") or {}
    started = _now()
    steps: dict[str, Any] = {}

    if load_rows is None:
        from routes.helpers import fetch_prices_light, rows_from_payload

        def load_rows(sym: str) -> list[dict[str, Any]]:
            payload = fetch_prices_light(sym, force_refresh=False, provider="auto", allow_nse_fallback=True)
            rows = rows_from_payload(payload)
            if len(rows) < 30:
                raise ValueError("insufficient history")
            return rows

    # Agent 0 — PDF data foundation
    try:
        from quant_layer.agent0.etl import run_agent0_etl

        steps["agent0"] = run_agent0_etl(force=force)
    except Exception as exc:
        steps["agent0"] = {"error": str(exc)[:200]}

    limit = int(ap.get("daily_universe_limit") or 500)
    max_shortlist = int(ap.get("quant_shortlist_max") or 30)

    # Layer 1 quant scan (always — PDF Layer 1)
    try:
        from quant_layer.pipeline import ensure_quant_shortlist

        steps["quant_scan"] = ensure_quant_shortlist(
            load_rows=load_rows,
            limit=limit,
            max_shortlist=max_shortlist,
            force=force,
        )
    except Exception as exc:
        steps["quant_scan"] = {"error": str(exc)[:200]}

    # Full PDF pipeline (Agents 0–9 orchestrator) when LLM enabled or forced
    if use_llm or ap.get("quant_llm_synthesis_enabled"):
        try:
            from quant_layer.orchestrator import daily_pipeline

            steps["quant_pipeline"] = daily_pipeline(
                load_rows=load_rows,
                limit=limit,
                max_shortlist=max_shortlist,
                use_llm=bool(use_llm or ap.get("quant_llm_synthesis_enabled")),
            )
        except Exception as exc:
            steps["quant_pipeline"] = {"error": str(exc)[:200]}

    # Morning scan — TA screen + quant merge + RAG (existing; not replaced)
    try:
        from trading.morning_scan import run_morning_scan

        steps["morning_scan"] = run_morning_scan(force=force, load_rows_fn=load_rows)
    except Exception as exc:
        steps["morning_scan"] = {"error": str(exc)[:200]}

    # Conviction scan — optional research pass (kept for PDF / deep dossier path)
    if run_conviction or ap.get("daily_universe_conviction_enabled", False):
        try:
            from trading.deep_universe_scan import run_deep_universe_scan

            steps["conviction_scan"] = run_deep_universe_scan(
                load_rows_fn=load_rows,
                limit=limit,
                force=force,
            )
        except Exception as exc:
            steps["conviction_scan"] = {"error": str(exc)[:200]}

    manifest = {
        "run_at": started,
        "finished_at": _now(),
        "force": force,
        "use_llm": use_llm,
        "steps": steps,
        "summary": {
            "quant_triggered": (steps.get("quant_scan") or {}).get("triggered_count"),
            "quant_shortlist": (steps.get("quant_scan") or {}).get("shortlist_count"),
            "morning_scored": (steps.get("morning_scan") or {}).get("scored"),
            "conviction_scored": (steps.get("conviction_scan") or {}).get("scored"),
        },
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def daily_universe_status() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        return {"ready": False}
    try:
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        return {"ready": True, **data}
    except Exception:
        return {"ready": False, "error": "manifest_unreadable"}
