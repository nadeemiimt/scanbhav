"""5-year historical pump / dump / pump-and-dump episode scanner.

Educational heuristics on OHLCV — not manipulation verdicts.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from technicals import row_close
from utils.numbers import parse_float as _num


def _parse_date(value: str) -> Optional[datetime]:
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _rolling_avg(values: list[float], window: int) -> list[Optional[float]]:
    out: list[Optional[float]] = []
    for i in range(len(values)):
        if i + 1 < window:
            out.append(None)
            continue
        chunk = values[i + 1 - window : i + 1]
        out.append(sum(chunk) / window)
    return out


def scan_price_history(
    rows: list[dict[str, Any]],
    *,
    lookback_years: float = 5.0,
    recent_days: int = 120,
) -> dict[str, Any]:
    """Walk daily candles and catalog parabolic pumps, crashes, and pump→dump pairs."""
    if not rows or len(rows) < 60:
        return {
            "episodes": [],
            "recent_episodes": [],
            "pump_count_5y": 0,
            "dump_count_5y": 0,
            "pump_and_dump_count_5y": 0,
            "repeat_pattern_risk": "low",
            "recent_pump_dump_emphasis": "Insufficient history for 5-year distortion scan.",
            "plain_english": "Need at least ~60 daily bars for historical distortion scan.",
            "disclaimer": "Historical episodes are heuristic pattern tags — not proof of manipulation.",
        }

    closes = [_num(row_close(r)) or 0.0 for r in rows]
    volumes = [_num(r.get("6. volume")) or 0.0 for r in rows]
    dates = [str(r.get("date", ""))[:10] for r in rows]

    vol_avg = _rolling_avg(volumes, 20)
    episodes: list[dict[str, Any]] = []
    cutoff = (_parse_date(dates[-1]) or datetime.now(timezone.utc)) - timedelta(days=int(lookback_years * 365.25))

    def ret_n(i: int, n: int) -> Optional[float]:
        if i < n:
            return None
        base = closes[i - n]
        if not base:
            return None
        return (closes[i] / base - 1) * 100

    def local_peak_trough(i: int, window: int = 10) -> tuple[float, float]:
        start = max(0, i - window)
        end = min(len(closes), i + window + 1)
        chunk = closes[start:end]
        return max(chunk), min(chunk)

    for i in range(20, len(closes)):
        dt = _parse_date(dates[i])
        if dt and dt < cutoff:
            continue
        r5 = ret_n(i, 5)
        r20 = ret_n(i, 20)
        rvol = (volumes[i] / vol_avg[i]) if vol_avg[i] and vol_avg[i] > 0 else None
        peak, trough = local_peak_trough(i, 12)
        drawdown_from_peak = ((closes[i] / peak) - 1) * 100 if peak else 0

        # Pump-like burst
        if r5 is not None and r5 >= 12 and (rvol is None or rvol >= 1.5):
            severity = "elevated" if r5 >= 20 or (rvol or 0) >= 2.2 else "moderate"
            episodes.append({
                "type": "pump",
                "date": dates[i],
                "move_pct": round(r5, 2),
                "horizon_days": 5,
                "rvol": round(rvol, 2) if rvol is not None else None,
                "close": round(closes[i], 4),
                "severity": severity,
                "plain_english": (
                    f"5-day surge +{r5:.1f}%"
                    + (f" on ~{rvol:.1f}× volume" if rvol else "")
                    + " — parabolic burst pattern."
                ),
            })
        elif r20 is not None and r20 >= 35 and (rvol is None or rvol >= 1.3):
            episodes.append({
                "type": "pump",
                "date": dates[i],
                "move_pct": round(r20, 2),
                "horizon_days": 20,
                "rvol": round(rvol, 2) if rvol is not None else None,
                "close": round(closes[i], 4),
                "severity": "elevated" if r20 >= 50 else "moderate",
                "plain_english": f"20-day rally +{r20:.1f}% — extended inflationary run.",
            })

        # Dump / washout
        if r5 is not None and r5 <= -12 and (rvol is None or rvol >= 1.5):
            episodes.append({
                "type": "dump",
                "date": dates[i],
                "move_pct": round(r5, 2),
                "horizon_days": 5,
                "rvol": round(rvol, 2) if rvol is not None else None,
                "close": round(closes[i], 4),
                "severity": "elevated" if r5 <= -18 else "moderate",
                "plain_english": (
                    f"5-day slide {r5:.1f}%"
                    + (f" on ~{rvol:.1f}× volume" if rvol else "")
                    + " — sharp deflationary flush."
                ),
            })
        elif drawdown_from_peak <= -18 and (rvol is None or rvol >= 1.4):
            episodes.append({
                "type": "dump",
                "date": dates[i],
                "move_pct": round(drawdown_from_peak, 2),
                "horizon_days": 12,
                "rvol": round(rvol, 2) if rvol is not None else None,
                "close": round(closes[i], 4),
                "severity": "elevated" if drawdown_from_peak <= -25 else "moderate",
                "plain_english": f"~{abs(drawdown_from_peak):.1f}% drawdown from local peak — washout profile.",
            })

    # De-dupe: keep strongest episode within 15-day windows
    episodes.sort(key=lambda e: e["date"])
    merged: list[dict[str, Any]] = []
    for ep in episodes:
        if not merged:
            merged.append(ep)
            continue
        prev = merged[-1]
        prev_dt = _parse_date(prev["date"])
        cur_dt = _parse_date(ep["date"])
        if (
            prev_dt and cur_dt
            and (cur_dt - prev_dt).days <= 15
            and prev["type"] == ep["type"]
        ):
            if abs(ep["move_pct"]) > abs(prev["move_pct"]):
                merged[-1] = ep
        else:
            merged.append(ep)

    # Pump-and-dump pairs: pump then dump within 90 days giving back >= 50% of pump
    pairs: list[dict[str, Any]] = []
    pumps = [e for e in merged if e["type"] == "pump"]
    dumps = [e for e in merged if e["type"] == "dump"]
    for pump in pumps:
        pdt = _parse_date(pump["date"])
        if not pdt:
            continue
        for dump in dumps:
            ddt = _parse_date(dump["date"])
            if not ddt or ddt <= pdt:
                continue
            gap = (ddt - pdt).days
            if gap > 90:
                break
            if abs(dump["move_pct"]) >= abs(pump["move_pct"]) * 0.45:
                pairs.append({
                    "type": "pump_and_dump",
                    "pump_date": pump["date"],
                    "dump_date": dump["date"],
                    "pump_pct": pump["move_pct"],
                    "dump_pct": dump["move_pct"],
                    "days_between": gap,
                    "severity": "elevated" if gap <= 45 and abs(dump["move_pct"]) >= abs(pump["move_pct"]) * 0.7 else "moderate",
                    "plain_english": (
                        f"Pump +{pump['move_pct']:.1f}% ({pump['date']}) followed by "
                        f"dump {dump['move_pct']:.1f}% ({dump['date']}) within {gap} days."
                    ),
                })
                break

    recent_cutoff = (_parse_date(dates[-1]) or datetime.now(timezone.utc)) - timedelta(days=recent_days)
    recent = [
        e for e in merged + pairs
        if (_parse_date(e.get("date") or e.get("dump_date") or "") or datetime.min.replace(tzinfo=timezone.utc)) >= recent_cutoff
    ]

    pump_n = sum(1 for e in merged if e["type"] == "pump")
    dump_n = sum(1 for e in merged if e["type"] == "dump")
    pair_n = len(pairs)

    repeat = "low"
    if pair_n >= 2 or (pump_n + dump_n) >= 5:
        repeat = "high"
    elif pair_n >= 1 or (pump_n + dump_n) >= 3:
        repeat = "moderate"

    recent_pd = [e for e in recent if e.get("type") in {"pump", "dump", "pump_and_dump"}]
    if recent_pd:
        top = recent_pd[-1]
        emphasis = (
            f"RECENT EMPHASIS — {top.get('plain_english', top.get('type', 'episode'))} "
            f"(within last {recent_days} days). Review whether volume was backed by fundamentals."
        )
    else:
        emphasis = f"No pump/dump-style episodes flagged in the last {recent_days} days."

    summary_parts = [
        f"5-year scan: {pump_n} pump-like, {dump_n} dump-like, {pair_n} pump→dump pair(s).",
        emphasis,
    ]
    if repeat != "low":
        summary_parts.append(f"Repeat distortion pattern risk: {repeat}.")

    return {
        "lookback_years": lookback_years,
        "bars_scanned": len(rows),
        "episodes": (merged + pairs)[-12:],
        "recent_episodes": recent[-5:],
        "pump_count_5y": pump_n,
        "dump_count_5y": dump_n,
        "pump_and_dump_count_5y": pair_n,
        "repeat_pattern_risk": repeat,
        "recent_pump_dump_emphasis": emphasis,
        "plain_english": " ".join(summary_parts),
        "headline": summary_parts[0],
        "disclaimer": "Historical episodes are heuristic pattern tags — not proof of manipulation.",
    }
