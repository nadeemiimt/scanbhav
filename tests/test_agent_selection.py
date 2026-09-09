"""Tests for seasoned-trader agent selection."""
from trading.agent_selection import (
    agent_candidate_gate,
    cap_bucket,
    intraday_edge_score,
    rank_rows_for_agent,
    realistic_intraday_move_pct,
    select_diversified_picks,
)


def _row(**kwargs):
    base = {
        "symbol": "TEST.NSE",
        "composite_score": 85,
        "stance": "strong_favorable",
        "price": 100,
        "atr_pct": 3.5,
        "horizon_return_pct": 5.0,
        "rsi_14": 58,
        "bucket": "small",
        "pattern_bias": "bullish",
        "supertrend_dir": 1,
    }
    base.update(kwargs)
    return base


def test_cap_bucket_from_row():
    assert cap_bucket({"bucket": "mid"}) == "mid"
    assert cap_bucket({"price": 2500}) == "large"
    assert cap_bucket({"price": 800}) == "mid"
    assert cap_bucket({"price": 120}) == "small"


def test_low_atr_candidate_blocked():
    row = _row(atr_pct=1.2)
    allowed, reason = agent_candidate_gate(row, ist_mins=10 * 60 + 30)
    assert allowed is False
    assert "atr" in reason


def test_extended_rsi_blocked():
    row = _row(rsi_14=79)
    allowed, reason = agent_candidate_gate(row, ist_mins=10 * 60 + 30)
    assert allowed is False
    assert "rsi" in reason


def test_small_cap_scores_higher_than_low_vol_large():
    cfg = {
        "min_atr_pct": 2.0,
        "max_rsi_entry": 72,
        "min_rsi_entry": 35,
        "min_horizon_return_pct": 0.5,
        "min_quality_score": 0,
        "block_quality_fail": False,
        "cap_weights": {"small": 1.25, "mid": 1.12, "large": 0.88},
    }
    small = _row(bucket="small", atr_pct=4.5, horizon_return_pct=8.0)
    large = _row(bucket="large", atr_pct=2.1, horizon_return_pct=3.0, symbol="BANK.NSE")
    edge_small, _, _ = intraday_edge_score(small, target_pct=2.0, cfg=cfg, ist_mins=10 * 60 + 30)
    edge_large, _, _ = intraday_edge_score(large, target_pct=2.0, cfg=cfg, ist_mins=10 * 60 + 30)
    assert edge_small > edge_large


def test_late_session_blocks_new_buys():
    row = _row()
    allowed, reason = agent_candidate_gate(row, ist_mins=14 * 60 + 45)
    assert allowed is False
    assert reason == "agent_late_session_no_buy"


def test_realistic_move_shrinks_near_close():
    row = _row(atr_pct=4.0)
    morning = realistic_intraday_move_pct(row, target_pct=2.0, ist_mins=10 * 60 + 30)
    late = realistic_intraday_move_pct(row, target_pct=2.0, ist_mins=15 * 60 + 0)
    assert morning > late


def test_rank_prefers_high_atr_over_composite_order():
    rows = [
        _row(symbol="LOW.NSE", bucket="large", atr_pct=2.0, composite_score=100),
        _row(symbol="HIGH.NSE", bucket="small", atr_pct=5.5, composite_score=78),
    ]
    ranked = rank_rows_for_agent(rows, min_composite=52, held=set(), top_n=5, target_pct=2.0, ist_mins=10 * 60 + 30)
    assert ranked[0]["symbol"] == "HIGH.NSE"


def test_diversified_picks_caps_large():
    cfg = {"enabled": True, "max_large_picks": 1, "max_mid_picks": 5}
    candidates = [
        {"symbol": "L1.NSE", "cap_bucket": "large", "edge_score": 90, "expected_profit_inr": 5000},
        {"symbol": "L2.NSE", "cap_bucket": "large", "edge_score": 85, "expected_profit_inr": 4800},
        {"symbol": "S1.NSE", "cap_bucket": "small", "edge_score": 80, "expected_profit_inr": 4500},
    ]
    picks = select_diversified_picks(candidates, max_picks=2, cfg=cfg)
    syms = [p["symbol"] for p in picks]
    assert syms.count("L1.NSE") + syms.count("L2.NSE") <= 1
    assert "S1.NSE" in syms
