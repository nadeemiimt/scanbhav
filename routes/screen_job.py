"""Background Nifty 500 screen job — keeps API responsive during long scans."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from config import BASE_DIR
from routes.schemas import TaScreenRequest
from routes.screen_checkpoint import (
    checkpoint_request_matches,
    checkpoint_summary,
    clear_checkpoint,
    load_checkpoint,
    load_checkpoint_meta,
    save_checkpoint,
)

JOB_PATH = BASE_DIR / "data" / "screen_cache" / "job_status.json"
ScreenJobMode = Literal["fresh", "resume", "restart"]

_lock = threading.Lock()
_screen_thread: Optional[threading.Thread] = None
_last_progress_persist = 0.0
_last_checkpoint_persist = 0.0
_job: dict[str, Any] = {
    "running": False,
    "phase": "idle",
    "started_at": None,
    "finished_at": None,
    "error": None,
    "scored": None,
    "failed": None,
    "progress": None,
    "mode": None,
}


def _load_persisted_job() -> dict[str, Any]:
    if not JOB_PATH.exists():
        return {}
    try:
        return json.loads(JOB_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _persist_job() -> None:
    JOB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        snapshot = dict(_job)
    JOB_PATH.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")


def _request_dict(request: TaScreenRequest) -> dict[str, Any]:
    return request.model_dump()


def screen_job_status() -> dict[str, Any]:
    with _lock:
        status = dict(_job)
    ck = checkpoint_summary()
    status["checkpoint"] = ck
    status["can_resume"] = bool(ck.get("available")) and not status.get("running")
    return status


def _set(**kwargs: Any) -> None:
    with _lock:
        _job.update(kwargs)
    _persist_job()


def start_screen_job(request: TaScreenRequest, mode: ScreenJobMode = "fresh") -> dict[str, Any]:
    global _screen_thread
    with _lock:
        if _job.get("running"):
            if _screen_thread is not None and _screen_thread.is_alive():
                return {"accepted": False, "running": True, "message": "Screen already in progress", **dict(_job)}
            _job["running"] = False

    if mode == "restart":
        clear_checkpoint()
        mode = "fresh"
    elif mode == "fresh":
        clear_checkpoint()
    elif mode == "resume":
        meta = checkpoint_summary()
        if not meta.get("available"):
            return {
                "accepted": False,
                "running": False,
                "message": "No checkpoint to resume — run a fresh screen first.",
                "can_resume": False,
            }
        if not checkpoint_request_matches(_request_dict(request), meta):
            return {
                "accepted": False,
                "running": False,
                "message": "Checkpoint settings differ (horizon/limit/bucket). Use Restart or match prior settings.",
                "can_resume": True,
            }

    resumed_from = 0
    if mode == "resume":
        meta = checkpoint_summary()
        resumed_from = int(meta.get("scored") or 0)

    with _lock:
        _job.update({
            "running": True,
            "phase": "starting",
            "mode": mode,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
            "error": None,
            "scored": None,
            "failed": None,
            "resumed_from": resumed_from if mode == "resume" else None,
            "progress": {
                "total": request.limit,
                "scored_so_far": resumed_from if mode == "resume" else 0,
                "failed_so_far": 0,
            },
        })
    _persist_job()

    thread = threading.Thread(target=_run, args=(request, mode), daemon=True, name="screen-job")
    _screen_thread = thread
    thread.start()
    msg = "Screen started in background"
    if mode == "resume":
        msg = f"Resuming screen from {resumed_from} scored symbols"
    return {"accepted": True, "running": True, "message": msg, "mode": mode}


def _progress_callback(total: int):
    def _cb(scored: int, failed: int) -> None:
        global _last_progress_persist
        with _lock:
            _job["progress"] = {"total": total, "scored_so_far": scored, "failed_so_far": failed}
        now = time.monotonic()
        if now - _last_progress_persist >= 2.0 or scored + failed >= total:
            _last_progress_persist = now
            _persist_job()
    return _cb


def _checkpoint_callback(request: TaScreenRequest, started_at: str, universe_size: int):
    def _cb(results: list[dict[str, Any]], error_map: dict[str, str]) -> None:
        global _last_checkpoint_persist
        now = time.monotonic()
        if now - _last_checkpoint_persist < 15.0 and len(results) % 25 != 0:
            return
        _last_checkpoint_persist = now
        save_checkpoint(
            request=_request_dict(request),
            results=results,
            error_map=error_map,
            universe_size=universe_size,
            started_at=started_at,
        )
    return _cb


def _run(request: TaScreenRequest, mode: ScreenJobMode = "fresh") -> None:
    started_at = datetime.now(timezone.utc).isoformat()
    initial_results: list[dict[str, Any]] = []
    initial_error_map: dict[str, str] = {}
    if mode == "resume":
        ck = load_checkpoint() or {}
        initial_results = list(ck.get("results") or [])
        initial_error_map = {
            str(e.get("symbol") or ""): str(e.get("error") or "")
            for e in (ck.get("errors") or [])
            if e.get("symbol")
        }
        started_at = str(ck.get("started_at") or started_at)

    try:
        from routes.helpers import fetch_prices_light, rows_from_payload, warm_price_cache_batched
        from screener import screen_universe
        from universe import universe_symbols
        from universe_refresh import ensure_universe_fresh

        ensure_universe_fresh(force=False)
        eff_limit = request.limit
        if request.bucket:
            eff_limit = {"large": 100, "mid": 150, "small": 250}.get(request.bucket, request.limit)
        elif eff_limit < 500:
            eff_limit = 500
        symbols = universe_symbols(eff_limit, bucket=request.bucket)
        total = len(symbols)
        done_syms = {str(r.get("symbol") or "").upper() for r in initial_results}
        remaining = [s for s in symbols if s.upper() not in done_syms]

        _set(
            phase="warming_cache",
            progress={
                "total": total,
                "scored_so_far": len(initial_results),
                "failed_so_far": len(initial_error_map),
            },
        )
        warm_stats = {"warmed": 0, "requested": 0}
        if remaining:
            warm_stats = warm_price_cache_batched(
                remaining,
                force_refresh=request.force_refresh,
                chunk_size=request.batch_size,
                pause_seconds=request.batch_pause_seconds,
                batch_strategy=request.batch_strategy,
            )

        def load_rows(symbol: str) -> list[dict[str, Any]]:
            if request.provider == "auto":
                bulk_provider = "auto"
                allow_nse = True
            else:
                bulk_provider = "yfinance" if request.provider == "yfinance" else request.provider
                allow_nse = request.provider == "nse"
            payload = fetch_prices_light(
                symbol,
                force_refresh=request.force_refresh,
                provider=bulk_provider,
                allow_nse_fallback=allow_nse,
                retries=3,
                retry_delay=2.5,
            )
            rows = rows_from_payload(payload)
            if len(rows) < 30:
                raise ValueError("insufficient history")
            return rows

        _set(
            phase="scoring",
            progress={
                "total": total,
                "scored_so_far": len(initial_results),
                "failed_so_far": len(initial_error_map),
                "warmed": warm_stats.get("warmed"),
            },
        )
        score_pause = 0.0 if warm_stats.get("requested", 0) == 0 else request.batch_pause_seconds
        result = screen_universe(
            load_rows=load_rows,
            limit=eff_limit,
            max_workers=request.max_workers,
            horizon=request.horizon,
            bucket=request.bucket,
            data_provider=request.provider,
            batch_size=request.batch_size,
            batch_pause_seconds=request.batch_pause_seconds,
            score_batch_pause_seconds=score_pause,
            retry_rounds=request.retry_rounds,
            retry_pause_seconds=request.retry_pause_seconds,
            batch_strategy=request.batch_strategy,
            on_progress=_progress_callback(total),
            initial_results=initial_results,
            initial_error_map=initial_error_map,
            on_checkpoint=_checkpoint_callback(request, started_at, total),
        )
        _set(
            running=False,
            phase="done",
            mode=None,
            finished_at=datetime.now(timezone.utc).isoformat(),
            scored=result.get("scored"),
            failed=result.get("failed"),
            progress={
                "total": total,
                "scored_so_far": result.get("scored"),
                "failed_so_far": result.get("failed"),
            },
        )
    except Exception as exc:
        _set(
            running=False,
            phase="error",
            mode=None,
            finished_at=datetime.now(timezone.utc).isoformat(),
            error=str(exc)[:500],
        )


_persisted = _load_persisted_job()
if _persisted:
    if _persisted.get("running") and _persisted.get("phase") not in {"done", "error"}:
        _persisted["running"] = False
        _persisted["phase"] = "interrupted"
        ck = load_checkpoint_meta() or checkpoint_summary()
        if ck.get("available"):
            _persisted["error"] = (
                f"Scan interrupted at {ck.get('scored')}/{ck.get('universe_size')} — "
                "checkpoint saved. Use Resume or Restart."
            )
            _persisted["progress"] = {
                "total": ck.get("universe_size"),
                "scored_so_far": ck.get("scored"),
                "failed_so_far": ck.get("failed"),
            }
        else:
            _persisted["error"] = _persisted.get("error") or (
                "Scan interrupted — API reloaded during background job. Run again."
            )
        _persisted["finished_at"] = datetime.now(timezone.utc).isoformat()
    with _lock:
        _job.update(_persisted)
    _persist_job()
