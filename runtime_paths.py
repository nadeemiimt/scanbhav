"""Resolve install vs user-writable paths for dev and PyInstaller builds."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "StockAdda"
APP_VERSION = "0.6.0"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_dir() -> Path:
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent


def user_data_dir() -> Path:
    if not is_frozen():
        return Path(__file__).resolve().parent

    override = os.environ.get("STOCK_ADDA_DATA", "").strip()
    if override:
        path = Path(override).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        path = Path(base) / APP_NAME
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        path = Path.home() / f".{APP_NAME.lower()}"

    path.mkdir(parents=True, exist_ok=True)
    return path


def frontend_dist_path() -> Path:
    bundled = bundle_dir() / "frontend" / "dist"
    if bundled.is_dir():
        return bundled
    return Path(__file__).resolve().parent / "frontend" / "dist"


def logs_dir() -> Path:
    path = user_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _copy_tree(src: Path, dest: Path) -> None:
    if not src.exists():
        return
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dest / item.name
        if item.is_dir():
            if not target.exists():
                shutil.copytree(item, target)
        elif not target.exists():
            shutil.copy2(item, target)


def ensure_first_run() -> None:
    """Seed ~/StockAdda (or platform equivalent) from bundled templates on first launch."""
    if not is_frozen():
        return

    user_root = user_data_dir()
    marker = user_root / ".installed"
    seed_root = bundle_dir() / "bundle_data"

    if marker.exists():
        return

    if seed_root.is_dir():
        _copy_tree(seed_root, user_root)

    env_example = bundle_dir() / ".env.example"
    env_target = user_root / ".env"
    if env_example.is_file() and not env_target.is_file():
        shutil.copy2(env_example, env_target)

    for sub in ("data/chroma", "data/raw", "data/trading/session_reports", "data/screen_cache", "data/quant_cache"):
        (user_root / sub).mkdir(parents=True, exist_ok=True)

    marker.write_text(f"{APP_VERSION}\n", encoding="utf-8")
