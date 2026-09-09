"""Trade journal outcome wiring."""
from __future__ import annotations

from quant_layer.trade_journal import _load, _save, log_signal, record_outcome


def test_record_outcome_closes_open_signal():
    log_signal(
        symbol="TEST.NSE",
        conviction_score=7.5,
        validation_score=4.0,
        triggers=["rsi_oversold_bounce"],
        rationale="unit test",
        source="test",
    )
    updated = record_outcome("TEST.NSE", pnl_inr=1500.0, outcome="win")
    assert updated == 1
    data = _load()
    closed = [e for e in data.get("entries") or [] if e.get("symbol") == "TEST.NSE" and e.get("outcome")]
    assert closed
    assert closed[-1]["outcome_pnl_inr"] == 1500.0
    assert closed[-1]["outcome"] == "win"
