"""FastAPI backend for the local stock research dashboard."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import BASE_DIR
from routes import mount_spa, register_routes
from utils.logging_config import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)

app = FastAPI(title="Scan Bhav Research API", version="0.6.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.on_event("startup")
async def _on_startup() -> None:
    logger.info("Stock Technical Intelligence API starting (v%s)", app.version)
    from brokers.ltp_stream import start_ltp_stream
    from trading.scheduler import start_scheduler

    start_ltp_stream()
    start_scheduler()
    try:
        from trading.mac_sleep_guard import ensure_mac_sleep_guard_on_startup

        result = ensure_mac_sleep_guard_on_startup()
        if result.get("started"):
            logger.info("Mac sleep guard started: %s", result)
    except Exception as exc:
        logger.warning("Mac sleep guard startup skipped: %s", exc)


@app.on_event("shutdown")
async def _on_shutdown() -> None:
    from brokers.ltp_stream import stop_ltp_stream
    from trading.scheduler import stop_scheduler

    stop_scheduler()
    stop_ltp_stream()


@app.exception_handler(Exception)
async def _unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


register_routes(app)
mount_spa(app, BASE_DIR)
