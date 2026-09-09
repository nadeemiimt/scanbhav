"""Basic live-trading module smoke tests."""
from __future__ import annotations

import unittest

from trading.order_lifecycle import is_filled_status, is_rejected_status
from trading.paper_ledger import sync_positions_from_broker
from brokers.positions_normalize import app_symbol, normalize_kite_positions


class LiveTradingTests(unittest.TestCase):
    def test_app_symbol(self):
        self.assertEqual(app_symbol("NSE", "RELIANCE"), "RELIANCE.NSE")

    def test_fill_status(self):
        self.assertTrue(is_filled_status("COMPLETE"))
        self.assertTrue(is_rejected_status("REJECTED"))

    def test_sync_positions_from_broker(self):
        rows = [{"symbol": "RELIANCE.NSE", "quantity": 2, "avg_price": 2500, "product": "mis", "broker": "zerodha"}]
        out = sync_positions_from_broker(rows, product="mis")
        self.assertEqual(out["synced"], 1)

    def test_normalize_kite_positions(self):
        raw = {"net": [{"exchange": "NSE", "tradingsymbol": "RELIANCE", "quantity": 5, "average_price": 100, "product": "MIS"}]}
        pos = normalize_kite_positions(raw)
        self.assertEqual(len(pos), 1)
        self.assertEqual(pos[0]["symbol"], "RELIANCE.NSE")


if __name__ == "__main__":
    unittest.main()
