"""Tests for time-decay exits and late-session rules."""
from trading.intraday_rules import (
    conviction_risk_multiplier,
    dynamic_target_pct,
    effective_exit_rules,
    estimate_daily_profit_ceiling,
    late_buy_blocked,
    no_buy_after_minute,
)
from trading.entry_gates import evaluate_stop_cooldown, record_stop_cooldown


def test_late_buy_blocked_after_cutoff():
    ap = {"no_buy_after_minute_ist": 14 * 60 + 30}
    blocked, reason = late_buy_blocked(ap, ist_mins=14 * 60 + 45)
    assert blocked is True
    assert reason == "late_session_no_buy"
    blocked, _ = late_buy_blocked(ap, ist_mins=10 * 60 + 30)
    assert blocked is False


def test_effective_exit_tightens_in_power_hour():
    ap = {
        "target_pct": 2.0,
        "trailing_stop_arm_pct": 1.0,
        "trailing_stop_pct": 0.5,
        "power_hour_start_minute_ist": 14 * 60 + 30,
        "late_tighten_minute_ist": 15 * 60,
    }
    morning = effective_exit_rules(ap, ist_mins=10 * 60 + 30)
    power = effective_exit_rules(ap, ist_mins=14 * 60 + 45)
    late = effective_exit_rules(ap, ist_mins=15 * 60 + 5)
    assert morning["target_pct"] == 2.0
    assert power["target_pct"] == 1.0
    assert late["target_pct"] == 0.8
    assert late["trail_arm_pct"] < morning["trail_arm_pct"]


def test_scale_out_pct_defaults_to_half_target():
    ap = {"target_pct": 2.0, "partial_scale_out_pct": 0}
    rules = effective_exit_rules(ap, ist_mins=10 * 60)
    assert rules["scale_out_pct"] == 1.0


def test_profitable_exit_does_not_block_rebuy(tmp_path, monkeypatch):
    block_path = tmp_path / "blocks.json"
    monkeypatch.setattr("trading.entry_gates.COOLDOWN_PATH", block_path)
    record_stop_cooldown(symbol="WIN.NSE", reason="target_hit", ret_pct=1.8)
    gate = evaluate_stop_cooldown("WIN.NSE")
    assert gate["allowed"] is True


def test_stop_hit_still_blocks_rebuy(tmp_path, monkeypatch):
    block_path = tmp_path / "blocks.json"
    monkeypatch.setattr("trading.entry_gates.COOLDOWN_PATH", block_path)
    record_stop_cooldown(symbol="LOSS.NSE", reason="stop_hit", ret_pct=-1.1)
    gate = evaluate_stop_cooldown("LOSS.NSE")
    assert gate["allowed"] is False


def test_dynamic_target_home_run_for_small_cap():
    ap = {"target_pct": 2.0, "dynamic_target_enabled": True, "home_run_target_pct": 5.0}
    row = {"bucket": "small", "atr_pct": 4.5}
    assert dynamic_target_pct(row, ap) == 5.0


def test_conviction_multiplier_on_high_edge():
    ap = {"conviction_sizing_enabled": True, "conviction_edge_threshold": 75, "conviction_risk_multiplier": 2.0}
    assert conviction_risk_multiplier({"edge_score": 80}, ap) == 2.0
    assert conviction_risk_multiplier({"edge_score": 60}, ap) == 1.0


def test_profit_ceiling_estimate():
    est = estimate_daily_profit_ceiling(
        max_positions=8, avg_notional_inr=400_000, avg_target_pct=3.5, win_rate=0.45
    )
    assert est["estimated_net_inr"] > 30_000
