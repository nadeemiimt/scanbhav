"""
Backtest learning agent — walk-forward trigger stats on past OHLC + quant/news signals.

Builds a rolling policy file consumed by agent auto-pick ranking and live gates.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from config import BASE_DIR

POLICY_PATH = BASE_DIR / "data" / "trading" / "backtest_policy.json"

DEFAULT_TRIGGERS = [
    "trigger_rsi_oversold_bounce",
    "trigger_macd_bull_cross",
    "trigger_golden_cross",
    "trigger_price_above_sma50",
    "trigger_ema9_above_ema21",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_backtest_policy() -> dict[str, Any]:
    if not POLICY_PATH.exists():
        return {"symbols": {}, "triggers": {}, "updated_at": None}
    try:
        return json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"symbols": {}, "triggers": {}, "updated_at": None}


def save_backtest_policy(data: dict[str, Any]) -> dict[str, Any]:
    POLICY_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = _now()
    POLICY_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def backtest_score_adjustment(symbol: str) -> tuple[float, dict[str, Any]]:
    """Score bump/penalty from latest backtest policy for live agent ranking."""
    sym = str(symbol or "").upper().replace(".NSE", "")
    policy = load_backtest_policy()
    row = (policy.get("symbols") or {}).get(sym) or (policy.get("symbols") or {}).get(f"{sym}.NSE")
    if not row:
        return 0.0, {}

    adj = 0.0
    meta: dict[str, Any] = {"backtest": row}
    expectancy = float(row.get("expectancy_pct") or 0)
    win_rate = float(row.get("win_rate") or 0)
    trusted = bool(row.get("trusted"))

    if trusted and expectancy > 0:
        adj += min(10.0, expectancy * 2.5)
    elif trusted and expectancy < -0.15:
        adj -= min(8.0, abs(expectancy) * 2.0)

    if trusted and win_rate >= 0.55:
        adj += 3.0
    elif trusted and win_rate <= 0.4:
        adj -= 4.0

    best_trigger = row.get("best_trigger")
    if best_trigger:
        trig = (policy.get("triggers") or {}).get(best_trigger) or {}
        if trig.get("trusted") and float(trig.get("expectancy_pct") or 0) > 0:
            adj += 2.0
            meta["best_trigger"] = best_trigger

    return round(max(-12.0, min(12.0, adj)), 2), meta


def _symbol_history(
    symbol: str,
    load_rows: Callable[[str], list[dict[str, Any]]],
) -> Any:
    import pandas as pd

    from quant_layer.triggers import build_trigger_frame

    sym = symbol.upper()
    if not sym.endswith(".NSE"):
        sym = f"{sym}.NSE"
    rows = load_rows(sym)
    df = build_trigger_frame(rows)
    if df is None or df.empty:
        return pd.DataFrame()
    return df


def backtest_symbol(
    symbol: str,
    *,
    load_rows: Callable[[str], list[dict[str, Any]]],
    triggers: Optional[list[str]] = None,
) -> dict[str, Any]:
    from quant_layer.backtest import backtest_stats, backtest_trigger_catalog, run_backtest

    sym = symbol.upper()
    if not sym.endswith(".NSE"):
        sym_full = f"{sym}.NSE"
    else:
        sym_full = sym

    df = _symbol_history(sym_full, load_rows)
    if df.empty or len(df) < 60:
        return {"symbol": sym_full, "skipped": True, "reason": "insufficient_history"}

    cols = triggers or DEFAULT_TRIGGERS
    catalog = backtest_trigger_catalog(df, cols)
    best_trigger = None
    best_exp = -999.0
    best_stats: dict[str, Any] = {}
    for trig, stats in catalog.items():
        exp = float(stats.get("expectancy_pct") or 0)
        if stats.get("trusted") and exp > best_exp:
            best_exp = exp
            best_trigger = trig
            best_stats = stats

    news_boost_col = "news_bullish" if "news_bullish" in df.columns else None
    news_stats = {}
    if news_boost_col and df[news_boost_col].any():
        trades = run_backtest(df, news_boost_col)
        news_stats = backtest_stats(trades)

    return {
        "symbol": sym_full,
        "n_bars": len(df),
        "trigger_stats": catalog,
        "best_trigger": best_trigger,
        "best_stats": best_stats,
        "news_stats": news_stats,
    }


def run_backtest_learning_job(
    *,
    symbols: Optional[list[str]] = None,
    limit: int = 40,
    load_rows: Optional[Callable[[str], list[dict[str, Any]]]] = None,
    force: bool = False,
) -> dict[str, Any]:
    """
    Batch backtest curated + morning-scan leaders; merge into backtest_policy.json.
    """
    from trading.config_store import load_trading_config
    from trading.desk_universe import agent_curated_superset_symbols, symbol_base

    cfg = load_trading_config()
    ap = cfg.get("autopilot") or {}
    if not force and not ap.get("backtest_agent_enabled", True):
        return {"skipped": True, "reason": "backtest_agent_disabled"}

    if load_rows is None:
        from routes.helpers import fetch_prices_light, rows_from_payload

        def load_rows(sym: str) -> list[dict[str, Any]]:
            payload = fetch_prices_light(sym, force_refresh=False, provider="auto", allow_nse_fallback=True)
            rows = rows_from_payload(payload)
            if len(rows) < 30:
                raise ValueError("insufficient history")
            return rows

    sym_set: list[str] = []
    for s in agent_curated_superset_symbols(None) or set():
        sym_set.append(f"{symbol_base(s)}.NSE")
    for s in symbols or []:
        sym_set.append(str(s).upper())

    if not sym_set:
        try:
            from trading.morning_scan import load_morning_scan

            ms = load_morning_scan() or {}
            for row in (ms.get("rows") or ms.get("scored") or [])[:limit]:
                sym = str(row.get("symbol") or "")
                if sym:
                    sym_set.append(sym.upper())
        except Exception:
            pass

    seen: set[str] = set()
    ordered: list[str] = []
    for s in sym_set:
        if s not in seen:
            seen.add(s)
            ordered.append(s)
    ordered = ordered[: max(5, limit)]

    policy = load_backtest_policy()
    sym_policy: dict[str, Any] = dict(policy.get("symbols") or {})
    trig_policy: dict[str, Any] = dict(policy.get("triggers") or {})
    results: list[dict[str, Any]] = []

    for sym in ordered:
        try:
            one = backtest_symbol(sym, load_rows=load_rows)
            results.append(one)
            if one.get("skipped"):
                continue
            best = one.get("best_stats") or {}
            sym_policy[str(one.get("symbol") or sym)] = {
                **best,
                "best_trigger": one.get("best_trigger"),
                "news_stats": one.get("news_stats") or {},
                "backtested_at": _now(),
            }
            for trig, stats in (one.get("trigger_stats") or {}).items():
                prev = trig_policy.get(trig) or {}
                n_prev = int(prev.get("n_trades") or 0)
                n_new = int(stats.get("n_trades") or 0)
                if n_new >= n_prev:
                    trig_policy[trig] = stats
        except Exception as exc:
            results.append({"symbol": sym, "error": str(exc)[:160]})

    merged = save_backtest_policy({
        "symbols": sym_policy,
        "triggers": trig_policy,
        "last_job": {
            "run_at": _now(),
            "symbol_count": len(ordered),
            "ok_count": sum(1 for r in results if not r.get("skipped") and not r.get("error")),
        },
    })
    return {"policy": merged, "results": results[:25], "symbol_count": len(ordered)}


def backtest_agent_status() -> dict[str, Any]:
    from trading.config_store import load_trading_config

    policy = load_backtest_policy()
    last = policy.get("last_job") or {}
    return {
        "enabled": bool(load_trading_config().get("autopilot", {}).get("backtest_agent_enabled", True)),
        "updated_at": policy.get("updated_at"),
        "symbol_policies": len(policy.get("symbols") or {}),
        "trigger_policies": len(policy.get("triggers") or {}),
        "last_job": last,
    }
