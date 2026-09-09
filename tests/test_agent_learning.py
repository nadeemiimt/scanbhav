"""Tests for agent RAG learning layer."""
from trading.agent_learning import (
    agent_learning_score,
    agent_premarket_learn,
    learning_curve_adjustment,
    timing_profile_score,
)


def _row(**kwargs):
    base = {
        "symbol": "DIACABS.NSE",
        "composite_score": 82,
        "stance": "favorable",
        "price": 368,
        "atr_pct": 3.5,
        "horizon_return_pct": 5,
        "rsi_14": 55,
        "bucket": "small",
    }
    base.update(kwargs)
    return base


def test_curated_overlap_boost_in_learning_score():
    adj, meta, reasons = agent_learning_score(
        _row(),
        curated_symbols={"DIACABS"},
    )
    assert adj >= 18.0
    assert "curated_overlap" in reasons
    assert meta.get("learning_enabled") is True


def test_learning_curve_neutral_without_history():
    adj, meta = learning_curve_adjustment("UNKNOWN.NSE")
    assert adj == 0.0
    assert meta.get("pick_log", {}).get("total") == 0


def test_timing_profile_score_no_profile():
    score, reasons = timing_profile_score("UNKNOWN.NSE")
    assert score == 0.0
    assert reasons == []


def test_agent_premarket_learn_empty_rows():
    result = agent_premarket_learn([])
    assert result.get("skipped") is True


def test_agent_premarket_learn_picks_symbols(monkeypatch):
    monkeypatch.setattr(
        "trading.timing_intelligence.learn_timing_batch",
        lambda symbols, feed_rag=True: {"learned": len(symbols), "rag_chunks": len(symbols)},
    )
    rows = [_row(symbol="DIACABS.NSE"), _row(symbol="ACE.NSE", bucket="large", composite_score=70)]
    result = agent_premarket_learn(rows, curated_symbols=["DIACABS"], top_n=5)
    assert result.get("symbol_count", 0) >= 1
    assert "DIACABS" in result.get("symbols", [])
