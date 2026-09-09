"""Unified intraday edge score — single number with explainable factors."""
from __future__ import annotations

from typing import Any

from trading.agent_selection import agent_selection_cfg, intraday_edge_score


def compute_unified_edge_score(
    row: dict[str, Any],
    *,
    target_pct: float,
    ist_mins: int | None = None,
    curated_symbols: set[str] | None = None,
) -> dict[str, Any]:
    """
    One edge_score for agent ranking: quant + TA + calibration + learning inputs.
    PDF Layer 1/2 outputs remain available on the row; this merges them for Auto Pick.
    """
    cfg = agent_selection_cfg()
    from trading.agent_selection import ist_minutes_now

    ist_mins = ist_mins if ist_mins is not None else ist_minutes_now()
    edge, edge_reasons, edge_meta = intraday_edge_score(
        row, target_pct=target_pct, cfg=cfg, ist_mins=ist_mins,
    )

    learn_adj = 0.0
    learn_meta: dict[str, Any] = {}
    learn_reasons: list[str] = []
    try:
        from trading.agent_learning import agent_learning_score

        curated = {str(s or "").upper().replace(".NSE", "") for s in (curated_symbols or set())}
        learn_adj, learn_meta, learn_reasons = agent_learning_score(
            row, curated_symbols=curated, ist_mins=ist_mins,
        )
    except Exception:
        pass

    total = round(edge + learn_adj, 2)
    return {
        "edge_score": total,
        "edge_base": edge,
        "learning_adj": learn_adj,
        "factors": {
            **edge_meta,
            "edge_reasons": edge_reasons,
            "learning": learn_meta,
            "learning_reasons": learn_reasons,
            "composite_score": row.get("composite_score"),
            "quant_triggers": (row.get("quant_triggers") or [])[:8],
            "quant_trigger_count": row.get("quant_trigger_count"),
        },
    }
