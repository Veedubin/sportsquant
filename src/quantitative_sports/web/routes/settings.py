"""Settings route for the Quant-Sports web dashboard (v0.2.0).

Renders a read-only configuration page showing the current database connection,
scheduler setup, poller parameters, and source API settings.  All sensitive
values (passwords, API keys) are masked before being sent to the template.

In v0.2.0 the settings page is **display-only** — configuration is managed via
environment variables or docker-compose, not through the web UI (that would
require auth, which is out of scope).
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from quantitative_sports.infra.db.connection import DBConfig
from quantitative_sports.infra.poller.config import PollerConfig, get_active_sports

router = APIRouter()


def _mask(s: str, show_last: int = 4) -> str:
    """Mask a secret, showing only the last *show_last* characters.

    Args:
        s: The secret string to mask.
        show_last: Number of trailing characters to reveal.

    Returns:
        A masked representation like ``****abcd`` or ``"(not set)"``.
    """
    if not s:
        return "(not set)"
    if len(s) <= show_last:
        return "****"
    return "****" + s[-show_last:]


@router.get("/settings", response_class=HTMLResponse)
async def settings_get(request: Request) -> HTMLResponse:
    """Render the read-only settings page."""
    poller_cfg = PollerConfig()
    db_cfg = DBConfig()

    db_display = {
        "host": db_cfg.host,
        "port": db_cfg.port,
        "user": db_cfg.user,
        "password": _mask(db_cfg.password),
        "database": db_cfg.database,
    }

    odds_api_display = {
        "api_key": _mask(poller_cfg.odds_api.api_key),
        "base_url": poller_cfg.odds_api.base_url,
        "regions": poller_cfg.odds_api.regions,
        "markets": poller_cfg.odds_api.markets,
        "interval_seconds": poller_cfg.odds_api.interval_seconds,
    }

    espn_display = {
        "base_url": poller_cfg.espn.base_url,
        "interval_seconds": poller_cfg.espn.interval_seconds,
    }

    return request.app.state.templates.TemplateResponse(
        request,
        "settings.html",
        {
            "request": request,
            "scheduler": poller_cfg.scheduler,
            "active_sports": get_active_sports(poller_cfg),
            "log_level": poller_cfg.log_level,
            "max_retries": poller_cfg.max_retries,
            "retry_delay": poller_cfg.retry_delay,
            "db_display": db_display,
            "odds_api_display": odds_api_display,
            "espn_display": espn_display,
        },
    )


@router.post("/settings", response_class=HTMLResponse)
async def settings_post(request: Request) -> HTMLResponse:
    """Accept POST but ignore — settings are read-only in v0.2.0."""
    return await settings_get(request)
