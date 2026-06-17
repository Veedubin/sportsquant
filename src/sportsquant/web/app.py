"""SportsQuant Web Dashboard — FastAPI + Jinja2 + uvicorn.

Creates a configured FastAPI app with static file serving, Jinja2
templates, and route handlers for dashboard, EV calculator,
backtest results, and power ratings pages.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .paths import STATIC_DIR
from .routes.backtest import router as backtest_router
from .routes.dashboard import router as dashboard_router
from .routes.ev import router as ev_router
from .routes.ratings import router as ratings_router


def create_app() -> FastAPI:
    """Build and return a configured FastAPI application."""
    app = FastAPI(
        title="SportsQuant Dashboard",
        version="0.2.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    # Static files
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Routes
    app.include_router(dashboard_router)
    app.include_router(ev_router, prefix="/ev")
    app.include_router(backtest_router, prefix="/backtest")
    app.include_router(ratings_router, prefix="/ratings")

    return app


app = create_app()
