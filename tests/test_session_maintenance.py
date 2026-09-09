"""Tests for session store trimming."""
from trading.session_maintenance import slim_event_detail, slim_cycle_record


def test_slim_event_detail_strips_universe_audit():
    event = {
        "type": "cycle_complete",
        "detail": {
            "cycle_id": "cy-1",
            "universe_audit": [{"symbol": "A"}] * 50,
            "realized_pnl_inr": 100.0,
        },
    }
    out = slim_event_detail(event)
    assert "universe_audit" not in out["detail"]
    assert out["detail"].get("universe_audit_count") == 50
    assert out["detail"].get("realized_pnl_inr") == 100.0


def test_slim_cycle_record():
    cycle = {
        "id": "c1",
        "at": "2026-08-14T10:00:00+00:00",
        "universe_audit": [{"symbol": "X"}] * 20,
        "pick_result": {"trades": [1, 2], "picks": [3]},
    }
    out = slim_cycle_record(cycle)
    assert out.get("universe_audit_count") == 20
    assert "universe_audit" not in out
    assert out.get("trades_attempted") == 2
