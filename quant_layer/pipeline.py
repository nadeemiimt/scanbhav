"""Universe scan — Layer 1 shortlist builder for Nifty 500."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from config import BASE_DIR
from quant_layer.features import row_to_llm_payload
from quant_layer.triggers import any_entry_trigger, build_trigger_frame, trigger_summary
from universe import universe_symbols

CACHE_PATH = BASE_DIR / "data" / "quant_cache" / "daily_shortlist.json"


def analyze_symbol_rows(symbol: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Full Layer-1 output for one symbol (indicators + triggers + LLM payload)."""
    df = build_trigger_frame(rows)
    if df.empty or len(df) < 30:
        return {"symbol": symbol, "ok": False, "reason": "insufficient_history"}
    row = df.iloc[-1]
    return {
        "symbol": symbol,
        "ok": True,
        "triggered": any_entry_trigger(row),
        **trigger_summary(row),
        "payload": row_to_llm_payload(symbol, df),
        "as_of": str(df.index[-1].date()) if hasattr(df.index[-1], "date") else str(df.index[-1]),
    }


def build_universe_shortlist(
    *,
    load_rows: Callable[[str], list[dict[str, Any]]],
    limit: int = 500,
    max_shortlist: int = 30,
    max_workers: int = 8,
    symbols: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Scan Nifty 500; return stocks with ≥1 entry trigger on the latest bar."""
    syms = symbols or universe_symbols(limit)
    started = datetime.now(timezone.utc)
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    def work(sym: str) -> dict[str, Any]:
        rows = load_rows(sym)
        return analyze_symbol_rows(sym, rows)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(work, s): s for s in syms}
        for fut in as_completed(futures):
            sym = futures[fut]
            try:
                out = fut.result()
                if out.get("ok") and out.get("triggered"):
                    results.append(out)
            except Exception as exc:
                errors.append({"symbol": sym, "error": str(exc)[:200]})

    results.sort(key=lambda x: (-int(x.get("trigger_count") or 0), x.get("symbol") or ""))
    shortlist = results[:max_shortlist]
    payload = {
        "run_at": started.isoformat(),
        "universe_size": len(syms),
        "triggered_count": len(results),
        "shortlist_count": len(shortlist),
        "shortlist": shortlist,
        "llm_batch": [r["payload"] for r in shortlist if r.get("payload")],
        "errors": errors[:50],
        "elapsed_seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 2),
    }
    _save_cache(payload)
    return payload


def load_cached_shortlist() -> Optional[dict[str, Any]]:
    if not CACHE_PATH.exists():
        return None
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_quant_digest_lookup() -> dict[str, dict[str, Any]]:
    """Symbol → LLM row from latest daily pipeline snapshot (for agent veto)."""
    snap_dir = BASE_DIR / "data" / "quant_cache" / "features"
    if not snap_dir.exists():
        return {}
    snaps = sorted(snap_dir.glob("daily_snapshot_*.json"), reverse=True)
    if not snaps:
        return {}
    try:
        data = json.loads(snaps[0].read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in data.get("ranked") or []:
        sym = str(row.get("symbol") or "").upper()
        llm = row.get("llm") or {}
        if sym and llm:
            out[sym] = llm
            base = sym.replace(".NSE", "").replace(".BSE", "")
            out[base] = llm
    return out


def ensure_quant_shortlist(
    *,
    load_rows: Callable[[str], list[dict[str, Any]]],
    limit: int = 500,
    max_shortlist: int = 30,
    force: bool = False,
) -> dict[str, Any]:
    """Run Layer-1 scan if cache missing or stale (same UTC day)."""
    cached = load_cached_shortlist()
    if cached and not force:
        run_at = cached.get("run_at") or ""
        try:
            run_day = datetime.fromisoformat(run_at.replace("Z", "+00:00")).strftime("%Y-%m-%d")
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if run_day == today:
                return {"skipped": True, "reason": "cache_fresh", **cached}
        except Exception:
            pass
    return build_universe_shortlist(
        load_rows=load_rows,
        limit=limit,
        max_shortlist=max_shortlist,
    )


def _save_cache(payload: dict[str, Any]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def attach_quant_triggers(row: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge trigger flags into a screener/morning-scan row (in-process helper)."""
    analyzed = analyze_symbol_rows(str(row.get("symbol") or ""), rows)
    if not analyzed.get("ok"):
        return row
    merged = dict(row)
    merged["quant_triggers"] = analyzed.get("triggers_fired") or []
    merged["quant_trigger_count"] = analyzed.get("trigger_count") or 0
    merged["quant_regime_hint"] = analyzed.get("regime_hint")
    merged["quant_triggered"] = bool(analyzed.get("triggered"))
    if analyzed.get("quant_triggered") or analyzed.get("triggered"):
        merged["quant_trigger_boost"] = min(15.0, 3.0 * float(analyzed.get("trigger_count") or 0))
    else:
        merged["quant_trigger_boost"] = 0.0
    return merged
