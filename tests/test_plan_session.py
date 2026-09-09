from analysis.plan_session import (
    build_session_trade_plan,
    enrich_row_session_plan,
    session_plan_target_day,
    slim_session_fields,
)


def test_session_plan_produces_prices():
    tech = {
        "price": 1000.0,
        "volatility": {"atr_14": 20.0, "atr_pct": 2.0},
        "levels": {"s1": 980.0, "pivot": 990.0, "r1": 1020.0, "r2": 1040.0},
    }
    plan = build_session_trade_plan(tech=tech, ratings={"composite_score": 70, "composite_stance": "favorable"}, target_day="today")
    assert plan["ok"] is True
    fields = slim_session_fields(plan)
    assert fields["entry_15d"] is not None
    assert fields["exit_15d"] is not None
    assert fields["exit_15d"] > fields["entry_15d"]


def test_enrich_row_from_slim_fields():
    row = {
        "symbol": "RELIANCE.NSE",
        "scan_status": "scanned",
        "price": 2500.0,
        "atr_14": 40.0,
        "atr_pct": 1.6,
        "composite_score": 80,
        "stance": "strong_favorable",
    }
    enrich_row_session_plan(row, full=None)
    assert row.get("entry_15d") is not None
    assert row.get("exit_15d") is not None


def test_target_day_values():
    assert session_plan_target_day() in {"today", "next_day"}
