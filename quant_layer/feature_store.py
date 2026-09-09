"""Parquet/CSV feature store for Layer-1 daily rows."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from config import BASE_DIR

STORE_DIR = BASE_DIR / "data" / "quant_cache" / "features"


def save_feature_table(df: pd.DataFrame, symbol: str, *, fmt: str = "parquet") -> Path:
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    safe = symbol.replace(".", "_").replace("/", "_")
    if fmt == "parquet":
        path = STORE_DIR / f"{safe}.parquet"
        try:
            df.to_parquet(path)
            return path
        except Exception:
            fmt = "csv"
    path = STORE_DIR / f"{safe}.csv"
    df.to_csv(path)
    return path


def load_feature_table(symbol: str) -> Optional[pd.DataFrame]:
    safe = symbol.replace(".", "_").replace("/", "_")
    pq = STORE_DIR / f"{safe}.parquet"
    csv = STORE_DIR / f"{safe}.csv"
    if pq.exists():
        try:
            return pd.read_parquet(pq)
        except Exception:
            pass
    if csv.exists():
        try:
            df = pd.read_csv(csv, parse_dates=["date"], index_col="date")
            return df
        except Exception:
            return None
    return None


def save_daily_snapshot(payload: dict[str, Any]) -> Path:
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = STORE_DIR / f"daily_snapshot_{day}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
