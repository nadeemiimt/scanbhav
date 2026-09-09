"""Trading mode, risk caps, autopilot settings (persisted locally)."""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from config import BASE_DIR, setting

CONFIG_PATH = BASE_DIR / "data" / "trading" / "config.json"

ExecutionMode = Literal["paper", "live"]

DEFAULT_CONFIG: dict[str, Any] = {
    "execution_mode": "paper",
    "live_armed": False,
    "default_broker": setting("BROKER_DEFAULT", "stub"),
    "default_product": "mis",
    "risk": {
        "max_orders_per_day": 5,
        "max_intraday_loss_inr": 5000.0,
        "max_profit_inr": 8000.0,
        "max_unrealized_loss_inr": 3000.0,
        "max_position_inr": 50000.0,
        "max_daily_notional_inr": 100000.0,
        "max_open_positions": 3,
        "symbol_whitelist": [],
        "block_live_without_arm": True,
        "halt_new_buys_on_profit": True,
        "auto_square_off_enabled": True,
        "agent_min_composite": 55.0,
        "default_stop_pct": 0.75,
        "default_target_pct": 1.5,
        "place_sl_m_at_entry": True,
    },
    "autopilot": {
        "enabled": False,
        "paper_autopilot": True,
        "watchlist_agent": True,
        "intraday_sim": False,
        "active_symbol": "",
        "poll_seconds": 120,
        "entry_min_composite": 55.0,
        "target_pct": 1.5,
        "stop_pct": 0.75,
        "trailing_stop_enabled": True,
        "trailing_stop_arm_pct": 1.0,
        "trailing_stop_pct": 0.5,
        "square_off_minute_ist": 15 * 60 + 20,
        "morning_scan_enabled": True,
        "morning_scan_hour_ist": 9,
        "morning_scan_minute_ist": 0,
        "nse_premarket_start_minute_ist": 9 * 60,
        "nse_market_open_minute_ist": 9 * 60 + 15,
        "nse_market_close_minute_ist": 15 * 60 + 30,
        "use_nse_calendar": True,
        "use_nse_live_status": True,
        "session_auto_stop_at_close": True,
        "session_park_for_next_day": False,
        "session_follow_nse_hours": True,
        "morning_scan_rag_top": 60,
        "agent_scan_top_n": 80,
        "agent_smart_selection": True,
        "agent_min_atr_pct": 2.0,
        "agent_max_rsi_entry": 72,
        "agent_min_rsi_entry": 35,
        "agent_min_horizon_return_pct": 0.5,
        "agent_min_quality_score": 0,
        "agent_block_quality_fail": False,
        "agent_no_buy_after_minute_ist": 10 * 60 + 30,
        "agent_learning_enabled": True,
        "agent_timing_learn_top_n": 30,
        "agent_deep_analyze_top_n": 20,
        "agent_rag_top_k": 5,
        "agent_curated_overlap_boost": 18.0,
        "agent_timing_window_boost": 8.0,
        "agent_timing_window_penalty": 6.0,
        "agent_learning_curve_weight": 1.0,
        "agent_min_pick_log_trades": 2,
        "agent_news_intel_enabled": True,
        "agent_news_enrich_top_n": 80,
        "agent_news_fast_rss": True,
        "agent_news_edge_weight": 1.0,
        "agent_news_min_headlines": 1,
        "agent_pattern_scoring_enabled": True,
        "quant_layer_enabled": True,
        "quant_shortlist_max": 30,
        "quant_llm_synthesis_enabled": False,
        "quant_llm_min_conviction": 4.0,
        "agent_pattern_edge_weight": 1.0,
        "agent_pattern_min_boost_score": 55.0,
        "agent_min_daily_profit_target_inr": 100_000,
        "agent_capital_inr": 3_000_000,
        "min_trade_notional_inr": 25_000,
        "agent_cap_weight_small": 1.25,
        "agent_cap_weight_mid": 1.12,
        "agent_cap_weight_large": 0.88,
        "agent_max_large_picks": 2,
        "agent_max_mid_picks": 5,
        "no_buy_after_minute_ist": 14 * 60 + 30,
        "power_hour_start_minute_ist": 14 * 60 + 30,
        "late_tighten_minute_ist": 15 * 60,
        "power_hour_target_pct": 1.0,
        "power_hour_trail_arm_pct": 0.6,
        "power_hour_trail_pct": 0.35,
        "late_target_pct": 0.8,
        "late_trail_arm_pct": 0.5,
        "late_trail_pct": 0.3,
        "power_hour_lock_min_pct": 0.4,
        "power_hour_lock_pullback_pct": 0.25,
        "partial_scale_out_enabled": True,
        "partial_scale_out_fraction": 0.5,
        "partial_scale_out_target_fraction": 0.5,
        "partial_scale_out_pct": 0,
        "atr_risk_sizing_enabled": True,
        "risk_per_trade_inr": 0,
        "ltp_guard_enabled": True,
        "ltp_guard_debounce_seconds": 3,
        "timing_preferred_windows_only": True,
        "timing_preferred_window_ids": ["open_drive", "morning_trend"],
        "top_up_guard_enabled": True,
        "top_up_min_profit_pct": 0.5,
        "top_up_min_minutes": 10,
        "dynamic_target_enabled": True,
        "home_run_target_pct": 5.0,
        "extended_target_pct": 3.5,
        "home_run_min_atr_pct": 3.5,
        "conviction_sizing_enabled": True,
        "conviction_edge_threshold": 75,
        "conviction_risk_multiplier": 2.0,
        "momentum_pyramid_min_pct": 1.0,
        "momentum_pyramid_fraction": 0.5,
        "profit_profile": "conservative",
        "home_run_recommend_min_score": 65,
        "home_run_recommend_strong_score": 78,
        "auto_home_run_enabled": True,
        "auto_home_run_all_desks": True,
        "auto_home_run_min_score": 65,
        "auto_home_run_revert_score": 45,
        "auto_home_run_cooldown_minutes": 20,
        "timing_intel_enabled": True,
        "timing_gate_auto_trades": True,
        "timing_strict_symbol": False,
        "timing_adaptive_loosen": False,
        "timing_adaptive_skip_threshold": 5,
        "rag_block_repeat_losers": True,
        "rag_block_repeat_losers_curated": False,
        "rag_block_min_loss_lessons": 2,
        "rag_block_min_pick_losses": 2,
        "daily_universe_limit": 500,
        "daily_universe_conviction_enabled": False,
        "unified_daily_job_enabled": True,
        "stop_cooldown_enabled": True,
        "same_day_symbol_block": True,
        "fast_poll_open_window": True,
        "latency_compensation_enabled": True,
        "latency_budget_seconds": None,
        "latency_min_pattern_score": 2,
        "latency_require_preemptive": False,
        "ltp_stream_enabled": True,
        "ltp_poll_seconds": 3,
        "ltp_yahoo_poll_seconds": 15,
        "live_autopilot": False,
        "use_morning_scan_candidates": True,
        "pick_mode": "curated_list",
        "curated_symbols": [],
        "session_active": False,
        "session_id": None,
        "max_concurrent_picks": 3,
        "prevent_mac_sleep_on_session": True,
        "mac_sleep_guard_until_minute_ist": None,
        "psychology_enabled": True,
        "psychology_gate_buys": True,
        "psychology_gate_sells": True,
        "psychology_block_rsi_fomo": 78,
        "psychology_block_sentiment_high": 85,
        "psychology_block_sentiment_low": 22,
        "psychology_early_take_pct": 0.9,
        "psychology_fear_stop_pct": 0.55,
        "psychology_greed_rsi_take": 70,
        "dual_desk_preferences": None,
    },
    "reconcile_enabled": True,
    "halt_on_reconcile_drift": True,
    "margin_check_enabled": True,
    "watchlist": [],
    "updated_at": None,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_trading_config() -> dict[str, Any]:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    env_mode = setting("TRADING_EXECUTION_MODE", "").strip().lower()
    if not CONFIG_PATH.exists():
        cfg = deepcopy(DEFAULT_CONFIG)
        if env_mode in {"paper", "live"}:
            cfg["execution_mode"] = env_mode
        cfg["updated_at"] = _now()
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        return cfg
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    cfg = deepcopy(DEFAULT_CONFIG)
    cfg.update({k: v for k, v in raw.items() if k in cfg or k == "watchlist"})
    cfg["risk"] = {**DEFAULT_CONFIG["risk"], **(raw.get("risk") or {})}
    cfg["autopilot"] = {**DEFAULT_CONFIG["autopilot"], **(raw.get("autopilot") or {})}
    try:
        from trading.symbol_validate import CURATED_SYMBOLS_MAX, normalize_app_symbol, normalize_symbol_list

        if cfg.get("watchlist"):
            cfg["watchlist"] = normalize_symbol_list(cfg["watchlist"], max_count=50)
        ap = cfg.get("autopilot") or {}
        if ap.get("curated_symbols"):
            ap["curated_symbols"] = normalize_symbol_list(ap["curated_symbols"], max_count=CURATED_SYMBOLS_MAX)
        if ap.get("active_symbol"):
            try:
                ap["active_symbol"] = normalize_app_symbol(str(ap["active_symbol"]))
            except ValueError:
                ap["active_symbol"] = ""
        cfg["autopilot"] = ap
    except ValueError:
        pass
    if env_mode in {"paper", "live"}:
        cfg["execution_mode"] = env_mode
    return cfg


def save_trading_config(patch: dict[str, Any]) -> dict[str, Any]:
    from trading.symbol_validate import CURATED_SYMBOLS_MAX, normalize_app_symbol, normalize_symbol_list

    cfg = load_trading_config()
    for key, val in patch.items():
        if key == "risk" and isinstance(val, dict):
            cfg["risk"] = {**cfg.get("risk", {}), **val}
        elif key == "autopilot" and isinstance(val, dict):
            ap = {**cfg.get("autopilot", {}), **val}
            if "curated_symbols" in val and val["curated_symbols"] is not None:
                ap["curated_symbols"] = normalize_symbol_list(val["curated_symbols"], max_count=CURATED_SYMBOLS_MAX)
            if ap.get("active_symbol"):
                try:
                    ap["active_symbol"] = normalize_app_symbol(str(ap["active_symbol"]))
                except ValueError:
                    ap["active_symbol"] = ""
            cfg["autopilot"] = ap
        elif key in DEFAULT_CONFIG or key in {"watchlist", "reconcile_enabled", "halt_on_reconcile_drift", "margin_check_enabled"}:
            if key == "watchlist" and val is not None:
                cfg[key] = normalize_symbol_list(val, max_count=50)
            else:
                cfg[key] = val
    cfg["updated_at"] = _now()
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return cfg


def is_live_execution(cfg: dict[str, Any] | None = None) -> bool:
    c = cfg or load_trading_config()
    return c.get("execution_mode") == "live" and bool(c.get("live_armed"))
