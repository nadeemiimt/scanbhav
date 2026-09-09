"""Agent 0 — optional NSE cache sync (best-effort; production uses vendor/broker feeds)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import BASE_DIR

FOUNDATION_DIR = BASE_DIR / "data" / "quant_foundation"


def _ensure_seed_files() -> None:
    """Create empty seed files so downstream loaders never crash."""
    FOUNDATION_DIR.mkdir(parents=True, exist_ok=True)
    seeds = {
        "fii_dii_flow.json": {"rows": []},
        "bulk_deals.json": {"deals": []},
        "earnings_calendar.json": {"events": []},
        "fo_oi.json": {"symbols": {}},
    }
    for name, payload in seeds.items():
        path = FOUNDATION_DIR / name
        if not path.exists():
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    delivery = FOUNDATION_DIR / "delivery_pct.csv"
    if not delivery.exists():
        delivery.write_text("symbol,date,delivery_pct\n", encoding="utf-8")


def sync_nse_foundation_caches(*, force: bool = False) -> dict[str, Any]:
    """
    Best-effort sync. Full NSE bhavcopy parsing is vendor-specific;
    this ensures seed structure exists and can be extended with broker APIs.
    """
    _ensure_seed_files()
    return {
        "ok": True,
        "message": "Seed foundation files ensured. Load delivery/FII/OI via CSV/JSON drops or broker API.",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "force": force,
    }
