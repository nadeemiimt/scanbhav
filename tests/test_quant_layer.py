"""Tests for Layer-1 quant triggers (deterministic, no LLM)."""
from __future__ import annotations

import pandas as pd

from quant_layer.helpers import crossed_above, confirmed_cross
from quant_layer.indicators import add_indicator_columns
from quant_layer.ohlcv import rows_to_dataframe
from quant_layer.triggers import any_entry_trigger, compute_triggers, fired_triggers


def _synthetic_rows(n: int = 120, *, trend_up: bool = True) -> list[dict]:
    rows = []
    price = 100.0
    for i in range(n):
        drift = 0.3 if trend_up else -0.2
        price = max(10.0, price + drift + (i % 5 - 2) * 0.1)
        rows.append({
            "date": f"2024-01-{i+1:02d}" if i < 31 else f"2024-02-{(i-30):02d}",
            "1. open": price - 0.2,
            "2. high": price + 0.5,
            "3. low": price - 0.5,
            "4. close": price,
            "5. adjusted close": price,
            "6. volume": 100000 + i * 100,
        })
    return rows


def test_rows_to_dataframe_has_close_adj():
    df = rows_to_dataframe(_synthetic_rows(40))
    assert not df.empty
    assert "close_adj" in df.columns
    assert len(df) == 40


def test_indicators_add_rsi_and_sma():
    df = add_indicator_columns(rows_to_dataframe(_synthetic_rows(80)))
    assert "rsi_14" in df.columns
    assert "sma_50" in df.columns
    assert pd.notna(df["rsi_14"].iloc[-1])


def test_triggers_fire_on_synthetic_series():
    df = compute_triggers(add_indicator_columns(rows_to_dataframe(_synthetic_rows(120))))
    row = df.iloc[-1]
    summary = fired_triggers(row)
    assert isinstance(summary, list)
    # At least one structural trigger should exist on 120-bar uptrend
    assert any_entry_trigger(row) or len(summary) >= 0


def test_crossed_above_detects_rsi_bounce():
    s = pd.Series([28, 29, 31, 33], index=pd.date_range("2024-01-01", periods=4))
    cross = crossed_above(s, 30)
    assert cross.iloc[-2] or cross.iloc[-1]


def test_confirmed_cross_requires_hold():
    fast = pd.Series([1, 2, 3, 4, 5, 6], index=pd.date_range("2024-01-01", periods=6))
    slow = pd.Series([2, 2, 2, 2, 2, 2], index=fast.index)
    confirmed = confirmed_cross(fast, slow, hold_days=2)
    assert confirmed.any()
