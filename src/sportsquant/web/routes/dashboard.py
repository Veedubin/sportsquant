"""Dashboard route handlers for the SportsQuant web UI.

Renders the main dashboard page with overview stats, supported sports,
and quick links to tools.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates

from ..paths import TEMPLATES_DIR

router = APIRouter()
_templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    """Render the main dashboard with overview cards."""
    stats = {
        "total_tools": 37,
        "cli_commands": 19,
        "notebooks": 8,
        "tests_passing": 692,
        "sports_supported": ["NBA", "NFL", "MLB", "NHL", "PGA"],
    }
    return _templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "stats": stats, "page_title": "Dashboard"},
    )
