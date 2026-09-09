"""Conservative vs home-run profit profiles — one-click config presets."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

from trading.config_store import load_trading_config, save_trading_config
from trading.intraday_rules import estimate_daily_profit_ceiling

ProfitProfileName = Literal["conservative", "home_run", "agent_pro"]

PROFILES: dict[str, dict[str, Any]] = {
    "conservative": {
        "id": "conservative",
        "label": "Conservative",
        "tagline": "₹15–30k typical days",
        "description": (
            "Tighter risk (₹3.5k/trade), ₹3L max per position, 2–3.5% targets, "
            "small pyramids. Best for steady paper tuning."
        ),
        "risk": {
            "max_position_inr": 300_000,
            "max_profit_inr": 100_000,
        },
        "autopilot": {
            "profit_profile": "conservative",
            "target_pct": 2.0,
            "risk_per_trade_inr": 3500,
            "dynamic_target_enabled": True,
            "home_run_target_pct": 3.5,
            "extended_target_pct": 2.5,
            "home_run_min_atr_pct": 3.5,
            "conviction_sizing_enabled": True,
            "conviction_edge_threshold": 75,
            "conviction_risk_multiplier": 1.5,
            "momentum_pyramid_min_pct": 1.0,
            "momentum_pyramid_fraction": 0.25,
            "partial_scale_out_enabled": True,
            "partial_scale_out_fraction": 0.5,
            "top_up_max_fraction": 0.25,
        },
        "dual_desk": {
            "agent_max_profit_inr": 50_000,
            "curated_max_profit_inr": 50_000,
        },
        "estimate": {
            "avg_notional_inr": 250_000,
            "avg_target_pct": 2.5,
            "win_rate": 0.42,
            "max_positions": 8,
        },
    },
    "home_run": {
        "id": "home_run",
        "label": "Home run",
        "tagline": "₹150k ceiling on trend days",
        "description": (
            "Aggressive sizing (₹8k/trade, ₹5L cap), 5% small-cap targets, "
            "50% momentum pyramids. Higher risk — use after consistent ₹30k+ weeks."
        ),
        "risk": {
            "max_position_inr": 500_000,
            "max_profit_inr": 600_000,
        },
        "autopilot": {
            "profit_profile": "home_run",
            "target_pct": 2.0,
            "risk_per_trade_inr": 8000,
            "dynamic_target_enabled": True,
            "home_run_target_pct": 5.0,
            "extended_target_pct": 3.5,
            "home_run_min_atr_pct": 3.5,
            "conviction_sizing_enabled": True,
            "conviction_edge_threshold": 75,
            "conviction_risk_multiplier": 2.5,
            "momentum_pyramid_min_pct": 1.0,
            "momentum_pyramid_fraction": 0.5,
            "partial_scale_out_enabled": True,
            "partial_scale_out_fraction": 0.5,
            "top_up_max_fraction": 0.5,
        },
        "dual_desk": {
            "agent_max_profit_inr": 150_000,
            "curated_max_profit_inr": 150_000,
        },
        "estimate": {
            "avg_notional_inr": 450_000,
            "avg_target_pct": 4.5,
            "win_rate": 0.55,
            "max_positions": 8,
        },
    },
    "agent_pro": {
        "id": "agent_pro",
        "label": "Agent Pro",
        "tagline": "Target ₹100k+/day on ₹30L (you set max profit cap)",
        "description": (
            "Auto Pick primary: ₹30L capital reference, minimum ₹100k/day profit *target*, "
            "news + pattern scoring. Max profit cap is not set here — configure it yourself."
        ),
        "risk": {
            "max_position_inr": 300_000,
            "max_daily_notional_inr": 3_000_000,
        },
        "autopilot": {
            "profit_profile": "agent_pro",
            "target_pct": 2.0,
            "risk_per_trade_inr": 5500,
            "dynamic_target_enabled": True,
            "home_run_target_pct": 4.0,
            "extended_target_pct": 3.0,
            "home_run_min_atr_pct": 3.0,
            "conviction_sizing_enabled": True,
            "conviction_edge_threshold": 72,
            "conviction_risk_multiplier": 1.75,
            "momentum_pyramid_min_pct": 0.8,
            "momentum_pyramid_fraction": 0.35,
            "partial_scale_out_enabled": True,
            "partial_scale_out_fraction": 0.5,
            "top_up_max_fraction": 0.35,
            "agent_news_intel_enabled": True,
            "agent_pattern_scoring_enabled": True,
            "agent_news_enrich_top_n": 80,
            "agent_min_daily_profit_target_inr": 100_000,
            "agent_capital_inr": 3_000_000,
            "max_concurrent_picks": 8,
            "auto_home_run_enabled": True,
            "auto_home_run_min_score": 62,
        },
        "dual_desk": {},
        "estimate": {
            "avg_notional_inr": 320_000,
            "avg_target_pct": 3.2,
            "win_rate": 0.48,
            "max_positions": 8,
        },
    },
}


def _profile_summary(profile: dict[str, Any]) -> dict[str, Any]:
    est_in = profile.get("estimate") or {}
    est = estimate_daily_profit_ceiling(
        max_positions=int(est_in.get("max_positions") or 8),
        avg_notional_inr=float(est_in.get("avg_notional_inr") or 300_000),
        avg_target_pct=float(est_in.get("avg_target_pct") or 2.5),
        win_rate=float(est_in.get("win_rate") or 0.45),
    )
    return {
        "typical_net_inr": est["estimated_net_inr"],
        "gross_win_inr": est["estimated_gross_win_inr"],
        "gross_loss_inr": est["estimated_gross_loss_inr"],
    }


def list_profit_profiles() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for pid, profile in PROFILES.items():
        row = {
            "id": pid,
            "label": profile["label"],
            "tagline": profile["tagline"],
            "description": profile["description"],
            "max_position_inr": profile["risk"]["max_position_inr"],
            "risk_per_trade_inr": profile["autopilot"]["risk_per_trade_inr"],
            "home_run_target_pct": profile["autopilot"]["home_run_target_pct"],
            "estimate": _profile_summary(profile),
        }
        if pid == "agent_pro":
            row["min_daily_profit_target_inr"] = profile["autopilot"].get("agent_min_daily_profit_target_inr")
            row["capital_inr"] = profile["autopilot"].get("agent_capital_inr")
        out.append(row)
    return out


def active_profit_profile_name(cfg: dict[str, Any] | None = None) -> str:
    cfg = cfg or load_trading_config()
    name = str((cfg.get("autopilot") or {}).get("profit_profile") or "conservative")
    return name if name in PROFILES else "conservative"


def profit_profile_status() -> dict[str, Any]:
    cfg = load_trading_config()
    active = active_profit_profile_name(cfg)
    risk = cfg.get("risk") or {}
    ap = cfg.get("autopilot") or {}
    dual = ap.get("dual_desk_preferences") or {}
    from trading.agent_capital_goals import agent_capital_goals
    from trading.home_run_advisor import recommend_home_run_day, _load_auto_state

    auto_state = _load_auto_state()
    goals = agent_capital_goals(cfg)
    return {
        "active": active,
        "profiles": list_profit_profiles(),
        "applied": {
            "max_position_inr": risk.get("max_position_inr"),
            "risk_per_trade_inr": ap.get("risk_per_trade_inr"),
            "home_run_target_pct": ap.get("home_run_target_pct"),
            "max_profit_inr": risk.get("max_profit_inr"),
            "agent_max_profit_inr": (dual.get("agent") or {}).get("max_profit_inr"),
            "curated_max_profit_inr": (dual.get("curated") or {}).get("max_profit_inr"),
            "agent_min_daily_profit_target_inr": goals["min_daily_profit_target_inr"],
            "agent_capital_inr": goals["capital_inr"],
        },
        "auto_home_run_enabled": bool(ap.get("auto_home_run_enabled", True)),
        "auto_profile_state": auto_state if auto_state.get("date_ist") else None,
        "home_run_recommendation": recommend_home_run_day(cfg),
    }


def apply_profit_profile(name: str) -> dict[str, Any]:
    """Apply preset and persist — preserves dual-desk symbols and spend caps."""
    key = str(name or "").strip().lower()
    if key not in PROFILES:
        raise ValueError(f"Unknown profit profile: {name}. Use: {', '.join(PROFILES)}")

    profile = PROFILES[key]
    cfg = load_trading_config()
    ap = deepcopy(cfg.get("autopilot") or {})
    risk = deepcopy(cfg.get("risk") or {})

    risk.update(profile.get("risk") or {})
    ap.update(profile.get("autopilot") or {})

    if profile.get("risk", {}).get("max_daily_notional_inr") is not None:
        risk["max_daily_notional_inr"] = float(profile["risk"]["max_daily_notional_inr"])

    dual = deepcopy(ap.get("dual_desk_preferences") or {})
    desk_patch = profile.get("dual_desk") or {}
    if dual or desk_patch:
        dual.setdefault("agent", {})
        dual.setdefault("curated", {})
        if "agent_max_profit_inr" in desk_patch:
            dual["agent"]["max_profit_inr"] = float(desk_patch["agent_max_profit_inr"])
        if "curated_max_profit_inr" in desk_patch:
            dual["curated"]["max_profit_inr"] = float(desk_patch["curated_max_profit_inr"])
        ap["dual_desk_preferences"] = dual

    saved = save_trading_config({"risk": risk, "autopilot": ap})
    return {
        "config": saved,
        "profile": key,
        "label": profile["label"],
        "estimate": _profile_summary(profile),
        "message": f"Profit profile set to {profile['label']} — {profile['tagline']}",
    }
