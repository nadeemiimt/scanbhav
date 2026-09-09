import unittest
from unittest.mock import patch

from brokers.groww_data import _candles_to_daily_series
from brokers.symbols import groww_symbol


class GrowwSymbolTests(unittest.TestCase):
    def test_nse_mapping(self):
        self.assertEqual(groww_symbol("TMCV.NSE"), "NSE-TMCV")
        self.assertEqual(groww_symbol("RELIANCE.NSE"), "NSE-RELIANCE")

    def test_bse_mapping(self):
        self.assertEqual(groww_symbol("RELIANCE.BSE"), "BSE-RELIANCE")


class GrowwCandleParseTests(unittest.TestCase):
    def test_candles_to_daily_series(self):
        series = _candles_to_daily_series([
            ["2025-01-02T00:00:00", 100.0, 105.0, 99.0, 102.5, 1200, None],
            ["2025-01-03T00:00:00", 102.5, 106.0, 101.0, 104.0, 800, None],
        ])
        self.assertEqual(set(series.keys()), {"2025-01-02", "2025-01-03"})
        self.assertEqual(series["2025-01-02"]["4. close"], "102.5")
        self.assertEqual(series["2025-01-02"]["6. volume"], "1200")


class FetchDailyAutoTests(unittest.TestCase):
    @patch("fetch_stock_data.fetch_yfinance_daily")
    @patch("fetch_stock_data.fetch_nse_daily")
    def test_nse_fallback_after_yahoo(self, nse_fetch, yahoo_fetch):
        from fetch_stock_data import fetch_daily_auto

        yahoo_fetch.side_effect = RuntimeError("no yahoo")
        nse_fetch.return_value = {"Meta Data": {"source": "NSE charting API"}, "Time Series (Daily)": {}}

        payload = fetch_daily_auto("TMCV.NSE", 5, allow_groww_fallback=False)
        self.assertEqual(payload["Meta Data"]["source"], "NSE charting API")
        nse_fetch.assert_called_once_with("TMCV.NSE", 5)

    @patch("fetch_stock_data.fetch_yfinance_daily")
    def test_yahoo_wins_when_available(self, yahoo_fetch):
        from fetch_stock_data import fetch_daily_auto

        yahoo_fetch.return_value = {"Meta Data": {"source": "Yahoo Finance"}, "Time Series (Daily)": {}}
        payload = fetch_daily_auto("RELIANCE.NSE", 5)
        self.assertEqual(payload["Meta Data"]["source"], "Yahoo Finance")


if __name__ == "__main__":
    unittest.main()
