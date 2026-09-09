"""Agent 4 — ATR-based position sizing."""
from __future__ import annotations

from typing import Any, Optional


def position_size_from_atr(
    *,
    account_risk_inr: float,
    entry_price: float,
    atr_14: float,
    stop_atr_mult: float = 2.0,
    max_notional_inr: Optional[float] = None,
) -> dict[str, Any]:
    if entry_price <= 0 or atr_14 <= 0 or account_risk_inr <= 0:
        return {"quantity": 0, "stop_price": None, "risk_per_share": None}
    stop_price = entry_price - stop_atr_mult * atr_14
    risk_per_share = entry_price - stop_price
    if risk_per_share <= 0:
        return {"quantity": 0, "stop_price": stop_price, "risk_per_share": risk_per_share}
    qty = int(account_risk_inr / risk_per_share)
    if max_notional_inr and qty * entry_price > max_notional_inr:
        qty = int(max_notional_inr / entry_price)
    return {
        "quantity": max(0, qty),
        "stop_price": round(stop_price, 2),
        "target_price": round(entry_price + 2 * risk_per_share, 2),
        "risk_per_share": round(risk_per_share, 2),
        "notional_inr": round(qty * entry_price, 2),
    }


def attach_position_sizes(
    ranked: list[dict[str, Any]],
    *,
    account_risk_inr: float,
    max_notional_inr: float,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in ranked:
        payload = (row.get("quant") or {}).get("payload") or row.get("payload") or row
        price = float(payload.get("close_adj") or payload.get("price") or 0)
        atr_pct = float(payload.get("atr_pct") or 1.5)
        atr_14 = price * atr_pct / 100.0 if price else 0
        sizing = position_size_from_atr(
            account_risk_inr=account_risk_inr,
            entry_price=price,
            atr_14=atr_14,
            max_notional_inr=max_notional_inr,
        )
        merged = dict(row)
        merged["position_sizing"] = sizing
        out.append(merged)
    return out
