import unittest

from analysis.plan_7d import build_7d_swing_summary


class Plan7dTests(unittest.TestCase):
    def test_builds_paths_and_zones(self):
        tech = {
            "price": 704.0,
            "as_of": "2026-08-10",
            "levels": {
                "s1": 683.0,
                "s2": 665.0,
                "pivot": 699.0,
                "r1": 716.0,
                "r2": 732.0,
                "high_52w": 704.5,
            },
            "momentum": {"rsi_14": 73.0},
            "volatility": {"atr_14": 32.0, "atr_pct": 4.6},
            "returns_pct": {"1w": 7.5},
        }
        ratings = {
            "composite_score": 100,
            "composite_stance": "strong_favorable",
            "best_horizon": "1w",
            "horizons": {"1w": {"horizon_return_pct": 7.5, "score": 97.5}},
        }
        out = build_7d_swing_summary(symbol="SIGMAADV.NSE", tech=tech, ratings=ratings)
        self.assertTrue(out["ok"])
        self.assertEqual(out["horizon_days"], 7)
        self.assertTrue(out["overbought"])
        self.assertGreaterEqual(len(out["zones"]), 5)
        self.assertEqual(len(out["paths"]), 2)
        self.assertTrue(out["forecast_7d"].get("target_price"))
        self.assertIn("pullback", out["plain"].lower())


if __name__ == "__main__":
    unittest.main()
