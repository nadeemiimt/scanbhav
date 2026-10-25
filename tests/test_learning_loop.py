from trading.learning_loop import gap_from_stats
from trading.simple_backtest import plain_summary


def test_gap_when_average_trade_loses():
    gap = gap_from_stats({"n_trades": 12, "expectancy_pct": -0.4, "win_rate": 0.5, "trusted": True})
    assert gap is not None
    assert "lost money" in gap["summary"]


def test_no_gap_when_result_is_fine():
    assert gap_from_stats({"n_trades": 20, "expectancy_pct": 0.6, "win_rate": 0.55, "trusted": True}) is None


def test_plain_summary_is_readable():
    text = plain_summary(
        {"n_trades": 10, "win_rate": 0.4, "expectancy_pct": -0.2, "trusted": True},
        symbol="RELIANCE.NSE",
        trigger="trigger_rsi_oversold_bounce",
    )
    assert "RELIANCE.NSE" in text
    assert "lost money" in text
    assert "not a promise" in text
