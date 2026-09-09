"""Calibration ranking, symbol win-rate, and trailing stop."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from trading.agent_picker import _calibration_base_score, _score_screen_row
from trading.decision_rationale import build_sell_rationale
from trading.pick_learning import symbol_pick_stats, symbol_win_rate_adjustment


def test_calibration_base_score_uses_weights():
    row = {
        "symbol": "TEST.NSE",
        "composite_score": 70,
        "horizon_return_pct": 3.0,
        "supertrend_dir": 1,
        "golden_cross": True,
        "quality_score": 80,
        "rsi_14": 55,
    }
    weights = {
        "technicals": 0.4,
        "composite": 0.3,
        "horizons": 0.1,
        "competitive": 0.1,
        "news": 0.1,
    }
    with patch("trading.autopilot.load_calibration", return_value={"weights": weights}):
        base, meta = _calibration_base_score(row)
    assert base > 0
    assert meta.get("calibration_factors")
    assert meta["calibration_factors"]["composite"] == 70


def test_score_screen_row_includes_symbol_win_rate():
    row = {
        "symbol": "WIN.NSE",
        "composite_score": 60,
        "stance": "favorable",
        "price": 100,
    }
    with patch("trading.autopilot.load_calibration", return_value={"weights": {}}):
        with patch("trading.agent_picker._rag_score_adjustment", return_value=0.0):
            with patch("trading.pick_learning.symbol_win_rate_adjustment", return_value=4.0):
                scored = _score_screen_row(row, target_pct=2.0)
    assert any("symbol_wr" in r for r in scored["reasons"])
    assert scored["pick_score"] >= 34


def test_symbol_win_rate_adjustment_from_log(tmp_path, monkeypatch):
    log = {
        "picks": [
            {"symbol": "ABC.NSE", "outcome": {"pnl_inr": 500}},
            {"symbol": "ABC.NSE", "outcome": {"pnl_inr": 300}},
            {"symbol": "ABC.NSE", "outcome": {"pnl_inr": -200}},
        ]
    }
    log_path = tmp_path / "pick_log.json"
    log_path.write_text(json.dumps(log), encoding="utf-8")
    monkeypatch.setattr("trading.pick_learning.LOG_PATH", log_path)
    stats = symbol_pick_stats("ABC.NSE")
    assert stats["total"] == 3
    assert stats["wins"] == 2
    adj = symbol_win_rate_adjustment("ABC.NSE")
    assert adj > 0


def test_trailing_stop_rationale():
    rat = build_sell_rationale(
        symbol="X.NSE",
        entry_price=100,
        exit_price=101.2,
        quantity=10,
        trigger="trailing_stop",
        target_pct=2.0,
        stop_pct=1.0,
        trailing_peak_ret_pct=1.8,
        trailing_stop_pct=0.5,
    )
    assert rat["trigger"] == "trailing_stop"
    assert "Trailing exit" in rat["thought_process"]


def test_update_trailing_peak_arms_and_tracks(tmp_path, monkeypatch):
    from trading import paper_ledger

    ledger = tmp_path / "ledger.json"
    daily = tmp_path / "daily.json"
    monkeypatch.setattr(paper_ledger, "LEDGER_PATH", ledger)
    monkeypatch.setattr(paper_ledger, "DAILY_PATH", daily)
    paper_ledger.record_paper_order(
        payload={"symbol": "T.NSE", "side": "buy", "quantity": 10, "product": "mis"},
        fill_price=100.0,
    )
    state = paper_ledger.update_trailing_peak("T.NSE", 101.5, arm_pct=1.0)
    assert state["trailing_armed"] is True
    assert state["peak_ret_pct"] >= 1.0
    state2 = paper_ledger.update_trailing_peak("T.NSE", 102.0, arm_pct=1.0)
    assert state2["peak_price"] == 102.0
