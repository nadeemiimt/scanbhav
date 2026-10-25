"""External-user prerequisites for packaged Scan Bhav (Windows / Mac)."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from typing import Any

from runtime_paths import APP_NAME, APP_VERSION, is_frozen, user_data_dir


OLLAMA_DOWNLOAD = {
    "darwin": "https://ollama.com/download/mac",
    "win32": "https://ollama.com/download/windows",
    "linux": "https://ollama.com/download/linux",
}


def _ollama_reachable() -> dict[str, Any]:
    host = (os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434").rstrip("/")
    try:
        import requests

        r = requests.get(f"{host}/api/tags", timeout=1.5)
        if r.ok:
            models = [m.get("name") for m in (r.json().get("models") or []) if m.get("name")]
            return {"ok": True, "host": host, "models": models[:12], "binary": shutil.which("ollama")}
    except Exception:
        pass
    return {"ok": False, "host": host, "models": [], "binary": shutil.which("ollama")}


def _has_browser() -> bool:
    try:
        import webbrowser

        return bool(webbrowser.get())
    except Exception:
        return True  # packaged builds still open the default handler in most cases


def _platform_label() -> str:
    sysname = platform.system()
    machine = platform.machine()
    if sys.platform == "darwin":
        return f"macOS {platform.mac_ver()[0] or ''} ({machine})".strip()
    if sys.platform == "win32":
        return f"Windows {platform.release()} ({machine})"
    return f"{sysname} {platform.release()} ({machine})"


def prerequisites_report() -> dict[str, Any]:
    """What an external user needs — required vs optional."""
    data = user_data_dir()
    ollama = _ollama_reachable()
    frozen = is_frozen()

    required = [
        {
            "id": "os",
            "label": "64-bit Windows 10/11 or macOS 12+",
            "ok": True,
            "plain": f"Detected: {_platform_label()}.",
        },
        {
            "id": "bundled_runtime",
            "label": "App runtime (Python + UI)",
            "ok": True,
            "plain": (
                "Bundled inside ScanBhav — you do not install Python or Node."
                if frozen
                else "Dev mode: use the project venv + npm (not needed for the shared .exe / .app)."
            ),
        },
        {
            "id": "browser",
            "label": "Any modern browser (Chrome / Edge / Safari / Firefox)",
            "ok": _has_browser(),
            "plain": "The app opens http://127.0.0.1:8000 automatically.",
        },
        {
            "id": "network",
            "label": "Internet for market prices (Yahoo / NSE)",
            "ok": True,
            "plain": "Offline mode is limited; Analyze / Screener need a connection.",
        },
    ]

    optional = [
        {
            "id": "ollama",
            "label": "Ollama (local GenAI — free)",
            "ok": bool(ollama.get("ok")),
            "plain": (
                f"Running at {ollama.get('host')} with {len(ollama.get('models') or [])} model(s)."
                if ollama.get("ok")
                else "Not required for Analyze / Screen / Paper Autopilot / Backtest. Needed only for local AI notes."
            ),
            "installable": True,
            "download_url": OLLAMA_DOWNLOAD.get(sys.platform, "https://ollama.com/download"),
        },
        {
            "id": "api_keys",
            "label": "Cloud API keys (OpenAI / Anthropic / Finnhub / …)",
            "ok": False,
            "plain": "Optional. Manage in Settings → Your API keys. None required for the core desk.",
            "installable": False,
        },
        {
            "id": "broker",
            "label": "Broker app keys (Zerodha / Groww / FYERS)",
            "ok": False,
            "plain": "Only for live ticks / live orders. Paper mode never needs a broker.",
            "installable": False,
        },
    ]

    os_notes: list[str] = []
    if sys.platform == "darwin":
        os_notes.append(
            "Unsigned Mac builds: right-click ScanBhav.app → Open → Open (Gatekeeper). "
            "Or: System Settings → Privacy & Security → Allow."
        )
        os_notes.append("Apple Silicon (M1/M2/M3) build is arm64; Intel Macs need a separate CI artifact.")
    if sys.platform == "win32":
        os_notes.append(
            "Windows may show SmartScreen for an unsigned .exe — More info → Run anyway. "
            "Keep the whole ScanBhav folder together (exe + _internal)."
        )
        os_notes.append(
            "If the app fails to start with a DLL error, install Microsoft Visual C++ Redistributable "
            "(x64) — the setup panel can open the download page."
        )

    marker = data / ".setup_seen"
    return {
        "app": APP_NAME,
        "version": APP_VERSION,
        "frozen": frozen,
        "platform": sys.platform,
        "platform_label": _platform_label(),
        "data_dir": str(data),
        "show_first_run": frozen and not marker.exists(),
        "headline": "No Python, Node, or paid API key is required to run Analyze, Screener, Backtest, or Paper Autopilot.",
        "required": required,
        "optional": optional,
        "ollama": ollama,
        "os_notes": os_notes,
        "vc_redist_url": "https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist",
    }


def mark_setup_seen() -> dict[str, Any]:
    path = user_data_dir() / ".setup_seen"
    path.write_text(APP_VERSION, encoding="utf-8")
    return {"ok": True, "path": str(path)}


def open_url(url: str) -> dict[str, Any]:
    import webbrowser

    webbrowser.open(url)
    return {"ok": True, "opened": url}


def install_or_open_ollama(*, prefer_package_manager: bool = True) -> dict[str, Any]:
    """Try winget/brew when available; otherwise open the official download page."""
    download = OLLAMA_DOWNLOAD.get(sys.platform, "https://ollama.com/download")
    steps: list[str] = []

    if prefer_package_manager:
        if sys.platform == "win32" and shutil.which("winget"):
            try:
                proc = subprocess.run(
                    ["winget", "install", "-e", "--id", "Ollama.Ollama", "--accept-package-agreements", "--accept-source-agreements"],
                    capture_output=True,
                    text=True,
                    timeout=600,
                )
                steps.append(f"winget exit {proc.returncode}")
                if proc.returncode == 0:
                    return {"ok": True, "method": "winget", "steps": steps, "hint": "Open a new terminal and run: ollama pull llama3.2:3b"}
            except Exception as exc:
                steps.append(f"winget failed: {exc}")

        if sys.platform == "darwin" and shutil.which("brew"):
            try:
                proc = subprocess.run(
                    ["brew", "install", "ollama"],
                    capture_output=True,
                    text=True,
                    timeout=600,
                )
                steps.append(f"brew exit {proc.returncode}")
                if proc.returncode == 0:
                    return {"ok": True, "method": "brew", "steps": steps, "hint": "Run: ollama serve && ollama pull llama3.2:3b"}
            except Exception as exc:
                steps.append(f"brew failed: {exc}")

    open_url(download)
    steps.append(f"opened {download}")
    return {
        "ok": True,
        "method": "download_page",
        "steps": steps,
        "hint": "Install Ollama from the browser page, then reopen Scan Bhav and click Refresh.",
        "download_url": download,
    }


def open_vc_redist() -> dict[str, Any]:
    return open_url("https://aka.ms/vs/17/release/vc_redist.x64.exe")
