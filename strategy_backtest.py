"""Educational rule backtester on daily OHLCV rows."""
from __future__ import annotations

from typing import Any, Optional


def _closes(rows: list[dict[str, Any]]) -> list[float]:
    out = []
    for row in rows:
        v = float(row.get("5. adjusted close") or row.get("4. close") or 0)
        if v > 0:
            out.append(v)
    return out


def _dates(rows: list[dict[str, Any]]) -> list[str]:
    out = []
    for row in rows:
        v = float(row.get("5. adjusted close") or row.get("4. close") or 0)
        if v > 0:
            out.append(row["date"])
    return out


def _sma(values: list[float], period: int) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(values)
    if len(values) < period:
        return out
    window = sum(values[:period])
    out[period - 1] = window / period
    for i in range(period, len(values)):
        window += values[i] - values[i - period]
        out[i] = window / period
    return out


def _rsi(values: list[float], period: int = 14) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(values)
    if len(values) <= period:
        return out
    gains = losses = 0.0
    for i in range(1, period + 1):
        ch = values[i] - values[i - 1]
        gains += max(ch, 0)
        losses += max(-ch, 0)
    avg_gain = gains / period
    avg_loss = losses / period
    out[period] = 100.0 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))
    for i in range(period + 1, len(values)):
        ch = values[i] - values[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(ch, 0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-ch, 0)) / period
        out[i] = 100.0 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))
    return out


def run_backtest(
    symbol: str,
    rows: list[dict[str, Any]],
    *,
    strategy: str = "sma_cross",
    capital: float = 100_000.0,
    fee_bps: float = 10.0,
    fast_period: int = 20,
    slow_period: int = 50,
) -> dict[str, Any]:
    """Long-only educational backtest. Strategies: sma_cross | rsi_reversion | trend_follow."""
    px = _closes(rows)
    dates = _dates(rows)
    min_bars = max(60, slow_period + 10)
    if len(px) < min_bars:
        raise ValueError(f"Need at least {min_bars} daily bars for a meaningful backtest.")

    strategy = (strategy or "sma_cross").lower()
    fee = fee_bps / 10_000.0
    cash = float(capital)
    shares = 0.0
    entry = None
    trades: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []
    peak = capital
    max_dd = 0.0

    sma_fast = _sma(px, fast_period)
    sma_slow = _sma(px, slow_period)
    rsi = _rsi(px, 14)

    def signal(i: int) -> int:
        """1 = want long, 0 = flat."""
        if strategy == "rsi_reversion":
            r = rsi[i]
            if r is None:
                return 1 if shares > 0 else 0
            if shares <= 0 and r <= 30:
                return 1
            if shares > 0 and r >= 55:
                return 0
            return 1 if shares > 0 else 0
        if strategy == "trend_follow":
            f, s = sma_fast[i], sma_slow[i]
            if f is None or s is None:
                return 1 if shares > 0 else 0
            return 1 if f > s else 0
        # default sma_cross
        f, s = sma_fast[i], sma_slow[i]
        if f is None or s is None:
            return 1 if shares > 0 else 0
        prev_f = sma_fast[i - 1] if i else None
        prev_s = sma_slow[i - 1] if i else None
        if prev_f is None or prev_s is None:
            return 1 if f > s else 0
        if prev_f <= prev_s and f > s:
            return 1
        if prev_f >= prev_s and f < s:
            return 0
        return 1 if shares > 0 else 0

    for i in range(1, len(px)):
        want = signal(i)
        price = px[i]
        if want == 1 and shares <= 0:
            spend = cash * (1 - fee / 2)
            shares = spend / price
            cash = 0.0
            entry = price
            trades.append({"date": dates[i], "side": "buy", "price": round(price, 4)})
        elif want == 0 and shares > 0:
            proceeds = shares * price * (1 - fee / 2)
            pnl = proceeds - (entry or price) * shares
            cash = proceeds
            trades.append({
                "date": dates[i],
                "side": "sell",
                "price": round(price, 4),
                "pnl": round(pnl, 2),
            })
            shares = 0.0
            entry = None

        equity = cash + shares * price
        peak = max(peak, equity)
        dd = (equity / peak - 1) * 100 if peak else 0
        max_dd = min(max_dd, dd)
        if i % 5 == 0 or i == len(px) - 1:
            equity_curve.append({
                "date": dates[i],
                "equity": round(equity, 2),
                "in_market": shares > 0,
            })

    final = cash + shares * px[-1]
    sells = [t for t in trades if t["side"] == "sell"]
    wins = [t for t in sells if (t.get("pnl") or 0) > 0]
    win_rate = (len(wins) / len(sells) * 100) if sells else None
    ret_pct = (final / capital - 1) * 100

    result = {
        "symbol": symbol.upper(),
        "strategy": strategy,
        "fast_period": fast_period if strategy in ("sma_cross", "trend_follow") else None,
        "slow_period": slow_period if strategy in ("sma_cross", "trend_follow") else None,
        "capital": capital,
        "final_equity": round(final, 2),
        "return_pct": round(ret_pct, 3),
        "max_drawdown_pct": round(max_dd, 3),
        "trades": len(trades),
        "round_trips": len(sells),
        "win_rate_pct": round(win_rate, 1) if win_rate is not None else None,
        "equity_curve": equity_curve[-80:],
        "recent_trades": trades[-12:],
        "plain": (
            f"{strategy}: {ret_pct:+.1f}% over sample, max DD {max_dd:.1f}%, "
            f"{len(sells)} exits, win rate {win_rate:.0f}%."
            if win_rate is not None
            else f"{strategy}: {ret_pct:+.1f}% over sample, max DD {max_dd:.1f}%."
        ),
        "disclaimer": "Educational long-only backtest on daily bars with assumed fees — not a live strategy or advice.",
    }
    return result


def run_backtest_sweep(
    symbol: str,
    rows: list[dict[str, Any]],
    strategy: str,
    capital: float,
    *,
    fast_periods: Optional[list[int]] = None,
    slow_periods: Optional[list[int]] = None,
) -> dict[str, Any]:
    """Grid sweep for sma_cross only — returns ranked parameter combos."""
    strategy = (strategy or "sma_cross").lower()
    if strategy != "sma_cross":
        raise ValueError("Parameter sweep is supported for sma_cross only.")

    fast_list = fast_periods or [10, 20]
    slow_list = slow_periods or [50, 100]
    combos: list[dict[str, Any]] = []

    for fast in fast_list:
        for slow in slow_list:
            if fast >= slow:
                continue
            try:
                bt = run_backtest(
                    symbol,
                    rows,
                    strategy="sma_cross",
                    capital=capital,
                    fast_period=fast,
                    slow_period=slow,
                )
                combos.append({
                    "fast_period": fast,
                    "slow_period": slow,
                    "return_pct": bt["return_pct"],
                    "max_drawdown_pct": bt["max_drawdown_pct"],
                    "win_rate_pct": bt.get("win_rate_pct"),
                    "round_trips": bt.get("round_trips"),
                    "score": round(bt["return_pct"] - abs(bt["max_drawdown_pct"]) * 0.25, 3),
                })
            except ValueError:
                continue

    combos.sort(key=lambda c: c["score"], reverse=True)
    return {
        "symbol": symbol.upper(),
        "strategy": "sma_cross",
        "capital": capital,
        "grid": {"fast_periods": fast_list, "slow_periods": slow_list},
        "ranked": combos,
        "best": combos[0] if combos else None,
        "disclaimer": "Educational grid on historical daily bars — overfitting risk is high.",
    }
