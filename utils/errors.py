"""Error helpers for consistent logging at module boundaries."""
from __future__ import annotations

from typing import Any, Optional

from utils.logging_config import get_logger

logger = get_logger(__name__)


def log_exception(
    message: str,
    *,
    exc: Optional[BaseException] = None,
    level: str = "warning",
    extra: Optional[dict[str, Any]] = None,
) -> None:
    """Log an exception with optional structured context."""
    log_fn = getattr(logger, level, logger.warning)
    exc_info = (type(exc), exc, exc.__traceback__) if exc is not None else None
    log_fn(message, exc_info=exc_info, extra=extra or {})


def swallow(message: str, exc: BaseException, *, level: str = "debug") -> None:
    """Log and suppress a non-fatal error (use sparingly)."""
    log_exception(f"{message}: {exc}", exc=exc, level=level)
