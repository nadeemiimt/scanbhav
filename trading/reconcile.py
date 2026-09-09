"""Reconcile broker positions vs local shadow ledger."""
from __future__ import annotations

from typing import Any

from brokers.service import get_positions
from trading.config_store import load_trading_config
from trading.paper_ledger import mark_trading_halted, sync_positions_from_broker


def _index_positions(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        sym = str(row.get("symbol") or "").upper()
        prod = str(row.get("product") or "mis").lower()
        key = f"{sym}:{prod}"
        out[key] = row
    return out


def reconcile_broker_positions(*, broker_id: str | None = None, product: str = "mis") -> dict[str, Any]:
    cfg = load_trading_config()
    if not cfg.get("reconcile_enabled", True):
        return {"skipped": True, "reason": "reconcile_disabled"}

    bid = (broker_id or cfg.get("default_broker") or "stub").lower()
    if bid == "stub":
        return {"skipped": True, "reason": "stub_broker"}

    pack = get_positions(bid, product=product)
    broker_rows = pack.get("positions") or []
    errors = pack.get("errors") or []

    from trading.paper_ledger import open_positions

    shadow = open_positions(product)
    broker_idx = _index_positions(broker_rows)
    shadow_idx = _index_positions(shadow)

    drift: list[dict[str, Any]] = []
    for key, brow in broker_idx.items():
        srow = shadow_idx.get(key)
        bqty = int(brow.get("quantity") or 0)
        sqty = int((srow or {}).get("quantity") or 0)
        if abs(bqty - sqty) > 0:
            drift.append({
                "symbol": brow.get("symbol"),
                "product": product,
                "broker_qty": bqty,
                "shadow_qty": sqty,
                "broker_avg": brow.get("avg_price"),
                "shadow_avg": (srow or {}).get("avg_price"),
            })

    for key, srow in shadow_idx.items():
        if key not in broker_idx:
            drift.append({
                "symbol": srow.get("symbol"),
                "product": product,
                "broker_qty": 0,
                "shadow_qty": int(srow.get("quantity") or 0),
                "ghost_shadow": True,
            })

    synced = sync_positions_from_broker(broker_rows, product=product)

    halt_on_drift = cfg.get("halt_on_reconcile_drift", True)
    if drift and halt_on_drift and cfg.get("execution_mode") == "live" and cfg.get("live_armed"):
        mark_trading_halted("reconcile_drift", f"Position drift detected ({len(drift)} mismatches).")

    return {
        "broker": bid,
        "product": product,
        "broker_positions": len(broker_rows),
        "shadow_before": len(shadow),
        "drift": drift,
        "drift_count": len(drift),
        "synced": synced,
        "errors": errors,
        "halted_on_drift": bool(drift and halt_on_drift),
    }
