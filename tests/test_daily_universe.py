"""Daily universe manifest helpers."""
from __future__ import annotations

from trading.daily_universe import daily_universe_status


def test_daily_universe_status_when_missing():
    out = daily_universe_status()
    assert out.get("ready") in {True, False}
