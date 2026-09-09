"""Tests for screen page cache."""
from analysis.plan_session import enrich_row_session_plan
from screen_page_cache import is_default_screen_query
from screen_contract import ScreenPageQueryContract


def test_is_default_screen_query():
    q = ScreenPageQueryContract(
        page=1,
        page_size=50,
        cap_view="all",
        view="all",
        sort_key="display_rank",
        sort_dir="asc",
        sort_key2="score",
        sort_dir2="desc",
    )
    assert is_default_screen_query(q) is True
    q2 = q.model_copy(update={"page": 2})
    assert is_default_screen_query(q2) is False


def test_enrich_skips_when_plan_fresh():
    row = {"symbol": "TCS.NSE", "entry_15d": 100.0, "plan_target_day": "next_day"}
    enrich_row_session_plan(row)
    assert row["entry_15d"] == 100.0
