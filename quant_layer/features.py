"""Compact Layer-1 → Layer-2 payload per stock."""
from __future__ import annotations

from typing import Any

import pandas as pd


def row_to_llm_payload(symbol: str, df: pd.DataFrame, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Structured facts for LLM synthesis — numbers only, no raw OHLCV series."""
    if df.empty:
        return {"symbol": symbol, "error": "insufficient_data"}
    row = df.iloc[-1]
    date = df.index[-1]
    payload: dict[str, Any] = {
        "symbol": symbol.replace(".NSE", "").replace(".BSE", ""),
        "symbol_full": symbol,
        "date": str(date.date()) if hasattr(date, "date") else str(date),
        "close_adj": round(float(row.get("close_adj") or 0), 4),
        "rsi_14": _f(row.get("rsi_14")),
        "rsi_bullish_divergence": bool(row.get("trigger_rsi_bullish_divergence")),
        "rsi_bearish_divergence": bool(row.get("trigger_rsi_bearish_divergence")),
        "bb_percent_b": _f(row.get("bb_percent_b")),
        "sma_50": _f(row.get("sma_50")),
        "sma_200": _f(row.get("sma_200")),
        "ema_21": _f(row.get("ema_21")),
        "trend_50_over_200": bool(row.get("trend_50_over_200")),
        "adx_14": _f(row.get("adx_14")),
        "macd_hist": _f(row.get("macd_hist")),
        "vol_vs_avg20": _f(row.get("vol_vs_avg20")),
        "atr_pct": round(float(row.get("atr_14") or 0) / float(row.get("close_adj") or 1) * 100, 3),
        "high_52w": _f(row.get("high_52w")),
        "low_52w": _f(row.get("low_52w")),
        "weekly_rsi_14": _f(row.get("weekly_rsi_14")),
        "triggers_fired": [
            c.replace("trigger_", "")
            for c in df.columns
            if c.startswith("trigger_") and bool(row.get(c))
        ],
        "delivery_pct": (extra or {}).get("delivery_pct"),
        "oi_change_signal": (extra or {}).get("oi_change_signal"),
    }
    if extra:
        payload.update({k: v for k, v in extra.items() if k not in payload})
    return payload


def _f(val: Any) -> float | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return round(float(val), 4)
    except (TypeError, ValueError):
        return None
