"""Point-in-time Nifty 500 universe approximation (survivorship bias guard)."""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd


def point_in_time_universe(
    market_cap_history: pd.DataFrame,
    as_of_date: str,
    top_n: int = 500,
) -> list[str]:
    """
    market_cap_history columns: date, symbol, free_float_market_cap
    Returns top-N symbols by free-float mcap as of as_of_date.
    """
    if market_cap_history.empty:
        return []
    snap = market_cap_history[market_cap_history["date"] == as_of_date]
    if snap.empty:
        snap = market_cap_history[market_cap_history["date"] <= as_of_date]
        if snap.empty:
            return []
        last_date = snap["date"].max()
        snap = market_cap_history[market_cap_history["date"] == last_date]
    top = snap.nlargest(top_n, "free_float_market_cap")
    return top["symbol"].astype(str).tolist()


def load_pit_universe(as_of_date: Optional[str] = None) -> list[str]:
    """Load cached PIT universe or fall back to current nifty500_buckets.json."""
    from config import BASE_DIR
    import json

    path = BASE_DIR / "data" / "quant_foundation" / "market_cap_history.parquet"
    if path.exists():
        try:
            df = pd.read_parquet(path)
            if as_of_date:
                return point_in_time_universe(df, as_of_date)
        except Exception:
            pass
    from universe import universe_symbols
    return universe_symbols(500)
