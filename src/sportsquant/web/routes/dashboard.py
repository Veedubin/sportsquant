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
        "cli_commands": 20,
        "notebooks": 9,
        "tests_passing": 762,
        "sports_supported": ["NBA", "NFL", "MLB", "NHL", "PGA"],
        "nfl_modules": [
            "NFLDataPipeline (nflfastR + ESPN + Pinnacle)",
            "NFL Game Predictor (XGBoost ensemble)",
            "Multi-book Odds Aggregator (Odds API)",
            "Spread & Total Middling Detection",
            "NFL Advanced Metrics (EPA/DVOA/QBR)",
        ],
    }
    return _templates.TemplateResponse(
        request,
        "dashboard.html",
        {"stats": stats, "page_title": "Dashboard"},
    )
