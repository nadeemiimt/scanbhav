"""Robustness checks for the simple backtest desk."""
from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from quant_layer.backtest import run_backtest
from trading.simple_backtest import resolve_backtest_symbol, run_simple_backtest


class ResolveSymbolTests(unittest.TestCase):
    def test_heromotors_maps_to_heromotoco(self):
        out = resolve_backtest_symbol("HEROMOTORS")
        self.assertTrue(out["ok"])
        self.assertEqual(out["symbol"], "HEROMOTOCO.NSE")
        self.assertTrue(out["remapped"])

    def test_valid_passthrough(self):
        out = resolve_backtest_symbol("RELIANCE.NSE")
        self.assertTrue(out["ok"])
        self.assertEqual(out["symbol"], "RELIANCE.NSE")

    def test_invalid_symbol(self):
        out = resolve_backtest_symbol("bad symbol!")
        self.assertFalse(out["ok"])


class RunBacktestNaNTests(unittest.TestCase):
    def test_nan_atr_does_not_crash(self):
        idx = pd.date_range("2024-01-01", periods=30, freq="B")
        df = pd.DataFrame(
            {
                "close_adj": [100 + i for i in range(30)],
                "atr_14": [None] * 10 + [1.5] * 20,
                "trigger_rsi_oversold_bounce": [False] * 5 + [True] + [False] * 24,
            },
            index=idx,
        )
        trades = run_backtest(df, "trigger_rsi_oversold_bounce")
        self.assertIsInstance(trades, pd.DataFrame)


class SimpleBacktestPipelineTests(unittest.TestCase):
    def test_empty_history_skips_cleanly(self):
        def fake_load(symbol):
            return [], None

        with patch("trading.simple_backtest._load_history", side_effect=fake_load):
            result = run_simple_backtest(
                {
                    "mode": "date_range",
                    "symbols": ["RELIANCE.NSE"],
                    "start": "2024-01-01",
                    "end": "2024-06-01",
                }
            )
        self.assertEqual(result["summary"]["skipped"], 1)
        self.assertEqual(result["summary"]["scored"], 0)
        self.assertTrue(result["results"][0]["skipped"])

    def test_alias_then_score(self):
        idx = pd.date_range("2022-01-01", periods=120, freq="B")
        rows = [
            {
                "date": str(d.date()),
                "1. open": 100,
                "2. high": 102,
                "3. low": 99,
                "4. close": 101,
                "5. adjusted close": 101 + (i % 7) * 0.1,
                "6. volume": 100000,
            }
            for i, d in enumerate(idx)
        ]

        def fake_load(symbol):
            self.assertEqual(symbol, "HEROMOTOCO.NSE")
            return rows, None

        with patch("trading.simple_backtest._load_history", side_effect=fake_load):
            result = run_simple_backtest(
                {
                    "mode": "walk_forward",
                    "symbols": ["HEROMOTORS.NSE"],
                    "trigger": "trigger_rsi_oversold_bounce",
                }
            )
        self.assertEqual(result["symbols"], ["HEROMOTOCO.NSE"])
        self.assertGreaterEqual(result["summary"]["scored"] + result["summary"]["skipped"], 1)
        self.assertTrue(any(r.get("remapped") for r in result["resolutions"]))


if __name__ == "__main__":
    unittest.main()
