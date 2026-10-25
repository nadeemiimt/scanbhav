"""Horizon picks board builds buy / plan-sell lists from screen rows."""
from __future__ import annotations


def test_score_for_plan_blend_and_direct():
    from horizon_picks import PLAN_HORIZONS, _score_for_plan

    row = {
        "symbol": "TCS.NSE",
        "horizon_scores": {
            "1w": {"score": 80, "grade": "A", "stance": "strong_favorable", "reasons": ["RSI ok"], "horizon_return_pct": 1.2},
            "1m": {"score": 70, "grade": "B", "stance": "favorable", "reasons": ["MACD +"], "horizon_return_pct": 3.0},
            "6m": {"score": 60, "grade": "C", "stance": "neutral", "reasons": [], "horizon_return_pct": 8.0},
            "1y": {"score": 55, "grade": "C", "stance": "neutral", "reasons": [], "horizon_return_pct": 12.0},
        },
    }
    plan_15 = next(p for p in PLAN_HORIZONS if p["id"] == "15d")
    blended = _score_for_plan(row, plan_15)
    assert blended["score"] == 75.0
    assert "RSI ok" in blended["reasons"]

    plan_6m = next(p for p in PLAN_HORIZONS if p["id"] == "6m")
    six = _score_for_plan(row, plan_6m)
    assert six["score"] == 60


def test_build_horizon_picks_from_rows(monkeypatch, tmp_path):
    from horizon_picks import build_horizon_picks
    import horizon_picks as hp

    rows = [
        {
            "symbol": "AAA.NSE",
            "price": 100,
            "bucket": "large",
            "horizon_scores": {
                "1w": {"score": 90, "grade": "A", "stance": "strong_favorable", "reasons": ["strong"], "horizon_return_pct": 2},
                "1m": {"score": 88, "grade": "A", "stance": "strong_favorable", "reasons": ["trend"], "horizon_return_pct": 4},
                "6m": {"score": 70, "grade": "B", "stance": "favorable", "reasons": [], "horizon_return_pct": 10},
                "1y": {"score": 65, "grade": "B", "stance": "favorable", "reasons": [], "horizon_return_pct": 15},
            },
        },
        {
            "symbol": "BBB.NSE",
            "price": 50,
            "bucket": "mid",
            "horizon_scores": {
                "1w": {"score": 20, "grade": "F", "stance": "unfavorable", "reasons": ["weak"], "horizon_return_pct": -5},
                "1m": {"score": 25, "grade": "F", "stance": "unfavorable", "reasons": ["down"], "horizon_return_pct": -8},
                "6m": {"score": 30, "grade": "D", "stance": "cautious", "reasons": [], "horizon_return_pct": -2},
                "1y": {"score": 35, "grade": "D", "stance": "cautious", "reasons": [], "horizon_return_pct": 1},
            },
        },
    ]
    monkeypatch.setattr(hp, "SCREEN_CACHE", tmp_path / "last_screen.json")
    monkeypatch.setattr(hp, "PICKS_CACHE", tmp_path / "horizon_picks.json")
    (tmp_path / "last_screen.json").write_text(
        __import__("json").dumps({"top": rows, "scored": 2, "horizon": "1m"}),
        encoding="utf-8",
    )
    out = build_horizon_picks(top_n=5, force_backfill=False)
    assert out["ok"] is True
    ids = [b["id"] for b in out["boards"]]
    assert ids == ["7d", "15d", "30d", "6m", "1y"]
    board_7 = next(b for b in out["boards"] if b["id"] == "7d")
    assert board_7["buy"][0]["symbol"] == "AAA.NSE"
    assert any(r["symbol"] == "BBB.NSE" for r in board_7["watch_sell"])
