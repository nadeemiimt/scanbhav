"""Tests for home run day recommendation."""
from unittest.mock import patch

from trading.home_run_advisor import recommend_home_run_day


def _favorable_scan():
    rows = []
    for i in range(10):
        rows.append({
            "bucket": "small",
            "atr_pct": 4.2,
            "stance": "strong_favorable",
            "composite_score": 85,
        })
    for i in range(30):
        rows.append({
            "bucket": "mid" if i % 2 else "large",
            "atr_pct": 3.0,
            "stance": "favorable",
        })
    return {
        "trade_date_ist": "2026-08-14",
        "scored": 500,
        "bullish_count": 310,
        "rows": rows,
    }


def test_strong_home_run_recommendation():
    window = {"id": "open_drive", "label": "Opening drive", "market_open": True}
    nse = {"phase": "trading", "ist_time": "09:25 IST"}
    with patch("trading.home_run_advisor.load_morning_scan", return_value=_favorable_scan()), patch(
        "trading.home_run_advisor._today_ist", return_value="2026-08-14"
    ), patch("trading.timing_intelligence.current_session_window", return_value=window), patch(
        "trading.market_hours.nse_session_info", return_value=nse
    ), patch("trading.profit_profiles.active_profit_profile_name", return_value="conservative"):
        rec = recommend_home_run_day({"autopilot": {}})
    assert rec["score"] >= 65
    assert rec["recommendation"] in {"home_run", "consider_home_run"}
    assert rec["reasons"]


def test_midday_caution_lowers_score():
    scan = _favorable_scan()
    nse = {"phase": "trading", "ist_time": "09:25 IST"}
    open_window = {"id": "open_drive", "label": "Opening drive", "market_open": True}
    midday_window = {"id": "midday", "label": "Mid session", "market_open": True}

    def run(window):
        with patch("trading.home_run_advisor.load_morning_scan", return_value=scan), patch(
            "trading.home_run_advisor._today_ist", return_value="2026-08-14"
        ), patch("trading.timing_intelligence.current_session_window", return_value=window), patch(
            "trading.market_hours.nse_session_info", return_value=nse
        ), patch("trading.profit_profiles.active_profit_profile_name", return_value="conservative"):
            return recommend_home_run_day({"autopilot": {}})

    open_rec = run(open_window)
    midday_rec = run(midday_window)
    assert open_rec["score"] > midday_rec["score"]
    assert "Midday" in " ".join(midday_rec.get("cautions") or [])


def test_auto_apply_home_run(tmp_path, monkeypatch):
    from trading import config_store
    from trading.home_run_advisor import auto_apply_profit_profile

    cfg_path = tmp_path / "config.json"
    state_path = tmp_path / "auto_state.json"
    monkeypatch.setattr(config_store, "CONFIG_PATH", cfg_path)
    monkeypatch.setattr("trading.home_run_advisor.AUTO_STATE_PATH", state_path)

    config_store.save_trading_config({"autopilot": {"profit_profile": "conservative", "auto_home_run_enabled": True}})

    rec = {
        "score": 80,
        "recommendation": "home_run",
        "headline": "Strong",
        "action": "Go",
        "reasons": [],
        "cautions": [],
        "signals": {"session_window": "open_drive"},
        "thresholds": {},
        "active_profile": "conservative",
        "aligned": False,
    }
    with patch("trading.home_run_advisor.recommend_home_run_day", return_value=rec):
        out = auto_apply_profit_profile(pick_mode="agent_auto", session_id="sess-1")
    assert out.get("applied") is True
    assert out.get("profile") == "home_run"
    assert config_store.load_trading_config()["autopilot"]["profit_profile"] == "home_run"


def test_auto_apply_respects_cooldown(tmp_path, monkeypatch):
    from trading import config_store
    from trading.home_run_advisor import auto_apply_profit_profile, _save_auto_state

    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(config_store, "CONFIG_PATH", cfg_path)
    monkeypatch.setattr("trading.home_run_advisor.AUTO_STATE_PATH", tmp_path / "auto_state.json")
    config_store.save_trading_config({"autopilot": {"profit_profile": "conservative", "auto_home_run_enabled": True}})
    _save_auto_state({
        "date_ist": "2026-08-14",
        "last_switch_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    })
    with patch("trading.home_run_advisor._today_ist", return_value="2026-08-14"), patch(
        "trading.home_run_advisor.recommend_home_run_day",
        return_value={"score": 90, "recommendation": "home_run", "signals": {}},
    ):
        out = auto_apply_profit_profile(pick_mode="agent_auto")
    assert out.get("reason") == "cooldown"
