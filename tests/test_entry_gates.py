"""Entry gates: RAG repeat-loser block, stop/same-day cooldown."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from trading.entry_gates import (
    evaluate_entry_gates,
    evaluate_rag_buy_gate,
    evaluate_stop_cooldown,
    record_stop_cooldown,
)


def test_stop_cooldown_blocks_same_day_rebuy(tmp_path, monkeypatch):
    block_path = tmp_path / "blocks.json"
    monkeypatch.setattr("trading.entry_gates.COOLDOWN_PATH", block_path)
    record_stop_cooldown(symbol="ABC.NSE", reason="stop_hit", session_id="sess-1")
    gate = evaluate_stop_cooldown("ABC.NSE")
    assert gate["allowed"] is False
    assert gate["reason"] == "stop_cooldown_same_day"


def test_rag_blocks_repeat_loser(tmp_path, monkeypatch):
    log_path = tmp_path / "pick_log.json"
    log_path.write_text(
        json.dumps({
            "picks": [
                {"symbol": "LOSER.NSE", "outcome": {"pnl_inr": -100}},
                {"symbol": "LOSER.NSE", "outcome": {"pnl_inr": -200}},
                {"symbol": "LOSER.NSE", "outcome": {"pnl_inr": -50}},
            ]
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr("trading.pick_learning.LOG_PATH", log_path)
    with patch("trading.pick_learning.retrieve_pick_lessons", return_value=[
        {"stance": "loss", "text": "autopilot loss on LOSER"},
        {"stance": "loss", "text": "repeat loser"},
    ]):
        gate = evaluate_rag_buy_gate("LOSER.NSE")
    assert gate["allowed"] is False
    assert gate["reason"] == "rag_repeat_loser"


def test_entry_gates_pass_when_clear(tmp_path, monkeypatch):
    block_path = tmp_path / "blocks.json"
    monkeypatch.setattr("trading.entry_gates.COOLDOWN_PATH", block_path)
    with patch("trading.pick_learning.retrieve_agent_lessons", return_value=[]), patch(
        "trading.pick_learning.symbol_pick_stats", return_value={"losses": 0, "total": 0},
    ):
        gate = evaluate_entry_gates("NEW.NSE")
    assert gate["allowed"] is True


def test_rag_curated_desk_can_disable_block(tmp_path, monkeypatch):
    log_path = tmp_path / "pick_log.json"
    log_path.write_text(
        json.dumps({
            "picks": [
                {"symbol": "LOSER.NSE", "outcome": {"pnl_inr": -100}},
                {"symbol": "LOSER.NSE", "outcome": {"pnl_inr": -200}},
                {"symbol": "LOSER.NSE", "outcome": {"pnl_inr": -50}},
            ]
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr("trading.pick_learning.LOG_PATH", log_path)
    with patch("trading.config_store.load_trading_config", return_value={
        "autopilot": {"rag_block_repeat_losers_curated": False, "rag_block_repeat_losers": True},
    }):
        gate = evaluate_rag_buy_gate("LOSER.NSE", pick_mode="curated_list")
    assert gate["allowed"] is True
    assert gate["reason"] == "rag_block_disabled"


def test_run_all_session_cycles_parallel(monkeypatch):
    import time
    from trading.session_autopilot import run_all_session_cycles

    calls: list[str] = []

    def fake_cycle(*, analyze_fn, quote_fn, session):
        sid = session["id"]
        calls.append(sid)
        time.sleep(0.05 if sid == "slow" else 0.01)
        return {"session_id": sid, "pick_mode": session.get("pick_mode")}

    monkeypatch.setattr("trading.session_autopilot.run_session_cycle", fake_cycle)
    monkeypatch.setattr(
        "trading.session_autopilot._active_sessions",
        lambda _data: [
            {"id": "slow", "pick_mode": "agent_auto"},
            {"id": "fast", "pick_mode": "curated_list"},
        ],
    )
    monkeypatch.setattr("trading.session_autopilot._load_store", lambda: {"sessions": []})

    out = run_all_session_cycles(analyze_fn=lambda s: {}, quote_fn=lambda s: 1.0)
    assert out["parallel"] is True
    assert out["session_count"] == 2
    assert {c["session_id"] for c in out["cycles"]} == {"slow", "fast"}
    assert len(calls) == 2


def test_per_session_paper_ledger_isolation(tmp_path, monkeypatch):
    from trading import paper_ledger

    ledger = tmp_path / "ledger.json"
    daily = tmp_path / "daily.json"
    monkeypatch.setattr(paper_ledger, "LEDGER_PATH", ledger)
    monkeypatch.setattr(paper_ledger, "DAILY_PATH", daily)

    paper_ledger.record_paper_order(
        payload={"symbol": "X.NSE", "side": "buy", "quantity": 10, "product": "mis", "session_id": "desk-a"},
        fill_price=100.0,
    )
    paper_ledger.record_paper_order(
        payload={"symbol": "X.NSE", "side": "buy", "quantity": 5, "product": "mis", "session_id": "desk-b"},
        fill_price=200.0,
    )
    a_pos = paper_ledger.open_positions("mis", session_id="desk-a")
    b_pos = paper_ledger.open_positions("mis", session_id="desk-b")
    assert len(a_pos) == 1
    assert len(b_pos) == 1
    assert a_pos[0]["quantity"] == 10
    assert b_pos[0]["quantity"] == 5
    assert float(a_pos[0]["avg_price"]) == 100.0
    assert float(b_pos[0]["avg_price"]) == 200.0
