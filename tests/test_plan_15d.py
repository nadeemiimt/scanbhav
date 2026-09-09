import unittest

from analysis.plan_15d import build_15d_trade_plan


class Plan15dTests(unittest.TestCase):
    def test_builds_entry_exit(self):
        tech = {
            "price": 1000,
            "levels": {"s1": 980, "pivot": 990, "r1": 1020, "r2": 1050},
            "returns_pct": {"15d": 3.5},
            "volatility": {"atr_14": 15, "atr_pct": 1.5},
        }
        plan = build_15d_trade_plan(tech=tech, ratings={"composite_score": 62, "composite_stance": "favorable"})
        self.assertTrue(plan["ok"])
        self.assertLess(plan["entry_price"], 1000)
        self.assertGreater(plan["exit_price"], 1000)
        self.assertLess(plan["stop_price"], plan["entry_price"])


if __name__ == "__main__":
    unittest.main()
