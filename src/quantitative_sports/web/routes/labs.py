"""Labs gallery route for the Quant-Sports web UI.

Renders the labs catalog listing all Jupyter notebook walkthroughs,
and serves pre-rendered HTML for individual lab notebooks.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from ..paths import LABS_HTML_DIR

router = APIRouter()

# Labs metadata (will be replaced when labs are written in Phase 4)
LABS_CATALOG: list[dict[str, str]] = [
    {
        "id": "01_getting_started",
        "title": "Getting Started",
        "description": "Install quantitative_sports, configure DB, first query.",
    },
    {
        "id": "02_data_ingestion",
        "title": "Data Ingestion",
        "description": "What the poller does, query raw data, backfill.",
    },
    {
        "id": "03_single_bet_ev",
        "title": "Single-Bet EV",
        "description": "From odds to Kelly-sized bet.",
    },
    {
        "id": "04_multi_book_middling",
        "title": "Multi-Book Middling",
        "description": "Detect and size middles across books.",
    },
    {
        "id": "05_building_backtest",
        "title": "Building a Backtest",
        "description": "Define strategy, run, interpret metrics.",
    },
    {
        "id": "06_nfl_game_prediction",
        "title": "NFL Game Prediction (XGBoost)",
        "description": "Train and predict NFL games.",
    },
    {
        "id": "07_ratings_systems",
        "title": "Ratings Systems",
        "description": "Elo, Massey, PageRank, Glicko.",
    },
    {
        "id": "08_live_workflow",
        "title": "Live Workflow",
        "description": "Start poller, find +EV, measure CLV.",
    },
    {
        "id": "09_custom_strategy",
        "title": "Custom Strategy",
        "description": "Subclass BaseStrategy, register, deploy.",
    },
    {
        "id": "10_production_patterns",
        "title": "Production Patterns",
        "description": "Scheduling, error handling, alerting.",
    },
]


@router.get("/labs", response_class=HTMLResponse)
async def labs_gallery(request: Request) -> HTMLResponse:
    """Render the labs gallery page listing all available labs."""
    return request.app.state.templates.TemplateResponse(
        request,
        "labs.html",
        {"request": request, "labs": LABS_CATALOG},
    )


@router.get("/labs/{name}")
async def lab_view(name: str) -> FileResponse:
    """Serve the pre-rendered HTML for a single lab notebook."""
    html_path = LABS_HTML_DIR / f"{name}.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail=f"Lab {name} not found")
    return FileResponse(html_path, media_type="text/html")
