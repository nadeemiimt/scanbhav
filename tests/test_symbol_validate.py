import unittest

from trading.symbol_validate import normalize_app_symbol, normalize_symbol_list


class SymbolValidateTests(unittest.TestCase):
    def test_bare_ticker_gets_nse(self):
        self.assertEqual(normalize_app_symbol("reliance"), "RELIANCE.NSE")

    def test_yahoo_suffixes(self):
        self.assertEqual(normalize_app_symbol("RELIANCE.NS"), "RELIANCE.NSE")
        self.assertEqual(normalize_app_symbol("RELIANCE.BO"), "RELIANCE.BSE")

    def test_yahoo_symbol_mapping(self):
        from fetch_stock_data import yahoo_symbol

        self.assertEqual(yahoo_symbol("TMCV.NSE"), "TMCV.NS")
        self.assertEqual(yahoo_symbol("TMCV.BSE"), "TMCV.BO")

    def test_canonical_passthrough(self):
        self.assertEqual(normalize_app_symbol("BIKEWO.NSE"), "BIKEWO.NSE")
        self.assertEqual(normalize_app_symbol("BIKEWO-SM.NSE"), "BIKEWO-SM.NSE")

    def test_invalid_rejected(self):
        with self.assertRaises(ValueError):
            normalize_app_symbol("")
        with self.assertRaises(ValueError):
            normalize_app_symbol("bad symbol!")

    def test_list_dedupes_and_limits(self):
        out = normalize_symbol_list(["BIKEWO", "bikewo.nse", "TCS.NSE"], max_count=10)
        self.assertEqual(out, ["BIKEWO.NSE", "TCS.NSE"])


if __name__ == "__main__":
    unittest.main()
