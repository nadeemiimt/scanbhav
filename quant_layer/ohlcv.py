"""Convert cached OHLCV row dicts to a pandas DataFrame for Layer 1."""
from __future__ import annotations

from typing import Any

import pandas as pd

from technicals import row_close


def rows_to_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Build a dated OHLCV frame with corporate-action-adjusted close."""
    records: list[dict[str, Any]] = []
    for row in rows:
        close_adj = row_close(row)
        if close_adj <= 0:
            continue
        try:
            vol = float(row.get("6. volume") or row.get("volume") or 0)
        except (TypeError, ValueError):
            vol = 0.0
        records.append({
            "date": row.get("date"),
            "open": float(row.get("1. open") or close_adj),
            "high": float(row.get("2. high") or close_adj),
            "low": float(row.get("3. low") or close_adj),
            "close": float(row.get("4. close") or close_adj),
            "close_adj": close_adj,
            "volume": vol,
        })
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    df = df.set_index("date")
    return df
