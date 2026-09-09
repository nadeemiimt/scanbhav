"""Tests for market news intel scoring."""
from trading.market_news_intel import (
    news_factor_from_row,
    score_news_bundle,
)


def test_score_news_bundle_no_headlines():
    score, meta = score_news_bundle({"headlines": [], "high_impact_count": 0, "tag_counts": {}})
    assert score == 40.0
    assert meta["headline_count"] == 0


def test_score_news_bundle_earnings_bullish():
    bundle = {
        "headlines": [
            {"title": "Company beats earnings estimates", "catalyst_tag": "earnings_corporate"},
            {"title": "Revenue guidance raised", "catalyst_tag": "earnings_corporate"},
        ],
        "high_impact_count": 0,
        "tag_counts": {"earnings_corporate": 2},
    }
    score, meta = score_news_bundle(bundle, sentiment_score=68.0)
    assert score >= 58.0
    assert "bullish_catalyst" in " ".join(meta["news_reasons"]) or "earnings" in " ".join(meta["news_reasons"])


def test_news_factor_from_row_uses_precomputed():
    row = {"news_score": 72.5, "news_headline_count": 4}
    assert news_factor_from_row(row) == 72.5


def test_news_factor_from_row_fallback_headlines():
    row = {"news_headline_count": 3}
    assert news_factor_from_row(row) == 58.0
