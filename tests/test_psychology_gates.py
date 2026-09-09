"""Tests for crowd psychology buy/sell gates."""
from trading.psychology_gates import (
    evaluate_buy_psychology,
    evaluate_sell_psychology,
    psychology_from_row,
    psychology_score_adjustment,
)


def _greed_row():
    return {
        "symbol": "TEST",
        "stance": "favorable",
        "rsi_14": 79,
        "horizon_return_pct": 12,
        "supertrend_dir": 1,
    }


def test_psychology_blocks_fomo_buy():
    psych = psychology_from_row(_greed_row())
    gate = evaluate_buy_psychology(psych)
    assert gate["allowed"] is False
    assert "FOMO" in gate["reason"]


def test_psychology_allows_fear_dip_with_bullish_stance():
    row = {"symbol": "TEST", "stance": "favorable", "rsi_14": 28, "horizon_return_pct": -8}
    psych = psychology_from_row(row)
    gate = evaluate_buy_psychology(psych)
    assert gate["allowed"] is True
    adj, reasons = psychology_score_adjustment(psych)
    assert adj > 0
    assert any("fear_dip" in r for r in reasons)


def test_psychology_early_take_profit():
    psych = {"primary_mood": "greed-prone", "rsi_14": 72, "sentiment_score": 70}
    out = evaluate_sell_psychology(symbol="TEST", ret_pct=1.0, psych=psych)
    assert out["trigger"] == "psych_take_profit"


def test_psychology_fear_cut():
    psych = {"primary_mood": "fear-prone", "rsi_14": 32, "sentiment_score": 30}
    out = evaluate_sell_psychology(symbol="TEST", ret_pct=-0.6, psych=psych)
    assert out["trigger"] == "psych_fear_cut"
