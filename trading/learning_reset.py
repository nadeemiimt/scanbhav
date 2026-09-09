"""Reset trading RAG / learning artifacts — fresh start without touching book RAG or price data."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import BASE_DIR, setting

TRADING_DIR = BASE_DIR / "data" / "trading"
QUANT_CACHE = BASE_DIR / "data" / "quant_cache"
SESSION_REPORTS_DIR = TRADING_DIR / "session_reports"
INSIGHTS_COLLECTION = setting("INSIGHTS_COLLECTION", "stock_insights")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def clear_chroma_insights() -> dict[str, Any]:
    """Delete the stock_insights Chroma collection (autopilot, morning scan, forecasts, GenAI memos).

    Preserves the separate stock_books collection used for PDF book RAG.
    """
    import chromadb
    from config import CHROMA_PATH

    CHROMA_PATH.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    deleted = False
    count_before = 0
    try:
        coll = client.get_collection(name=INSIGHTS_COLLECTION)
        count_before = int(coll.count())
        client.delete_collection(name=INSIGHTS_COLLECTION)
        deleted = True
    except Exception:
        pass

    # Warm recreate so later append/query does not fail.
    client.get_or_create_collection(
        name=INSIGHTS_COLLECTION,
        metadata={"hnsw:space": "cosine", "purpose": "append-only stock GenAI insights"},
    )
    if deleted:
        try:
            import sqlite3

            db_path = CHROMA_PATH / "chroma.sqlite3"
            if db_path.exists():
                with sqlite3.connect(str(db_path)) as conn:
                    conn.execute("VACUUM")
        except Exception:
            pass
    return {"collection": INSIGHTS_COLLECTION, "deleted": deleted, "entries_before": count_before}


def reset_learning_json_files() -> dict[str, Any]:
    """Clear local JSON stores that feed RAG gates, scoring nudges, and journals."""
    from trading.autopilot import DEFAULT_WEIGHTS

    resets: dict[str, str] = {}

    _write_json(TRADING_DIR / "pick_log.json", {"picks": []})
    resets["pick_log"] = "cleared"

    _write_json(TRADING_DIR / "session_trades.json", {"trades": []})
    resets["session_trades"] = "cleared"

    _write_json(TRADING_DIR / "trade_decisions.json", {"decisions": []})
    resets["trade_decisions"] = "cleared"

    _write_json(TRADING_DIR / "symbol_day_blocks.json", {})
    resets["symbol_day_blocks"] = "cleared"

    _write_json(TRADING_DIR / "operational_lessons_state.json", {})
    resets["operational_lessons_state"] = "cleared"

    _write_json(
        TRADING_DIR / "timing_profiles.json",
        {"symbols": {}, "learned": 0, "rag_chunks": 0, "errors": []},
    )
    resets["timing_profiles"] = "cleared"

    _write_json(TRADING_DIR / "timing_market.json", {"profiles": {}, "updated_at": _now()})
    resets["timing_market"] = "cleared"

    _write_json(TRADING_DIR / "auto_profile_state.json", {})
    resets["auto_profile_state"] = "cleared"

    _write_json(TRADING_DIR / "daily_stats.json", {"days": []})
    resets["daily_stats"] = "cleared"

    _write_json(TRADING_DIR / "latency_compensation.json", {"symbols": {}})
    resets["latency_compensation"] = "cleared"

    _write_json(QUANT_CACHE / "trade_journal.json", {"entries": []})
    resets["trade_journal"] = "cleared"

    _write_json(
        TRADING_DIR / "calibration.json",
        {
            "weights": dict(DEFAULT_WEIGHTS),
            "adjustments": [],
            "scoreboard_summary": {
                "total": 0,
                "hit_rate_pct": None,
                "by_horizon": {},
                "by_stance": {},
            },
            "updated_at": _now(),
            "disclaimer": "Heuristic calibration from local scoreboard — not validated ML.",
        },
    )
    resets["calibration"] = "reset_defaults"

    return resets


def clear_session_reports() -> dict[str, Any]:
    """Remove stored session RAG digests (reports regenerate on next EOD)."""
    removed = 0
    if SESSION_REPORTS_DIR.is_dir():
        for path in SESSION_REPORTS_DIR.glob("*.json"):
            try:
                path.unlink()
                removed += 1
            except Exception:
                pass
    return {"removed": removed}


def strip_morning_scan_rag_refs() -> dict[str, Any]:
    """Keep today's scan rows but drop embedded RAG id lists."""
    path = TRADING_DIR / "morning_scan.json"
    if not path.exists():
        return {"skipped": True}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"skipped": True, "reason": "invalid_json"}
    data.pop("rag", None)
    data.pop("rag_ids", None)
    _write_json(path, data)
    return {"stripped": True}


def run_learning_reset(
    *,
    confirm: bool = False,
    keep_morning_scan_rows: bool = True,
    wipe_session_reports: bool = True,
) -> dict[str, Any]:
    """Wipe all trading-learning RAG. Requires confirm=true."""
    if not confirm:
        return {
            "ok": False,
            "error": "Pass confirm=true to wipe RAG / learning data.",
            "preserved": ["stock_books Chroma collection", "raw price data", "quant shortlist cache", "paper ledger"],
        }

    result: dict[str, Any] = {
        "ok": True,
        "at": _now(),
        "chroma": clear_chroma_insights(),
        "json": reset_learning_json_files(),
    }

    if wipe_session_reports:
        result["session_reports"] = clear_session_reports()

    if keep_morning_scan_rows:
        result["morning_scan"] = strip_morning_scan_rag_refs()
    else:
        path = TRADING_DIR / "morning_scan.json"
        if path.exists():
            path.unlink()
        result["morning_scan"] = {"removed_file": True}

    result["preserved"] = [
        "stock_books Chroma (PDF RAG)",
        "data/raw price history",
        "quant feature store / daily shortlist",
        "paper_ledger.json positions",
        "trading config",
    ]
    result["next_steps"] = [
        "Run Daily universe job before session",
        "Auto Pick will learn from new trades only",
        "RAG repeat-loser gate inactive until 2+ closed picks per symbol",
    ]
    return result
