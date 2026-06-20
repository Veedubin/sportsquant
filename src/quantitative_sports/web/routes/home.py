"""Home / overview route for the Quant-Sports poller dashboard.

Renders a landing page showing all pollers with their health status,
last run info, and quick links to drill-down detail pages.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from quantitative_sports.infra.db.connection import get_pool
from quantitative_sports.infra.db.queries import get_poller_health_summary

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    """Render the home page with poller health summary."""
    pool = await get_pool()
    pollers = await get_poller_health_summary(pool)
    return request.app.state.templates.TemplateResponse(
        request,
        "home.html",
        {"request": request, "pollers": pollers},
    )
