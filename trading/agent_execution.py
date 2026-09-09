"""Agent execution hook after research completes."""
from __future__ import annotations

from typing import Any, Optional

from trading.config_store import load_trading_config
from trading.order_router import agent_trade_from_signal


def maybe_execute_agent_trade(
    *,
    symbol: str,
    insight: dict[str, Any],
    ratings: dict[str, Any],
    execute: bool = False,
    quantity: int = 1,
) -> Optional[dict[str, Any]]:
    """If enabled, map agent stance to a paper/live MIS order (risk-capped)."""
    if not execute:
        return None
    cfg = load_trading_config()
    ap = cfg.get("autopilot") or {}
    if not ap.get("enabled") and not execute:
        return None

    stance = str(insight.get("stance") or ratings.get("composite_stance") or "neutral")
    composite = ratings.get("composite_score")
    side = "buy" if stance.lower() in {"bullish", "constructive", "favorable", "strong_favorable"} else "sell"

    if side == "sell":
        from trading.paper_ledger import open_positions
        if not any(p.get("symbol") == symbol.upper() for p in open_positions("mis")):
            return {"skipped": True, "reason": "no_position_to_sell"}

    min_score = float((cfg.get("risk") or {}).get("agent_min_composite") or ap.get("entry_min_composite") or 55)
    if side == "buy" and composite is not None and float(composite) < min_score:
        return {"skipped": True, "reason": "min_composite", "composite_score": composite, "min_required": min_score}

    return agent_trade_from_signal(
        symbol=symbol,
        side=side,
        quantity=max(1, quantity),
        stance=stance,
        composite_score=float(composite) if composite is not None else None,
        product=str(cfg.get("default_product") or "mis"),
        source="genai_agent",
    )
