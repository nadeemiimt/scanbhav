"""Tests for intraday pattern scoring."""
from trading.intraday_patterns import pattern_edge_boost, score_intraday_patterns


def _row(**kwargs):
    base = {
        "symbol": "TEST.NSE",
        "stance": "favorable",
        "composite_score": 75,
        "horizon_return_pct": 3.5,
        "atr_pct": 3.2,
        "rsi_14": 52,
        "supertrend_dir": 1,
        "macd_hist": 0.5,
        "rvol": 1.6,
        "gap_pct": 1.2,
        "pattern_bias": "bullish",
    }
    base.update(kwargs)
    return base


def test_gap_and_go_pattern_fires():
    score, pattern_ids, _meta = score_intraday_patterns(_row(), ist_mins=9 * 60 + 30)
    assert "gap_and_go" in pattern_ids
    assert score >= 55.0


def test_momentum_continuation():
    score, pattern_ids, _meta = score_intraday_patterns(
        _row(golden_cross=True, gap_pct=None),
        ist_mins=10 * 60,
    )
    assert "momentum_continuation" in pattern_ids
    assert score >= 50.0


def test_pattern_edge_boost_positive():
    boost, reasons, meta = pattern_edge_boost(_row(news_score=70), ist_mins=9 * 60 + 45)
    assert boost > 0
    assert meta.get("pattern_score", 0) >= 55


def test_bearish_stance_lower_score():
    strong = score_intraday_patterns(_row(), ist_mins=9 * 60 + 30)[0]
    weak = score_intraday_patterns(_row(stance="neutral", horizon_return_pct=-1), ist_mins=9 * 60 + 30)[0]
    assert strong > weak
