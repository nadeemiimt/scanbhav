"""Tests for ATR sizing, timing windows, top-up guard."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from trading.intraday_rules import risk_per_trade_inr, size_by_atr_risk
from trading.timing_intelligence import timing_gate_allows


def test_atr_risk_sizing_reduces_qty_on_high_vol():
    # ₹100 stock, 4% ATR → effective stop 2% → qty for ₹3500 risk = 3500/(100*0.02) = 1750
    sized = size_by_atr_risk(
        100.0,
        atr_pct=4.0,
        stop_pct=1.0,
        risk_inr=3500,
        max_per_order_inr=300_000,
        remaining_budget_inr=3_000_000,
    )
    assert sized is not None
    assert sized["sizing_method"] == "atr_risk"
    assert sized["quantity"] == 1750
    assert sized["risk_at_stop_inr"] <= 3600


def test_atr_risk_caps_at_max_per_order():
    sized = size_by_atr_risk(
        50.0,
        atr_pct=2.0,
        stop_pct=1.0,
        risk_inr=50_000,
        max_per_order_inr=100_000,
        remaining_budget_inr=500_000,
    )
    assert sized is not None
    assert sized["notional_inr"] <= 100_000


def test_risk_per_trade_derived_from_session_loss():
    ap = {"max_concurrent_picks": 8, "risk_per_trade_inr": 0}
    risk = {"max_intraday_loss_inr": 80_000}
    assert risk_per_trade_inr(ap, risk) == 10_000.0


def test_midday_entries_blocked_with_preferred_windows():
    ap = {
        "timing_intel_enabled": True,
        "timing_gate_auto_trades": True,
        "timing_adaptive_loosen": False,
        "timing_preferred_windows_only": True,
        "timing_preferred_window_ids": ["open_drive", "morning_trend"],
    }
    midday_window = {
        "id": "midday",
        "label": "Mid session",
        "auto_trade": True,
        "market_open": True,
    }
    with patch("trading.config_store.load_trading_config", return_value={"autopilot": ap}), patch(
        "trading.timing_intelligence.current_session_window", return_value=midday_window
    ):
        gate = timing_gate_allows("buy", symbol="TEST.NSE")
    assert gate["allowed"] is False
    assert gate["reason"] == "outside_preferred_window_midday"


def test_morning_trend_allowed():
    ap = {
        "timing_intel_enabled": True,
        "timing_gate_auto_trades": True,
        "timing_adaptive_loosen": False,
        "timing_preferred_windows_only": True,
        "timing_preferred_window_ids": ["open_drive", "morning_trend"],
    }
    morning = {
        "id": "morning_trend",
        "label": "Morning trend",
        "auto_trade": True,
        "market_open": True,
    }
    with patch("trading.config_store.load_trading_config", return_value={"autopilot": ap}), patch(
        "trading.timing_intelligence.current_session_window", return_value=morning
    ):
        gate = timing_gate_allows("buy", symbol="TEST.NSE")
    assert gate["allowed"] is True


def test_top_up_guard_blocks_flat_position():
    from trading.agent_picker import _top_up_open_positions, _position_age_minutes

    pos = {
        "symbol": "FLAT.NSE",
        "quantity": 100,
        "avg_price": 200.0,
        "opened_at": (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat(),
    }
    assert _position_age_minutes(pos) >= 15

    limits = {
        "max_per_order_inr": 300_000,
        "remaining_budget_inr": 1_000_000,
        "held_symbols": {"FLAT.NSE"},
        "max_daily_notional_inr": 3_000_000,
        "buy_notional_used_inr": 0,
        "halted": False,
    }
    ap = {
        "top_up_guard_enabled": True,
        "top_up_min_profit_pct": 0.5,
        "top_up_min_minutes": 10,
        "top_up_max_fraction": 0.25,
        "top_up_max_daily_pct": 0.85,
    }
    with patch("trading.config_store.load_trading_config", return_value={"autopilot": ap, "risk": {}}), patch(
        "trading.agent_picker.open_positions", return_value=[pos]
    ), patch("trading.agent_picker.load_morning_scan", return_value={}), patch(
        "trading.scheduler._quote_symbol", return_value=200.5
    ):
        trades = _top_up_open_positions(
            limits=limits,
            target_pct=2.0,
            execute=False,
            session_id="sess-1",
        )
    assert len(trades) == 1
    assert trades[0].get("reason") == "top_up_guard_no_momentum"
