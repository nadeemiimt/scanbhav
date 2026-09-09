import unittest

from trading.trade_plan import build_intraday_plan, intraday_rules_from_config


class TradePlanTests(unittest.TestCase):
    def test_intraday_plan_levels(self):
        plan = build_intraday_plan(
            {"symbol": "RELIANCE.NSE", "price": 1000, "composite_score": 62, "stance": "favorable"},
            cfg={
                "autopilot": {"target_pct": 1.5, "stop_pct": 0.75},
                "risk": {},
            },
        )
        self.assertEqual(plan["entry"]["entry_price_inr"], 1000)
        self.assertEqual(plan["exit"]["target_price_inr"], 1015)
        self.assertEqual(plan["exit"]["stop_price_inr"], 992.5)

    def test_rules_from_config(self):
        rules = intraday_rules_from_config({
            "autopilot": {"target_pct": 2.0, "stop_pct": 1.0},
            "risk": {"default_target_pct": 1.5, "default_stop_pct": 0.75},
        })
        self.assertEqual(rules["target_pct"], 2.0)
        self.assertEqual(rules["stop_pct"], 1.0)


if __name__ == "__main__":
    unittest.main()
