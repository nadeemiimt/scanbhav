"""
Human decision desk — one review list, no new market scan.

Reads the cached technical digest and the cached order-book screen.
The spec's only required human step is reviewing this list.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from config import BASE_DIR

SNAP_DIR = BASE_DIR / "data" / "quant_cache" / "features"


def _latest_snapshot() -> Optional[dict[str, Any]]:
    if not SNAP_DIR.exists():
        return None
    snaps = sorted(SNAP_DIR.glob("daily_snapshot_*.json"), reverse=True)
    if not snaps:
        return None
    try:
        return json.loads(snaps[0].read_text(encoding="utf-8"))
    except Exception:
        return None


def _technical_cards(report: dict[str, Any], *, limit: int = 8) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for row in (report.get("ranked") or [])[:limit]:
        llm = row.get("llm") or {}
        quant = row.get("quant") or {}
        triggers = quant.get("triggers_fired") or (quant.get("payload") or {}).get("triggers_fired") or []
        conviction = llm.get("conviction_score")
        why = str(llm.get("rationale") or "").strip()
        if not why:
            why = f"{len(triggers) or quant.get('trigger_count') or 0} technical triggers fired"
        cards.append({
            "symbol": row.get("symbol"),
            "decision": "review",
            "conviction": conviction,
            "why": why[:280],
            "conflicts": llm.get("conflicting_signals") or [],
            "triggers": triggers[:6],
            "composite_score": row.get("composite_score"),
        })
    return cards


def _order_cards(screen: Optional[dict[str, Any]], *, limit: int = 8) -> list[dict[str, Any]]:
    if not screen or screen.get("skipped"):
        return []
    cards = []
    for row in (screen.get("shortlist") or [])[:limit]:
        cards.append({
            "symbol": row.get("symbol"),
            "decision": "review",
            "status": row.get("status"),
            "sector": row.get("sector"),
            "quality_score": row.get("quality_score"),
            "trigger_score": row.get("trigger_score"),
            "why": (
                f"{row.get('status')} · quality {row.get('quality_score')}/16 · "
                f"triggers {row.get('trigger_score')}/10"
            ),
            "red_flags": row.get("red_flags") or [],
            "firm_order_to_revenue": row.get("firm_order_to_revenue"),
            "pending_order_to_revenue": row.get("pending_order_to_revenue"),
        })
    return cards


def build_decision_desk(*, limit: int = 8) -> dict[str, Any]:
    """Cache-only review packet. Does not fetch prices or call an LLM."""
    from quant_layer.order_book_screener import load_order_book_screen
    from quant_layer.pipeline import load_cached_shortlist

    report = _latest_snapshot() or {}
    screen = load_order_book_screen()
    technical = _technical_cards(report, limit=limit)
    if not technical:
        cached = load_cached_shortlist() or {}
        for row in (cached.get("shortlist") or [])[:limit]:
            technical.append({
                "symbol": row.get("symbol"),
                "decision": "review",
                "conviction": None,
                "why": f"{row.get('trigger_count') or 0} technical triggers",
                "conflicts": [],
                "triggers": (row.get("triggers_fired") or [])[:6],
                "composite_score": row.get("trigger_count"),
            })
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "decision_support",
        "human_checkpoint": True,
        "auto_execute": False,
        "headline": "Review these names. Nothing here places an order.",
        "technical_reviews": technical,
        "order_book_watchlist": _order_cards(screen, limit=limit),
        "order_book_rejected": (screen or {}).get("rejected") or [],
        "regime": (report.get("regime") or {}).get("regime"),
        "conflicts": report.get("conflicts") or [],
    }
