"""Index strip prefers NSE allIndices and keeps a stable shape."""
from __future__ import annotations

from market_board import INDEX_YAHOO, _fetch_nse_indices, build_ticker_strip, fetch_live_indices


class _Resp:
    status_code = 200

    def json(self):
        return {
            "data": [
                {"index": "NIFTY 50", "last": 22888.95, "percentChange": -1.11},
                {"index": "NIFTY BANK", "last": 55488.1, "percentChange": -0.64},
                {"index": "INDIA VIX", "last": 14.69, "percentChange": 4.48},
            ]
        }


class _Session:
    def get(self, url, timeout=15):
        return _Resp()


def test_nse_indices_map(monkeypatch):
    monkeypatch.setattr("market_board._nse_session", lambda: _Session())
    rows = _fetch_nse_indices()
    ids = {r["id"] for r in rows}
    assert "NIFTY" in ids
    assert "BANKNIFTY" in ids
    assert "INDIA VIX" in ids
    nifty = next(r for r in rows if r["id"] == "NIFTY")
    assert nifty["price"] == 22888.95
    assert nifty["change_pct"] == -1.11
    assert nifty["source"] == "nse_all_indices"


def test_fetch_live_indices_uses_nse_without_yahoo(monkeypatch):
    monkeypatch.setattr("market_board._nse_session", lambda: _Session())
    monkeypatch.setattr("market_board._fetch_yahoo_index", lambda meta: None)
    monkeypatch.setattr("market_board._load_json", lambda path: {})
    monkeypatch.setattr("market_board._save_json", lambda path, payload: None)
    rows = fetch_live_indices(force=True)
    assert len(rows) >= 3
    strip = build_ticker_strip({"winners": [], "losers": []}, rows)
    assert strip[0]["s"] in {m["id"] for m in INDEX_YAHOO}
    assert strip[0]["v"] != "—"
