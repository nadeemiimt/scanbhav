"""FastAPI route registration."""
from __future__ import annotations

from fastapi import FastAPI

from routes import advisor, auth, broker, broker_holdings, desk, genai, health, market, portfolio, predictions, quant_pipeline, stocks, swing, ta, trading, webhooks


def register_routes(app: FastAPI) -> None:
    app.include_router(auth.router)
    app.include_router(health.router)
    app.include_router(stocks.router)
    app.include_router(predictions.router)
    app.include_router(genai.router)
    app.include_router(market.router)
    app.include_router(ta.router)
    app.include_router(quant_pipeline.router)
    app.include_router(desk.router)
    app.include_router(swing.router)
    app.include_router(broker.router)
    app.include_router(broker_holdings.router)
    app.include_router(portfolio.router)
    app.include_router(advisor.router)
    app.include_router(trading.router)
    app.include_router(webhooks.router)


def mount_spa(app: FastAPI, base_dir) -> None:
    """Serve built frontend when frontend/dist exists."""
    from pathlib import Path

    from fastapi import HTTPException
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    from config import FRONTEND_DIST

    frontend_dist = Path(FRONTEND_DIST)
    if not frontend_dist.exists():
        fallback = Path(base_dir) / "frontend" / "dist"
        if fallback.exists():
            frontend_dist = fallback
        else:
            return

    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str) -> FileResponse:
        if full_path == "health" or full_path.startswith("api/") or full_path.startswith("api"):
            raise HTTPException(status_code=404, detail=f"No API route for /{full_path}")
        candidate = frontend_dist / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(
            frontend_dist / "index.html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"},
        )
