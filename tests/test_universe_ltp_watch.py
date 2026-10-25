from brokers import quote_cache
from trading.universe_ltp_watch import hydrate_rows_from_universe_watch


def test_hydrate_rows_from_watch_merges_ltp(monkeypatch):
    quote_cache.clear()
    quote_cache.set_ltp("RELIANCE.NSE", 2500.0, source="test", stream="universe_watch")
    quote_cache.set_ltp("RELIANCE.NSE", 2505.0, source="test", stream="universe_watch")

    rows = [{"symbol": "RELIANCE.NSE", "composite_score": 70, "price": 2400}]
    out = hydrate_rows_from_universe_watch(rows, max_age_seconds=120)
    assert out[0]["price"] == 2505.0
    assert out[0].get("ltp_fresh") is True
