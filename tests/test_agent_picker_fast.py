"""Agent picker fast-scan path — no live social/RAG on full Nifty 500 loop."""
import time

from trading.agent_picker import (
    _load_nifty500_rows,
    _prefilter_bullish_rows,
    _score_screen_row,
    allocate_budget_picks,
)


def _limits():
    return {
        "max_per_order_inr": 300000,
        "remaining_budget_inr": 3_000_000,
        "position_slots": 8,
        "orders_left": 28,
        "held_symbols": set(),
        "halted": False,
    }


def test_prefilter_skips_non_bullish_before_scoring():
    rows, _ = _load_nifty500_rows()
    held = set()
    eligible = _prefilter_bullish_rows(rows, min_composite=52, held=held, top_n=80)
    assert eligible
    assert all(float(r.get("composite_score") or 0) >= 52 for r in eligible)
    assert all(str(r.get("stance") or "").lower() in {"favorable", "strong_favorable", "bullish", "constructive"} for r in eligible)


def test_fast_score_row_skips_live_social(monkeypatch):
    rows, _ = _load_nifty500_rows()
    row = rows[0]

    def _boom(*_a, **_k):
        raise AssertionError("live social fetch should not run in fast scan")

    monkeypatch.setattr("analysis.social_volume.fetch_social_volume", _boom)
    t0 = time.time()
    scored = _score_screen_row(row, target_pct=1.5, fast=True)
    elapsed = time.time() - t0
    assert scored.get("symbol")
    assert elapsed < 2.0


def test_allocate_budget_picks_completes_quickly(monkeypatch):
    rows, _ = _load_nifty500_rows()

    def _boom(*_a, **_k):
        raise AssertionError("live social fetch should not run during allocate")

    monkeypatch.setattr("analysis.social_volume.fetch_social_volume", _boom)
    t0 = time.time()
    picks, candidates = allocate_budget_picks(
        rows,
        limits=_limits(),
        max_picks=8,
        min_composite=52,
        target_pct=1.5,
    )
    elapsed = time.time() - t0
    assert elapsed < 15.0
    assert candidates
    assert picks
