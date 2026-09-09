"""Trading subsystem health — stream, token, reconcile, scheduler."""
from __future__ import annotations

from typing import Any

from brokers.config import load_broker_env
from brokers.ltp_stream import ltp_stream_status
from brokers.service import get_adapter
from brokers.token_store import token_health
from trading.config_store import load_trading_config
from trading.order_book import list_pending, recent_events
from trading.paper_ledger import is_trading_halted, ledger_summary
from trading.reconcile import reconcile_broker_positions


def trading_health(*, run_reconcile: bool = False) -> dict[str, Any]:
    cfg = load_trading_config()
    env = load_broker_env()
    bid = str(cfg.get("default_broker") or env.default_broker or "stub").lower()
    halted, halt_reason = is_trading_halted()
    adapter = get_adapter(bid)
    broker_st = adapter.status()
    token = token_health(bid)

    reconcile_result = None
    if run_reconcile:
        try:
            reconcile_result = reconcile_broker_positions(broker_id=bid)
        except Exception as exc:
            reconcile_result = {"error": str(exc)}

    ready_live = (
        cfg.get("execution_mode") == "live"
        and cfg.get("live_armed")
        and broker_st.get("configured")
        and token.get("ok")
        and not halted
        and bid != "stub"
    )

    return {
        "execution_mode": cfg.get("execution_mode"),
        "live_armed": cfg.get("live_armed"),
        "ready_for_live": ready_live,
        "halted": halted,
        "halt_reason": halt_reason,
        "broker": bid,
        "broker_status": broker_st,
        "token": token,
        "ltp_stream": ltp_stream_status(),
        "ledger": ledger_summary(),
        "pending_orders": len(list_pending()),
        "recent_events": recent_events(15),
        "reconcile": reconcile_result,
        "autopilot_enabled": (cfg.get("autopilot") or {}).get("enabled"),
        "checks": {
            "broker_configured": broker_st.get("configured"),
            "token_valid": token.get("ok"),
            "stream_running": ltp_stream_status().get("running"),
            "not_halted": not halted,
        },
    }
