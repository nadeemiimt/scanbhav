"""Tests for autopilot EOD session report."""
from trading.session_report import (
    build_markdown_report,
    build_session_summary,
    _closed_legs,
    _heuristic_postmortem,
)


def test_closed_legs_from_sells():
    trades = [
        {"side": "buy", "symbol": "A.NSE", "quantity": 10, "price": 100},
        {
            "side": "sell",
            "symbol": "A.NSE",
            "quantity": 10,
            "price": 102,
            "pnl_inr": 20,
            "reason": "target_hit",
            "detail": {"entry_price": 100, "return_pct": 2.0},
        },
    ]
    closed = _closed_legs(trades)
    assert len(closed) == 1
    assert closed[0]["pnl_inr"] == 20
    assert closed[0]["exit_reason"] == "target_hit"


def test_build_session_summary_win_rate():
    session = {
        "id": "sess-test",
        "pick_mode": "curated_list",
        "curated_symbols": ["A.NSE", "B.NSE"],
        "started_at": "2026-08-11T05:00:00+00:00",
        "trades": [
            {"side": "sell", "symbol": "A.NSE", "quantity": 1, "price": 110, "pnl_inr": 10, "reason": "target_hit", "detail": {"entry_price": 100}},
            {"side": "sell", "symbol": "B.NSE", "quantity": 1, "price": 90, "pnl_inr": -5, "reason": "stop_hit", "detail": {"entry_price": 100}},
        ],
        "cycles": [{}],
    }
    summary = build_session_summary(session)
    assert summary["closed_trades"] == 2
    assert summary["wins"] == 1
    assert summary["losses"] == 1
    assert summary["win_rate_pct"] == 50.0
    assert summary["realized_pnl_inr"] == 5.0
    assert summary["best_symbol"]["symbol"] == "A.NSE"


def test_build_session_summary_empty_session_not_daily_ledger(monkeypatch):
    """Sessions with no tagged trades must not inherit the whole day's ledger P&L."""
    session = {
        "id": "sess-empty",
        "pick_mode": "agent_auto",
        "started_at": "2026-08-12T09:08:01+00:00",
        "realized_pnl_inr": 0,
    }

    def fake_list_session_trades(session_id, limit=500):
        return [] if session_id == "sess-empty" else []

    monkeypatch.setattr("trading.session_report.list_session_trades", fake_list_session_trades)
    monkeypatch.setattr(
        "trading.session_report._ledger_closed_legs",
        lambda _date: [
            {"symbol": "OBSCP.NSE", "pnl_inr": 7869.0},
            {"symbol": "SIGMAADV.NSE", "pnl_inr": -5472.0},
        ],
    )
    monkeypatch.setattr(
        "trading.session_report._daily_stats_for_date",
        lambda _date: {"realized_pnl_inr": -6714.1},
    )

    summary = build_session_summary(session)
    assert summary["closed_trades"] == 0
    assert summary["realized_pnl_inr"] == 0.0
    assert summary["best_symbol"] is None


def test_report_is_stale_when_empty_report_has_trades():
    from trading.session_report import report_is_stale

    session = {"id": "sess-x", "started_at": "2026-08-11T05:00:00+00:00"}
    report = {"summary": {"closed_trades": 0, "buy_notional_inr": 0}, "generated_at": "2026-08-11T05:05:00+00:00"}
    assert report_is_stale(session, report) is False  # no trades in store in unit test


def test_markdown_report_contains_pnl():
    summary = {
        "trade_date_ist": "2026-08-11",
        "session_id": "sess-x",
        "pick_mode": "curated_list",
        "realized_pnl_inr": 1500,
        "buy_notional_inr": 50000,
        "closed_trades": 3,
        "win_rate_pct": 66.7,
        "wins": 2,
        "losses": 1,
        "avg_win_inr": 1000,
        "avg_loss_inr": -500,
        "cycle_count": 5,
        "best_symbol": {"symbol": "X.NSE", "pnl_inr": 1200, "closed_count": 2},
        "worst_symbol": {"symbol": "Y.NSE", "pnl_inr": -300, "closed_count": 1},
        "by_symbol": [],
        "by_exit_reason": {"target_hit": 2},
    }
    post = _heuristic_postmortem(summary)
    md = build_markdown_report(summary, post)
    assert "Autopilot session report" in md
    assert "₹+1,500" in md or "+1,500" in md
    assert post.get("executive_summary")
