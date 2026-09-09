"""Tests for agent capital goals (min profit target, not max cap)."""
from trading.agent_capital_goals import (
    optimize_picks_for_profit_target,
    portfolio_expected_profit_inr,
)


def _pick(symbol: str, profit: float, edge: float = 50) -> dict:
    return {"symbol": symbol, "expected_profit_inr": profit, "edge_score": edge}


def test_portfolio_expected_profit():
    assert portfolio_expected_profit_inr([_pick("A", 12000), _pick("B", 8000)]) == 20000.0


def test_optimize_swaps_for_higher_profit_when_below_target():
    picks = [_pick("A", 5000), _pick("B", 4000)]
    candidates = picks + [_pick("C", 15000), _pick("D", 12000)]
    out = optimize_picks_for_profit_target(
        picks,
        candidates,
        min_target_inr=20000,
        max_picks=2,
    )
    total = portfolio_expected_profit_inr(out)
    assert total >= 20000
    syms = {p["symbol"] for p in out}
    assert "C" in syms or "D" in syms


def test_optimize_no_change_when_target_met():
    picks = [_pick("A", 60000), _pick("B", 50000)]
    out = optimize_picks_for_profit_target(
        picks,
        picks,
        min_target_inr=100000,
        max_picks=2,
    )
    assert portfolio_expected_profit_inr(out) == 110000.0
