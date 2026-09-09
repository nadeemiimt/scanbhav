"""Tests for dynamic RBI macro and NSE announcements."""
from __future__ import annotations

from analysis import rbi_macro as rm
from analysis.india_data import fetch_corporate_announcements


def test_rbi_macro_scrape_or_cache(monkeypatch):
    monkeypatch.setattr(rm, "_load_cache", lambda: None)
    monkeypatch.setattr(
        rm,
        "_scrape_rbi_homepage",
        lambda: {"status": "ok", "source": "rbi_homepage", "rbi_repo_pct": 5.25, "as_of": "2026-08-08"},
    )
    monkeypatch.setattr(rm, "_fetch_datagov_cpi", lambda: {"status": "unconfigured"})
    monkeypatch.setattr(rm, "_fetch_fred_cpi", lambda: {"status": "unconfigured"})
    monkeypatch.setattr(
        rm,
        "_fetch_worldbank_cpi",
        lambda: {"status": "ok", "source": "worldbank", "cpi_yoy_pct": 4.9, "cpi_period": "2024", "cpi_frequency": "annual"},
    )
    out = rm.fetch_dynamic_rbi_macro(force_refresh=True)
    assert out["rbi_repo_pct"] == 5.25
    assert out["cpi_yoy_pct"] == 4.9


def test_nse_announcements_shape(monkeypatch):
    def fake_session():
        class S:
            def get(self, url, params=None, timeout=20):
                class R:
                    status_code = 200

                    def json(self):
                        return [{
                            "an_dt": "07-Aug-2026",
                            "desc": "Results",
                            "attchmntText": "Q1 results",
                            "symbol": "RELIANCE",
                        }]

                return R()

        return S()

    monkeypatch.setattr("analysis.india_data._nse_session", fake_session)
    out = fetch_corporate_announcements("RELIANCE")
    assert out["status"] == "ok"
    assert out["count"] == 1
    assert out["announcements"][0]["subject"] == "Results"
