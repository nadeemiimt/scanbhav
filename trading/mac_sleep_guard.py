"""Keep macOS awake while an all-day autopilot session is running (caffeinate)."""
from __future__ import annotations

import json
import platform
import shutil
import signal
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from config import BASE_DIR
from trading.config_store import load_trading_config
from trading.market_hours import nse_schedule, seconds_until_ist_minutes

STATE_PATH = BASE_DIR / "data" / "trading" / "mac_sleep_guard.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_macos() -> bool:
    return platform.system() == "Darwin"


def _caffeinate_path() -> Optional[str]:
    if not _is_macos():
        return None
    return shutil.which("caffeinate")


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if state:
        STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    elif STATE_PATH.exists():
        STATE_PATH.unlink(missing_ok=True)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import os
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _wake_until_minutes(cfg: dict[str, Any] | None = None) -> int:
    """Minutes from midnight IST to keep Mac awake (default 16:00 — through EOD square-off)."""
    ap = (cfg or load_trading_config()).get("autopilot") or {}
    override = ap.get("mac_sleep_guard_until_minute_ist")
    if override is not None and int(override) > 0:
        return int(override)
    sched = nse_schedule(cfg)
    # Stay awake 30 min past market close so post_close square-off retries can run.
    return int(sched["market_close"]) + 30


def sleep_guard_status() -> dict[str, Any]:
    state = _load_state()
    pid = int(state.get("pid") or 0)
    alive = _pid_alive(pid)
    if state and not alive:
        _save_state({})
        state = {}
    return {
        "supported": bool(_caffeinate_path()),
        "active": alive,
        "pid": pid if alive else None,
        "session_id": state.get("session_id"),
        "wake_until_ist": state.get("wake_until_ist"),
        "started_at": state.get("started_at"),
        "reason": state.get("reason"),
    }


def stop_mac_sleep_guard(*, reason: str = "session_stop") -> dict[str, Any]:
    state = _load_state()
    pid = int(state.get("pid") or 0)
    if pid and _pid_alive(pid):
        try:
            import os
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    _save_state({})
    return {"stopped": True, "reason": reason, "pid": pid or None}


def start_mac_sleep_guard(*, session_id: str = "", reason: str = "session_start") -> dict[str, Any]:
    cfg = load_trading_config()
    ap = cfg.get("autopilot") or {}
    if ap.get("prevent_mac_sleep_on_session", True) is False:
        return {"skipped": True, "reason": "prevent_mac_sleep_on_session_disabled"}

    caffeinate = _caffeinate_path()
    if not caffeinate:
        return {"skipped": True, "reason": "caffeinate_unavailable"}

    stop_mac_sleep_guard(reason="restart")

    wake_min = _wake_until_minutes(cfg)
    secs = seconds_until_ist_minutes(wake_min)
    if secs <= 0:
        return {"skipped": True, "reason": "wake_time_already_passed", "wake_until_minutes": wake_min}

    wake_h, wake_m = divmod(wake_min, 60)
    wake_label = f"{wake_h:02d}:{wake_m:02d}"

    proc = subprocess.Popen(
        [caffeinate, "-dims", "-t", str(secs)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    state = {
        "pid": proc.pid,
        "session_id": session_id,
        "wake_until_ist": wake_label,
        "wake_until_minutes": wake_min,
        "seconds": secs,
        "started_at": _now(),
        "reason": reason,
    }
    _save_state(state)

    return {
        "started": True,
        "pid": proc.pid,
        "session_id": session_id,
        "wake_until_ist": wake_label,
        "seconds": secs,
        "minutes": round(secs / 60),
    }


def ensure_mac_sleep_guard_on_startup() -> dict[str, Any]:
    """Re-attach caffeinate after API restart if session still active."""
    cfg = load_trading_config()
    ap = cfg.get("autopilot") or {}
    if not ap.get("session_active"):
        return {"skipped": True, "reason": "no_active_session"}

    status = sleep_guard_status()
    if status.get("active"):
        return {"skipped": True, "reason": "already_active", **status}

    return start_mac_sleep_guard(
        session_id=str(ap.get("session_id") or ""),
        reason="api_startup",
    )
