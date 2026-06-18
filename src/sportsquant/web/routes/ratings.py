"""Power Ratings route handlers for the SportsQuant web UI.

Renders the ratings viewer page with Massey, RAPTOR, and PageRank ratings.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates

from ..paths import TEMPLATES_DIR

router = APIRouter()
_templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/", response_class=HTMLResponse)
async def ratings_page(request: Request) -> HTMLResponse:
    """Render the ratings page with default sample data."""
    # Sample NBA ratings for demo — in production this would call the
    # actual ratings models via sportsquant.models.ratings
    sample_ratings = {
        "massey": [
            {"rank": 1, "team": "BOS", "rating": 8.42, "conference": "East"},
            {"rank": 2, "team": "OKC", "rating": 7.89, "conference": "West"},
            {"rank": 3, "team": "CLE", "rating": 7.21, "conference": "East"},
            {"rank": 4, "team": "DEN", "rating": 6.55, "conference": "West"},
            {"rank": 5, "team": "NYK", "rating": 5.88, "conference": "East"},
            {"rank": 6, "team": "MIN", "rating": 5.34, "conference": "West"},
            {"rank": 7, "team": "LAL", "rating": 4.72, "conference": "West"},
            {"rank": 8, "team": "MIL", "rating": 4.15, "conference": "East"},
            {"rank": 9, "team": "PHI", "rating": 3.68, "conference": "East"},
            {"rank": 10, "team": "DAL", "rating": 3.21, "conference": "West"},
        ],
        "raptor": [
            {"rank": 1, "team": "OKC", "rating": 9.12, "conference": "West"},
            {"rank": 2, "team": "BOS", "rating": 8.76, "conference": "East"},
            {"rank": 3, "team": "CLE", "rating": 7.45, "conference": "East"},
            {"rank": 4, "team": "DEN", "rating": 6.89, "conference": "West"},
            {"rank": 5, "team": "MIN", "rating": 6.12, "conference": "West"},
            {"rank": 6, "team": "NYK", "rating": 5.67, "conference": "East"},
            {"rank": 7, "team": "MIL", "rating": 4.93, "conference": "East"},
            {"rank": 8, "team": "LAL", "rating": 4.48, "conference": "West"},
            {"rank": 9, "team": "PHI", "rating": 3.92, "conference": "East"},
            {"rank": 10, "team": "DAL", "rating": 3.54, "conference": "West"},
        ],
        "pagerank": [
            {"rank": 1, "team": "BOS", "rating": 0.0312, "conference": "East"},
            {"rank": 2, "team": "OKC", "rating": 0.0289, "conference": "West"},
            {"rank": 3, "team": "CLE", "rating": 0.0264, "conference": "East"},
            {"rank": 4, "team": "DEN", "rating": 0.0241, "conference": "West"},
            {"rank": 5, "team": "NYK", "rating": 0.0218, "conference": "East"},
            {"rank": 6, "team": "MIN", "rating": 0.0195, "conference": "West"},
            {"rank": 7, "team": "LAL", "rating": 0.0172, "conference": "West"},
            {"rank": 8, "team": "MIL", "rating": 0.0149, "conference": "East"},
            {"rank": 9, "team": "PHI", "rating": 0.0128, "conference": "East"},
            {"rank": 10, "team": "DAL", "rating": 0.0105, "conference": "West"},
        ],
    }

    return _templates.TemplateResponse(
        request,
        "ratings.html",
        {
            "ratings": sample_ratings,
            "page_title": "Power Ratings",
        },
    )
