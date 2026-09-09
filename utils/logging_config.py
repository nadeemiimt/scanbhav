"""Application-wide logging configuration."""
from __future__ import annotations

import logging
import sys
from typing import Optional

from config import setting

_CONFIGURED = False
_DEFAULT_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging(level: Optional[str] = None) -> None:
    """Configure root logging once per process."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_level = (level or setting("LOG_LEVEL", "INFO")).upper()
    log_format = setting("LOG_FORMAT", _DEFAULT_FORMAT)

    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format=log_format,
        stream=sys.stdout,
        force=True,
    )

    # Quiet noisy third-party loggers unless DEBUG
    if log_level != "DEBUG":
        for name in ("urllib3", "httpx", "httpcore", "chromadb", "watchfiles", "yfinance"):
            logging.getLogger(name).setLevel(logging.WARNING)

    _CONFIGURED = True
    logging.getLogger(__name__).debug("Logging configured at level %s", log_level)


def get_logger(name: str) -> logging.Logger:
    """Return a module logger, ensuring logging is configured."""
    if not _CONFIGURED:
        configure_logging()
    return logging.getLogger(name)
