"""NSE calendar and market hours."""
from __future__ import annotations

from unittest.mock import patch

from trading.market_hours import nse_session_phase
from trading.nse_calendar import is_cm_holiday, is_trading_day, special_session_for_date


def test_special_session_makes_saturday_trading_day():
    assert special_session_for_date("2026-11-08") is not None
    assert is_trading_day("2026-11-08") is True


def test_cm_holiday_weekday_not_trading():
    holidays = [{"date": "2026-01-26", "description": "Republic Day"}]
    assert is_cm_holiday("2026-01-26", holidays) is True
    with patch("trading.nse_calendar.fetch_holiday_master", return_value={"holidays": holidays}):
        assert is_trading_day("2026-01-26") is False


def test_post_close_after_regular_close(monkeypatch):
    cfg = {"autopilot": {"use_nse_calendar": False, "nse_market_close_minute_ist": 930}}
    fake_now = __import__("datetime").datetime(2026, 8, 12, 15, 45, tzinfo=__import__("datetime").timezone(__import__("datetime").timedelta(hours=5, minutes=30)))
    monkeypatch.setattr("trading.market_hours._ist_now", lambda: fake_now)
    assert nse_session_phase(cfg) == "post_close"
