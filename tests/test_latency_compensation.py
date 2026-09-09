"""Latency compensation smoke tests."""
from __future__ import annotations

import unittest

from brokers import quote_cache
from trading.latency_compensation import (
    compensated_entry_allowed,
    estimate_latency_budget,
    predict_preemptive_entry,
)


class LatencyCompensationTests(unittest.TestCase):
    def test_latency_budget_defaults(self):
        budget = estimate_latency_budget()
        self.assertIn("budget_seconds", budget)
        self.assertGreater(budget["budget_seconds"], 0)

    def test_velocity_preemptive_signal(self):
        quote_cache.clear()
        quote_cache.set_ltp("TEST.NSE", 100.0, source="test")
        quote_cache.set_ltp("TEST.NSE", 100.15, source="test")
        pred = predict_preemptive_entry("TEST.NSE")
        self.assertEqual(pred["symbol"], "TEST.NSE")
        self.assertIn("pattern", pred)

    def test_compensated_entry_structure(self):
        gate = compensated_entry_allowed("RELIANCE.NSE")
        self.assertIn("allowed", gate)
        self.assertIn("compensation", gate)


if __name__ == "__main__":
    unittest.main()
