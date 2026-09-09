"""Markets desk payload: sector board, regime, FII/DII, VIX, breadth."""
from __future__ import annotations

from typing import Any

from analysis.breadth import compute_market_breadth
from analysis.india_data import fetch_fii_dii_flows
from analysis.market_context import sector_performance_board
from analysis.regime import compute_regime
from market_board import market_board
from screener import load_cached_screen
from technicals import compute_technicals


def build_markets_desk(*, limit: int = 500, top_n: int = 10) -> dict[str, Any]:
    board = market_board(limit_universe=limit, top_n=top_n, with_live_indices=True)
    breadth = compute_market_breadth(limit=limit)
    sector_board = sector_performance_board()
    fii = fetch_fii_dii_flows()

    # Regime from NIFTY proxy
    regime_pack = {"regime": {"regime": "sideways", "regime_score": 50}}
    try:
        from fetch_stock_data import fetch_yfinance_daily
        payload = fetch_yfinance_daily("^NSEI", years=2)
        entries = sorted(payload.get("Time Series (Daily)", {}).items())
        nifty_rows = [{"date": d, **v} for d, v in entries]
        nifty_tech = compute_technicals(nifty_rows)
        regime_pack = compute_regime(nifty_tech, None)
    except Exception:
        pass

    vix = next((i for i in (board.get("indices") or []) if "VIX" in str(i.get("id", "")).upper()), None)
    cached = load_cached_screen() or {}

    return {
        "board": board,
        "breadth": breadth,
        "sector_board": sector_board,
        "regime": regime_pack,
        "fii_dii": fii,
        "vix": vix,
        "screener_meta": {
            "scored": cached.get("scored"),
            "as_of": cached.get("meta", {}).get("as_of"),
        },
        "disclaimer": "Educational market context — delayed quotes and public NSE/Yahoo feeds.",
    }
