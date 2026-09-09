"""Stock Adda desktop launcher — starts the local API and opens the dashboard."""
from __future__ import annotations

import argparse
import logging
import multiprocessing
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path


def _setup_paths() -> Path:
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return root


def _configure_logging() -> None:
    from runtime_paths import is_frozen, logs_dir

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if is_frozen():
        log_file = logs_dir() / "stock-adda.log"
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=handlers,
    )


def _open_browser(url: str, delay: float = 2.0) -> None:
    time.sleep(delay)
    try:
        webbrowser.open(url)
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    multiprocessing.freeze_support()
    _setup_paths()
    _configure_logging()

    parser = argparse.ArgumentParser(description="Stock Adda — local research & autopilot desk")
    parser.add_argument("--host", default=os.environ.get("STOCK_ADDA_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("STOCK_ADDA_PORT", "8000")))
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser tab")
    args = parser.parse_args(argv)

    from runtime_paths import APP_NAME, APP_VERSION, is_frozen, user_data_dir

    url = f"http://{args.host}:{args.port}"
    data_dir = user_data_dir()
    log = logging.getLogger("launcher")

    log.info("%s v%s starting", APP_NAME, APP_VERSION)
    log.info("Data directory: %s", data_dir)
    if is_frozen():
        log.info("Packaged build — edit %s/.env for API keys", data_dir)
    log.info("Dashboard: %s", url)

    if not args.no_browser:
        threading.Thread(target=_open_browser, args=(url,), daemon=True).start()

    import uvicorn

    uvicorn.run(
        "api:app",
        host=args.host,
        port=args.port,
        log_level="info",
        access_log=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
