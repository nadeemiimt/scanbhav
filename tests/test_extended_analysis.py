"""Smoke tests for extended analysis modules."""
from __future__ import annotations

from analysis.bundle import build_extended_analysis, extended_summary_for_agents
from analysis.indicators_extended import compute_extended_indicators
from analysis.patterns import compute_patterns
from analysis.score_blend import blend_extended_scores
from horizon_rank import rate_all_horizons
from technicals import compute_technicals


def _sample_rows(n: int = 120) -> list[dict]:
    rows = []
    price = 100.0
    for i in range(n):
        price *= 1.001 if i % 5 else 0.998
        rows.append({
            "date": f"2024-01-{i+1:02d}",
            "1. open": price * 0.99,
            "2. high": price * 1.01,
            "3. low": price * 0.98,
            "4. close": price,
            "6. volume": 1_000_000 + i * 1000,
        })
    return rows


def test_extended_indicators_smoke():
    rows = _sample_rows()
    out = compute_extended_indicators(rows)
    assert out["status"] == "ok"
    assert "ichimoku" in out
    assert "cmf" in out


def test_patterns_smoke():
    rows = _sample_rows()
    out = compute_patterns(rows)
    assert "composite_bias" in out


def test_score_blend_smoke():
    rows = _sample_rows()
    tech = compute_technicals(rows)
    ratings = rate_all_horizons(tech)
    ext = build_extended_analysis(symbol="TEST", rows=rows, tech=tech, include_slow=False)
    blended = blend_extended_scores(ratings, ext)
    assert "extended_adjustment" in blended
    assert blended["composite_score"] is not None


def test_extended_summary():
    rows = _sample_rows()
    tech = compute_technicals(rows)
    ext = build_extended_analysis(symbol="TEST", rows=rows, tech=tech, include_slow=False)
    summary = extended_summary_for_agents(ext)
    assert isinstance(summary, str)
