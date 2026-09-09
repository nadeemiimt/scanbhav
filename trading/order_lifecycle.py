"""Poll broker for fill confirmation."""
from __future__ import annotations

import time
from typing import Any

from brokers.service import get_order_status
from trading.order_book import append_event, update_pending


_FILLED = {"complete", "completed", "filled", "traded", "success", "executed"}
_REJECTED = {"rejected", "cancelled", "canceled", "failed", "error"}


def is_filled_status(status: str) -> bool:
    s = (status or "").lower()
    return s in _FILLED or "complete" in s


def is_rejected_status(status: str) -> bool:
    s = (status or "").lower()
    return s in _REJECTED


def poll_order_fill(
    broker_id: str,
    broker_order_id: str,
    *,
    max_attempts: int = 8,
    delay_seconds: float = 0.75,
) -> dict[str, Any]:
    last: dict[str, Any] = {}
    for _ in range(max_attempts):
        last = get_order_status(broker_id, broker_order_id)
        status = str(last.get("status") or "")
        if is_filled_status(status):
            update_pending(broker_order_id, status="filled", fill=last)
            append_event({"type": "fill", "broker_order_id": broker_order_id, "status": status, "fill": last})
            return {"confirmed": True, "status": status, **last}
        if is_rejected_status(status):
            update_pending(broker_order_id, status="rejected", fill=last)
            append_event({"type": "reject", "broker_order_id": broker_order_id, "status": status, "fill": last})
            return {"confirmed": False, "rejected": True, "status": status, **last}
        time.sleep(delay_seconds)
    update_pending(broker_order_id, status="pending_poll_timeout", last_poll=last)
    return {"confirmed": False, "pending": True, "status": last.get("status"), **last}


def poll_all_pending(broker_id: str) -> list[dict[str, Any]]:
    from trading.order_book import list_pending

    results = []
    for row in list_pending():
        oid = str(row.get("broker_order_id") or "")
        if oid:
            results.append(poll_order_fill(broker_id, oid, max_attempts=3, delay_seconds=0.5))
    return results
