"""Quant-Sports Web Dashboard — FastAPI + Jinja2 + uvicorn.

Creates a configured FastAPI app with static file serving, Jinja2
templates, and route handlers for the poller ops dashboard.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .paths import STATIC_DIR, TEMPLATES_DIR
from .routes.docs import router as docs_router
from .routes.home import router as home_router
from .routes.labs import router as labs_router
from .routes.metrics import router as metrics_router
from .routes.poller import router as poller_router
from .routes.settings import router as settings_router


def create_app() -> FastAPI:
    """Build and return a configured FastAPI application."""
    app = FastAPI(
        title="Quant-Sports Dashboard",
        version="0.2.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    # Templates and static
    app.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Routes (no prefix — routes define their own paths)
    app.include_router(home_router)  # GET /
    app.include_router(poller_router)  # GET /poller/{name}, GET /api/poller/{name}/logs
    app.include_router(metrics_router)  # GET /metrics
    app.include_router(labs_router)  # GET /labs, GET /labs/{name}
    app.include_router(docs_router)  # GET /docs
    app.include_router(settings_router)  # GET /settings, POST /settings

    return app


app = create_app()
