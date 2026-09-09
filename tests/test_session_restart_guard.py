"""Restart guard — square orphans before start, flatten on stop."""
from __future__ import annotations

from trading.session_autopilot import ensure_flat_before_restart, list_orphan_positions


def test_ensure_flat_ok_when_no_orphans(monkeypatch):
    monkeypatch.setattr(
        "trading.session_autopilot.list_orphan_positions",
        lambda **kwargs: [],
    )
    result = ensure_flat_before_restart(active_session_ids=set(), auto_square=True)
    assert result["ok"] is True
    assert result["squared"] == 0


def test_ensure_flat_blocks_when_orphans_and_no_auto_square(monkeypatch):
    monkeypatch.setattr(
        "trading.session_autopilot.list_orphan_positions",
        lambda **kwargs: [{"symbol": "RPTECH.NSE", "session_id": "sess-old"}],
    )
    monkeypatch.setattr(
        "trading.session_autopilot._orphan_desk_pnl",
        lambda active_ids: {"position_count": 1, "symbols": ["RPTECH.NSE"]},
    )
    result = ensure_flat_before_restart(active_session_ids=set(), auto_square=False)
    assert result["ok"] is False
    assert "Square all legacy" in result["error"]


def test_ensure_flat_auto_squares_orphans(monkeypatch):
    monkeypatch.setattr(
        "trading.session_autopilot.list_orphan_positions",
        lambda **kwargs: [{"symbol": "RPTECH.NSE", "session_id": "sess-old"}],
    )
    monkeypatch.setattr(
        "trading.session_autopilot._orphan_desk_pnl",
        lambda active_ids: {"position_count": 1, "symbols": ["RPTECH.NSE"]},
    )
    monkeypatch.setattr(
        "trading.session_autopilot.square_orphan_positions",
        lambda **kwargs: {"count": 1, "closed": [{"symbol": "RPTECH.NSE"}]},
    )
    result = ensure_flat_before_restart(active_session_ids=set(), auto_square=True)
    assert result["ok"] is True
    assert result["squared"] == 1


def test_rank_rows_curated_overlap_boost():
    from trading.agent_selection import rank_rows_for_agent

    rows = [
        {
            "symbol": "DIACABS.NSE",
            "composite_score": 80,
            "stance": "favorable",
            "price": 100,
            "atr_pct": 3.5,
            "horizon_return_pct": 4,
            "rsi_14": 55,
            "bucket": "small",
        },
        {
            "symbol": "ACE.NSE",
            "composite_score": 82,
            "stance": "favorable",
            "price": 1000,
            "atr_pct": 3.5,
            "horizon_return_pct": 4,
            "rsi_14": 55,
            "bucket": "large",
        },
    ]
    ranked = rank_rows_for_agent(
        rows,
        min_composite=55,
        held=set(),
        top_n=5,
        target_pct=2.0,
        ist_mins=10 * 60 + 15,
        curated_symbols={"DIACABS.NSE"},
    )
    assert ranked[0]["symbol"] == "DIACABS.NSE"


def test_rank_rows_skips_cross_desk_held():
    from trading.agent_selection import rank_rows_for_agent

    rows = [
        {
            "symbol": "DIACABS.NSE",
            "composite_score": 80,
            "stance": "favorable",
            "price": 100,
            "atr_pct": 3.5,
            "horizon_return_pct": 4,
            "rsi_14": 55,
            "bucket": "small",
        },
    ]
    ranked = rank_rows_for_agent(
        rows,
        min_composite=55,
        held=set(),
        top_n=5,
        target_pct=2.0,
        cross_desk_held={"DIACABS.NSE"},
    )
    assert ranked == []
