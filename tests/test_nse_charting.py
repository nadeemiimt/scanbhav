import unittest
from unittest.mock import patch

from fetch_stock_data import (
    _chart_bars_to_daily_series,
    fetch_daily_auto,
    fetch_nse_charting_daily,
)


class NseChartingParseTests(unittest.TestCase):
    def test_chart_bars_to_daily_series(self):
        series = _chart_bars_to_daily_series([
            {"time": 1727395200000, "open": 45, "high": 47.25, "low": 45, "close": 47.25, "volume": 336000},
        ])
        self.assertIn("2024-09-27", series)
        self.assertEqual(series["2024-09-27"]["4. close"], "47.25")


class FetchDailyAutoNseTests(unittest.TestCase):
    @patch("fetch_stock_data.fetch_yfinance_daily")
    @patch("fetch_stock_data.fetch_nse_daily")
    def test_nse_after_yahoo_fail(self, nse_fetch, yahoo_fetch):
        yahoo_fetch.side_effect = RuntimeError("No Yahoo Finance daily history")
        nse_fetch.return_value = {
            "Meta Data": {"source": "NSE charting API"},
            "Time Series (Daily)": {"2026-01-01": {"4. close": "100"}},
        }
        payload = fetch_daily_auto("BIKEWO.NSE", 2, allow_groww_fallback=False)
        self.assertEqual(payload["Meta Data"]["source"], "NSE charting API")
        nse_fetch.assert_called_once()

    @patch("fetch_stock_data.fetch_yfinance_daily")
    def test_groww_skipped_by_default(self, yahoo_fetch):
        yahoo_fetch.return_value = {"Meta Data": {"source": "Yahoo Finance"}, "Time Series (Daily)": {}}
        with patch("brokers.groww_data.fetch_groww_daily") as groww_fetch:
            fetch_daily_auto("RELIANCE.NSE", 1)
            groww_fetch.assert_not_called()


class FetchNseChartingIntegration(unittest.TestCase):
    @unittest.skipUnless(
        __import__("os").environ.get("RUN_NSE_LIVE") == "1",
        "Set RUN_NSE_LIVE=1 to hit charting.nseindia.com",
    )
    def test_bikewo_live(self):
        payload = fetch_nse_charting_daily("BIKEWO.NSE", 2)
        self.assertEqual(payload["Meta Data"]["source"], "NSE charting API")
        self.assertGreaterEqual(len(payload["Time Series (Daily)"]), 30)


if __name__ == "__main__":
    unittest.main()
