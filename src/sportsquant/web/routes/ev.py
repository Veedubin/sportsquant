"""EV Calculator route handlers for the SportsQuant web UI.

Renders the EV calculator form (GET) and processes calculations (POST).
"""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates

from ..paths import TEMPLATES_DIR

router = APIRouter()
_templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/", response_class=HTMLResponse)
async def ev_form(request: Request) -> HTMLResponse:
    """Render the EV calculator form with no results."""
    return _templates.TemplateResponse(
        "ev.html",
        {"request": request, "result": None, "page_title": "EV Calculator"},
    )


@router.post("/", response_class=HTMLResponse)
async def ev_calculate(
    request: Request,
    line: float = Form(...),
    odds: int = Form(-110),
    prob: float = Form(...),
) -> HTMLResponse:
    """Process EV calculation from form inputs."""
    try:
        from sportsquant.core.betting.engine import (
            calculate_ev,
        )
        from sportsquant.core.betting.odds import Odds

        odds_obj = Odds(american=odds)
        decimal = odds_obj.to_decimal()
        implied_prob = odds_obj.implied_prob()

        ev = calculate_ev(probability=prob, odds=odds)

        # Kelly fraction: f = (p*b - (1-p)) / b where b = decimal - 1
        b = decimal - 1.0
        if b > 0:
            kelly = (prob * b - (1.0 - prob)) / b
            kelly = max(0.0, min(1.0, kelly))
        else:
            kelly = 0.0

        edge = prob - implied_prob

        result = {
            "line": line,
            "odds": odds,
            "prob": prob,
            "decimal": round(decimal, 3),
            "implied_prob": f"{implied_prob:.1%}",
            "ev": round(ev, 4),
            "ev_per_dollar": f"${ev:+.4f}" if ev else "$0.0000",
            "kelly": f"{kelly:.1%}",
            "kelly_raw": round(kelly, 4),
            "edge": f"{edge:+.1%}",
            "edge_raw": round(edge, 4),
            "recommendation": "BET" if ev > 0 else "PASS",
        }
    except Exception as e:
        result = {"error": str(e)}

    return _templates.TemplateResponse(
        "ev.html",
        {"request": request, "result": result, "page_title": "EV Calculator"},
    )
