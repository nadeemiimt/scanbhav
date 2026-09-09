import unittest
from unittest.mock import patch

from brokers.stub import StubBroker


class StubLtpTests(unittest.TestCase):
    @patch("brokers.stub.StubBroker._quote_price")
    def test_get_quotes_nse_source(self, quote_price):
        quote_price.return_value = {"price": 78.5, "source": "nse_charting", "stream": "nse_charting_5m"}
        out = StubBroker().get_quotes(["BIKEWO.NSE"])
        self.assertEqual(out["quotes"]["BIKEWO.NSE"]["price"], 78.5)
        self.assertEqual(out["quotes"]["BIKEWO.NSE"]["source"], "nse_charting")


class IntradayFallbackTests(unittest.TestCase):
    @patch("analysis.intraday._yahoo_intraday_rows", return_value=[])
    @patch("analysis.intraday._nse_intraday_rows")
    def test_nse_intraday_when_yahoo_empty(self, nse_rows, _yahoo):
        nse_rows.return_value = [
            {
                "date": f"2026-01-{d:02d}",
                "1. open": 100.0,
                "2. high": 101.0,
                "3. low": 99.0,
                "4. close": 100.0 + d,
                "6. volume": 1000.0,
            }
            for d in range(1, 35)
        ]
        from analysis.intraday import compute_intraday_ta

        out = compute_intraday_ta("BIKEWO.NSE")
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["source"], "nse_charting_60m")


if __name__ == "__main__":
    unittest.main()
