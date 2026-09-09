"""Agent 3 — backtesting Layer-1 triggers with costs and walk-forward."""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd


def run_backtest(
    df: pd.DataFrame,
    entry_col: str,
    *,
    stop_atr_mult: float = 2.0,
    target_r: float = 2.0,
    cost_pct: float = 0.1,
    slippage_pct: float = 0.05,
    max_hold_days: int = 15,
) -> pd.DataFrame:
    trades: list[dict[str, Any]] = []
    in_position = False
    entry_idx = entry_price = stop_price = target_price = None
    entry_i = 0

    for i in range(1, len(df)):
        if not in_position and entry_col in df.columns and bool(df[entry_col].iloc[i]):
            entry_idx = i
            entry_i = i
            entry_price = float(df["close_adj"].iloc[i]) * (1 + slippage_pct / 100)
            atr = float(df["atr_14"].iloc[i] or 0)
            stop_price = entry_price - stop_atr_mult * atr
            target_price = entry_price + target_r * (entry_price - stop_price)
            in_position = True
        elif in_position:
            price = float(df["close_adj"].iloc[i])
            reason = None
            if price <= stop_price:
                reason = "stop"
            elif price >= target_price:
                reason = "target"
            elif i - entry_i >= max_hold_days:
                reason = "time_stop"
            if reason:
                exit_price = price * (1 - slippage_pct / 100)
                pnl_pct = (exit_price / entry_price - 1) * 100 - 2 * cost_pct
                trades.append({
                    "entry_date": str(df.index[entry_idx]),
                    "exit_date": str(df.index[i]),
                    "pnl_pct": pnl_pct,
                    "reason": reason,
                    "hold_days": i - entry_i,
                })
                in_position = False
    return pd.DataFrame(trades)


def backtest_stats(trades_df: pd.DataFrame, *, min_trades: int = 30) -> dict[str, Any]:
    if trades_df.empty:
        return {"n_trades": 0, "trusted": False, "min_trades": min_trades}
    wins = trades_df[trades_df["pnl_pct"] > 0]
    losses = trades_df[trades_df["pnl_pct"] <= 0]
    n = len(trades_df)
    return {
        "n_trades": n,
        "trusted": n >= min_trades,
        "min_trades": min_trades,
        "win_rate": len(wins) / n,
        "avg_win_pct": float(wins["pnl_pct"].mean()) if len(wins) else 0.0,
        "avg_loss_pct": float(losses["pnl_pct"].mean()) if len(losses) else 0.0,
        "expectancy_pct": float(trades_df["pnl_pct"].mean()),
        "max_drawdown_pct": _max_drawdown(trades_df["pnl_pct"].cumsum()),
    }


def _max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    peak = equity.cummax()
    dd = equity - peak
    return float(dd.min())


def walk_forward_backtest(
    df: pd.DataFrame,
    entry_col: str,
    *,
    train_bars: int = 504,
    test_bars: int = 126,
    **kwargs: Any,
) -> dict[str, Any]:
    """Tune on train window, report stats on subsequent test window."""
    if len(df) < train_bars + test_bars:
        test_df = df
    else:
        test_df = df.iloc[-test_bars:]
    trades = run_backtest(test_df, entry_col, **kwargs)
    return backtest_stats(trades)


def backtest_trigger_catalog(df: pd.DataFrame, trigger_cols: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for col in trigger_cols:
        if col not in df.columns:
            continue
        if not df[col].any():
            continue
        trades = run_backtest(df, col)
        out[col] = backtest_stats(trades)
    return out
