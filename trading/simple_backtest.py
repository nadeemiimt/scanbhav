"""
Simple backtest for people and for experts.

Preferred mode is walk_forward: learn on older dates, score only the later dates.
date_range, a chosen symbol list, and a random sample are available too.
"""
from __future__ import annotations

from typing import Any, Iterator, Optional

from trading.learning_loop import gap_from_stats, record_gaps


MIN_BARS = 60
# After date slice / walk-forward cut, still need enough rows to score.
MIN_SCORE_BARS = 40
# Common wrong tickers people type (NSE official codes on the right).
SYMBOL_ALIASES = {
    "HEROMOTORS": "HEROMOTOCO",
    "HEROMOTOR": "HEROMOTOCO",
    "HERO": "HEROMOTOCO",
    "RELIANCEIND": "RELIANCE",
    "RELIANC": "RELIANCE",
    "TATAMOTOR": "TATAMOTORS",
    "TATAMOTORSS": "TATAMOTORS",
    "INFYSYS": "INFY",
    "INFOSYS": "INFY",
    "HDFCBANKLTD": "HDFCBANK",
    "ICICIBANKLTD": "ICICIBANK",
    "SBINBANK": "SBIN",
    "BAJAJFIN": "BAJFINANCE",
    "BAJAJFINANCE": "BAJFINANCE",
    "LTD": "LT",
    "LARSEN": "LT",
}


def plain_summary(stats: dict[str, Any], *, symbol: str, trigger: str) -> str:
    n = int(stats.get("n_trades") or 0)
    if n == 0:
        return f"{symbol}: this rule never fired in the chosen dates, so there is nothing to judge yet."
    exp = float(stats.get("expectancy_pct") or 0)
    wins = int(round(float(stats.get("win_rate") or 0) * n))
    direction = "made money on average" if exp > 0 else "lost money on average"
    trust = "Enough trades to take seriously." if stats.get("trusted") else "Too few trades to trust."
    return (
        f"{symbol} using {trigger}: {wins} of {n} finished trades were winners, and the rule {direction} "
        f"({exp:.2f}% per trade). {trust} This is a history check, not a promise about tomorrow."
    )


def _format_exc(exc: BaseException) -> str:
    if isinstance(exc, KeyError):
        return f"missing indicator {exc.args[0]!r} — price history is too short for this rule"
    msg = str(exc).strip() or exc.__class__.__name__
    return msg[:240]


def _bare(sym: str) -> str:
    return str(sym or "").strip().upper().removesuffix(".NSE").removesuffix(".BSE").removesuffix(".NS").removesuffix(".BO")


def _universe_tickers() -> set[str]:
    try:
        from pathlib import Path

        from config import BASE_DIR

        path = BASE_DIR / "data" / "universe" / "nifty500.csv"
        if not path.exists():
            return set()
        out: set[str] = set()
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.lower().startswith("symbol"):
                continue
            token = line.split(",")[0].strip().upper()
            if not token:
                continue
            out.add(_bare(token))
        return out
    except Exception:
        return set()


def resolve_backtest_symbol(raw: str) -> dict[str, Any]:
    """Normalize + alias-correct a user symbol for backtests."""
    from trading.symbol_validate import normalize_app_symbol

    original = str(raw or "").strip()
    try:
        normalized = normalize_app_symbol(original)
    except ValueError as exc:
        return {"ok": False, "input": original, "reason": str(exc)}

    bare = _bare(normalized)
    exchange = "BSE" if normalized.endswith(".BSE") else "NSE"
    notes: list[str] = []

    if bare in SYMBOL_ALIASES:
        fixed = SYMBOL_ALIASES[bare]
        notes.append(f"Mapped {bare} → {fixed} (common ticker alias).")
        bare = fixed

    universe = _universe_tickers()
    if universe and bare not in universe:
        # Prefix / contains match against Nifty 500 (e.g. HEROMOTORS → HEROMOTOCO).
        candidates = [u for u in universe if u.startswith(bare) or bare.startswith(u)]
        if not candidates and len(bare) >= 4:
            candidates = [u for u in universe if bare[:5] in u or u[:5] in bare]
        if len(candidates) == 1:
            notes.append(f"Corrected {bare} → {candidates[0]} using the Nifty 500 list.")
            bare = candidates[0]
        elif len(candidates) > 1:
            # Prefer exact-ish longest common prefix.
            candidates.sort(key=lambda u: (abs(len(u) - len(bare)), u))
            pick = candidates[0]
            notes.append(
                f"Ambiguous ticker {bare}; using closest Nifty name {pick}. "
                f"Other matches: {', '.join(candidates[1:4])}."
            )
            bare = pick

    symbol = f"{bare}.{exchange}"
    return {
        "ok": True,
        "input": original,
        "symbol": symbol,
        "notes": notes,
        "remapped": bool(notes),
    }


def _symbols_for_request(body: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    mode = str(body.get("mode") or "walk_forward")
    resolutions: list[dict[str, Any]] = []
    if mode == "random":
        from trading.backtest_agent import sample_random_nifty_backtest_symbols

        count = int(body.get("random_count") or 8)
        symbols = sample_random_nifty_backtest_symbols(count=max(1, min(count, 25)))
        return symbols, [{"ok": True, "symbol": s, "input": s, "notes": []} for s in symbols]

    raw = body.get("symbols") or ["RELIANCE.NSE"]
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        resolved = resolve_backtest_symbol(str(item or ""))
        resolutions.append(resolved)
        if not resolved.get("ok"):
            continue
        sym = resolved["symbol"]
        if sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
    return out[:25], resolutions


def _slice_dates(df, start: Optional[str], end: Optional[str]):
    if df is None or getattr(df, "empty", True):
        return df
    out = df
    if start:
        out = out[out.index >= start]
    if end:
        out = out[out.index <= end]
    return out


def _run_one(
    symbol: str,
    df,
    trigger: str,
    *,
    start: Optional[str],
    end: Optional[str],
    mode: str,
) -> dict[str, Any]:
    from quant_layer.backtest import backtest_stats, run_backtest

    full_len = len(df)
    frame = _slice_dates(df, start, end)
    sliced_len = len(frame)
    walk_forward_applied = False
    note_bits: list[str] = []

    if sliced_len < MIN_SCORE_BARS:
        # Date window too tight — fall back to full history so the check still runs.
        if full_len >= MIN_SCORE_BARS:
            frame = df
            note_bits.append(
                f"Date window had only {sliced_len} day(s); scored on full available history ({full_len} days)."
            )
        else:
            return {
                "symbol": symbol,
                "skipped": True,
                "reason": (
                    f"{symbol}: only {sliced_len} day(s) in the chosen dates "
                    f"(need ≥{MIN_SCORE_BARS}). Widen Start→End or pick a longer-listed stock."
                ),
            }

    if mode == "walk_forward" and len(frame) >= 80:
        cut = int(len(frame) * 0.7)
        test = frame.iloc[cut:]
        if len(test) >= MIN_SCORE_BARS:
            frame = test
            walk_forward_applied = True
        else:
            note_bits.append(
                f"Walk-forward test window was only {len(test)} day(s); scored on the full date window instead."
            )

    if trigger not in frame.columns:
        return {
            "symbol": symbol,
            "skipped": True,
            "reason": f"{symbol}: rule {trigger} is missing after indicators — history is too short.",
        }

    # Prefer rows with usable close (and ATR when present).
    usable = frame.dropna(subset=["close_adj"]).copy()
    if "atr_14" in usable.columns:
        with_atr = usable[usable["atr_14"].notna()]
        if len(with_atr) >= MIN_SCORE_BARS:
            usable = with_atr
    if len(usable) < MIN_SCORE_BARS:
        return {
            "symbol": symbol,
            "skipped": True,
            "reason": (
                f"{symbol}: after indicator warmup only {len(usable)} usable day(s) "
                f"(need ≥{MIN_SCORE_BARS})."
            ),
        }

    trades = run_backtest(usable, trigger)
    stats = backtest_stats(trades, min_trades=8)
    row = {
        "symbol": symbol,
        "trigger": trigger,
        "stats": stats,
        "bars_scored": len(usable),
        "bars_available": full_len,
        "walk_forward": walk_forward_applied,
        "plain": plain_summary(stats, symbol=symbol, trigger=trigger),
        "trades_sample": trades.head(8).to_dict(orient="records") if len(trades) else [],
    }
    if note_bits:
        row["notes"] = note_bits
        row["plain"] = f"{row['plain']} ({' '.join(note_bits)})"
    return row


def _load_history(symbol: str) -> tuple[list[dict[str, Any]], Optional[str]]:
    """Fetch daily bars; retry with force refresh / longer window if thin."""
    from routes.helpers import fetch_prices_light, rows_from_payload

    attempts = [
        {"force_refresh": False, "years": 5, "min_rows": MIN_BARS},
        {"force_refresh": True, "years": 8, "min_rows": max(30, MIN_BARS // 2)},
        {"force_refresh": True, "years": 10, "min_rows": 20},
    ]
    last_err: Optional[str] = None
    best: list[dict[str, Any]] = []
    for opts in attempts:
        try:
            payload = fetch_prices_light(
                symbol,
                force_refresh=bool(opts["force_refresh"]),
                years=int(opts["years"]),
                provider="auto",
                allow_nse_fallback=True,
                min_rows=int(opts["min_rows"]),
                retries=3,
            )
            history = rows_from_payload(payload)
            if len(history) > len(best):
                best = history
            if len(history) >= MIN_BARS:
                return history, None
        except Exception as exc:
            last_err = _format_exc(exc)
            continue
    if best:
        return best, last_err
    raise RuntimeError(last_err or f"Could not load prices for {symbol}")


def _final_payload(
    *,
    mode: str,
    trigger: str,
    start: Optional[str],
    end: Optional[str],
    symbols: list[str],
    rows_out: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
    resolutions: list[dict[str, Any]],
) -> dict[str, Any]:
    saved = record_gaps(gaps)
    scored = [r for r in rows_out if r.get("stats")]
    skipped = [r for r in rows_out if r.get("skipped")]
    avg = None
    if scored:
        avg = round(sum(float(r["stats"].get("expectancy_pct") or 0) for r in scored) / len(scored), 3)
    headline = (
        "Walk-forward check: older history is ignored and only the later dates are scored."
        if mode == "walk_forward"
        else "History check on the dates and stocks you picked."
    )
    summary = {
        "requested": len(resolutions) or len(symbols),
        "scored": len(scored),
        "skipped": len(skipped),
        "remapped": sum(1 for r in resolutions if r.get("remapped")),
    }
    if scored and not skipped:
        headline = f"{headline} All {len(scored)} stock(s) scored."
    elif scored and skipped:
        headline = f"{headline} Scored {len(scored)}, could not score {len(skipped)}."
    elif skipped and not scored:
        headline = f"No stock scored. {len(skipped)} skipped — see reasons below."

    return {
        "mode": mode,
        "trigger": trigger,
        "start": start,
        "end": end,
        "symbols": symbols,
        "headline": headline,
        "summary": summary,
        "plain": [r.get("plain") or r.get("reason") for r in rows_out],
        "average_expectancy_pct": avg,
        "results": rows_out,
        "resolutions": [
            {
                "input": r.get("input"),
                "symbol": r.get("symbol"),
                "ok": r.get("ok"),
                "remapped": bool(r.get("remapped")),
                "notes": r.get("notes") or [],
                "reason": r.get("reason"),
            }
            for r in resolutions
        ],
        "gaps": saved,
        "better_default": "walk_forward",
        "note": "Costs are a simple allowance, not your real brokerage. Review before acting.",
    }


def iter_simple_backtest(body: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield progress events, then a final `{type: done, result: ...}` payload."""
    from quant_layer.triggers import build_trigger_frame

    mode = str(body.get("mode") or "walk_forward")
    trigger = str(body.get("trigger") or "trigger_rsi_oversold_bounce")
    start = str(body.get("start") or "") or None
    end = str(body.get("end") or "") or None

    yield {"type": "status", "progress": 2, "message": "Preparing symbol list…"}
    symbols, resolutions = _symbols_for_request(body)

    # Surface bad symbols as skipped rows immediately.
    bad_rows = [
        {
            "symbol": str(r.get("input") or "?"),
            "skipped": True,
            "reason": r.get("reason") or "Invalid symbol",
        }
        for r in resolutions
        if not r.get("ok")
    ]

    total = max(len(symbols) + len(bad_rows), 1)
    yield {
        "type": "status",
        "progress": 5,
        "message": f"Checking {len(symbols)} stock(s) from {start or 'history start'} → {end or 'latest'}",
        "total": total,
        "symbols": symbols,
    }

    rows_out: list[dict[str, Any]] = list(bad_rows)
    gaps: list[dict[str, Any]] = []

    for index, sym in enumerate(symbols):
        base = int(8 + (index / max(len(symbols), 1)) * 84)
        remap_notes = next((r.get("notes") or [] for r in resolutions if r.get("symbol") == sym), [])
        msg = f"Loading prices for {sym} ({index + 1}/{len(symbols)})…"
        if remap_notes:
            msg = f"{msg} {' '.join(remap_notes)}"
        yield {
            "type": "symbol_start",
            "progress": base,
            "index": index + 1,
            "total": len(symbols),
            "symbol": sym,
            "message": msg,
        }
        try:
            history, fetch_note = _load_history(sym)
            yield {
                "type": "symbol_step",
                "progress": min(base + 4, 92),
                "index": index + 1,
                "total": len(symbols),
                "symbol": sym,
                "message": f"Scoring {sym} on the date window…",
            }
            if len(history) < MIN_BARS:
                one = {
                    "symbol": sym,
                    "skipped": True,
                    "reason": (
                        f"{sym}: only {len(history)} trading day(s) of history — need at least {MIN_BARS}. "
                        "Pick a more liquid name (e.g. HEROMOTOCO.NSE for Hero Motocorp)."
                    ),
                }
            else:
                df = build_trigger_frame(history)
                if df.empty or trigger not in df.columns:
                    one = {
                        "symbol": sym,
                        "skipped": True,
                        "reason": (
                            f"{sym}: not enough history to build {trigger} "
                            f"({len(history)} days). Try a longer-listed stock."
                        ),
                    }
                else:
                    one = _run_one(sym, df, trigger, start=start, end=end, mode=mode)
            if remap_notes:
                one.setdefault("notes", [])
                one["notes"] = list(one.get("notes") or []) + list(remap_notes)
            if fetch_note and one.get("skipped"):
                one["reason"] = f"{one.get('reason')} (last fetch note: {fetch_note})"
        except Exception as exc:
            one = {"symbol": sym, "skipped": True, "reason": f"{sym}: {_format_exc(exc)}"}
        rows_out.append(one)
        if one.get("stats"):
            gap = gap_from_stats(one["stats"], symbol=sym, trigger=trigger)
            if gap:
                gaps.append(gap)
        done_pct = int(8 + ((index + 1) / max(len(symbols), 1)) * 84)
        if one.get("skipped"):
            summary = f"Could not score {sym}: {one.get('reason') or 'skipped'}"
        else:
            summary = one.get("plain") or f"{sym}: done"
        yield {
            "type": "symbol_done",
            "progress": done_pct,
            "index": index + 1,
            "total": len(symbols),
            "symbol": sym,
            "message": summary,
            "ok": not one.get("skipped"),
        }

    yield {"type": "status", "progress": 96, "message": "Saving lessons…"}
    result = _final_payload(
        mode=mode,
        trigger=trigger,
        start=start,
        end=end,
        symbols=symbols,
        rows_out=rows_out,
        gaps=gaps,
        resolutions=resolutions,
    )
    yield {"type": "done", "progress": 100, "message": "Backtest complete.", "result": result}


def run_simple_backtest(body: dict[str, Any]) -> dict[str, Any]:
    final = None
    for event in iter_simple_backtest(body):
        if event.get("type") == "done":
            final = event.get("result")
    if not final:
        raise RuntimeError("Backtest produced no result")
    return final
