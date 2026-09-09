"""Tests for profit profile presets."""
import pytest

from trading.profit_profiles import (
    PROFILES,
    active_profit_profile_name,
    apply_profit_profile,
    list_profit_profiles,
)


def test_list_profiles_has_both_modes():
    profiles = list_profit_profiles()
    ids = {p["id"] for p in profiles}
    assert ids == {"conservative", "home_run"}
    home = next(p for p in profiles if p["id"] == "home_run")
    assert home["estimate"]["typical_net_inr"] > 50_000


def test_apply_conservative_profile(tmp_path, monkeypatch):
    from trading import config_store

    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(config_store, "CONFIG_PATH", cfg_path)
    result = apply_profit_profile("conservative")
    assert result["profile"] == "conservative"
    cfg = result["config"]
    assert cfg["risk"]["max_position_inr"] == 300_000
    assert cfg["autopilot"]["risk_per_trade_inr"] == 3500
    assert active_profit_profile_name(cfg) == "conservative"


def test_apply_home_run_preserves_dual_desk_symbols(tmp_path, monkeypatch):
    from trading import config_store

    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(config_store, "CONFIG_PATH", cfg_path)
    config_store.save_trading_config({
        "autopilot": {
            "dual_desk_preferences": {
                "curated": {"symbols": ["SHILPAMED.NSE", "DIACABS.NSE"]},
                "agent": {"max_spend_inr": 3_000_000},
            }
        }
    })
    result = apply_profit_profile("home_run")
    dual = result["config"]["autopilot"]["dual_desk_preferences"]
    assert dual["curated"]["symbols"] == ["SHILPAMED.NSE", "DIACABS.NSE"]
    assert dual["agent"]["max_profit_inr"] == 150_000
    assert dual["curated"]["max_profit_inr"] == 150_000
    assert result["config"]["risk"]["max_position_inr"] == 500_000


def test_unknown_profile_raises():
    with pytest.raises(ValueError, match="Unknown"):
        apply_profit_profile("yolo")
