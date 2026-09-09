"""Tests for composite social volume fallback chain."""
from __future__ import annotations

from analysis import social_volume as sv


def test_social_volume_merge_with_mock_providers(monkeypatch):
    def fake_forum(sym: str):
        return {"status": "ok", "source": "forum_intel", "forum_thread_count": 3, "bullish_count": 2, "bearish_count": 0, "headlines": ["RELIANCE breakout forum talk"]}

    def fake_yahoo(sym: str):
        return {"status": "ok", "source": "yahoo_news", "news_headline_count": 2, "headlines": ["Reliance profit beats estimates", "Oil surge helps RIL"]}

    def fake_google(sym: str):
        return {"status": "empty", "source": "google_news"}

    def fake_finnhub(sym: str):
        return {"status": "empty", "source": "finnhub_news"}

    def fake_av(sym: str):
        return {"status": "skipped", "source": "alpha_vantage"}

    def fake_st(sym: str):
        return {"status": "unauthorized", "source": "stocktwits"}

    monkeypatch.setattr(sv, "_from_forum_intel", fake_forum)
    monkeypatch.setattr(sv, "_from_yahoo_news", fake_yahoo)
    monkeypatch.setattr(sv, "_from_google_news", fake_google)
    monkeypatch.setattr(sv, "_from_finnhub_news", fake_finnhub)
    monkeypatch.setattr(sv, "_from_alpha_vantage", fake_av)
    monkeypatch.setattr(sv, "_from_stocktwits", fake_st)

    out = sv.fetch_social_volume("RELIANCE")
    assert out["status"] == "ok"
    assert "forum_intel" in out["sources_used"]
    assert "yahoo_news" in out["sources_used"]
    assert out["forum_thread_count"] == 3
    assert out["news_headline_count"] == 2
    assert out["sentiment_score"] is not None
