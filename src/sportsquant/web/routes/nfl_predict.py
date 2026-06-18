"""NFL game prediction route for the SportsQuant web UI.

Renders the NFL XGBoost predictor form (GET) and processes predictions (POST).
Wires the :class:`sportsquant.models.predictive.nfl_game_model.NFLGamePredictor`
into the dashboard.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates

from ..paths import TEMPLATES_DIR

logger = logging.getLogger(__name__)

router = APIRouter()
_templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# Cache the default trained model so we don't retrain on every request.
_predictor_cache: dict[str, Any] = {}


def _get_predictor() -> Any:
    """Return cached default NFLGamePredictor (synthetic bootstrap)."""
    if "default" not in _predictor_cache:
        from sportsquant.models.predictive.nfl_game_model import train_default_model

        _predictor_cache["default"] = train_default_model(n_games=200, verbose=False)
    return _predictor_cache["default"]


@router.get("/", response_class=HTMLResponse)
async def nfl_predict_form(request: Request) -> HTMLResponse:
    """Render the NFL prediction form with no results."""
    return _templates.TemplateResponse(
        request,
        "nfl_predict.html",
        {
            "result": None,
            "page_title": "NFL Game Predictor",
            "feature_importances": [],
        },
    )


@router.post("/", response_class=HTMLResponse)
async def nfl_predict_run(
    request: Request,
    home: str = Form("KC"),
    away: str = Form("BAL"),
    season: int = Form(2024),
    week: int = Form(10),
    home_ppg_for: float = Form(22.0),
    home_ppg_against: float = Form(22.0),
    home_yards_per_play: float = Form(5.5),
    home_turnover_rate: float = Form(1.4),
    home_qb_rating: float = Form(85.0),
    away_ppg_for: float = Form(22.0),
    away_ppg_against: float = Form(22.0),
    away_yards_per_play: float = Form(5.5),
    away_turnover_rate: float = Form(1.4),
    away_qb_rating: float = Form(85.0),
    rest_advantage: float = Form(0.0),
    model_path: str = Form(""),
) -> HTMLResponse:
    """Predict NFL game outcome from form inputs."""
    try:
        from sportsquant.models.predictive.nfl_game_model import (
            NFLGameFeatures,
            NFLGamePredictor,
        )

        # Load predictor (from path or default)
        if model_path and Path(model_path).exists():
            predictor = NFLGamePredictor.load(Path(model_path))
            model_source = f"loaded from {model_path}"
        else:
            predictor = _get_predictor()
            model_source = "default synthetic model (n=200 games)"

        features = NFLGameFeatures(
            home_team=home.upper(),
            away_team=away.upper(),
            season=season,
            week=week,
            home_ppg_for=home_ppg_for,
            home_ppg_against=home_ppg_against,
            home_yards_per_play=home_yards_per_play,
            home_turnover_rate=home_turnover_rate,
            home_qb_rating=home_qb_rating,
            away_ppg_for=away_ppg_for,
            away_ppg_against=away_ppg_against,
            away_yards_per_play=away_yards_per_play,
            away_turnover_rate=away_turnover_rate,
            away_qb_rating=away_qb_rating,
            ppg_differential=home_ppg_for - away_ppg_for,
            defense_differential=away_ppg_against - home_ppg_against,
            home_advantage=2.5,
            rest_advantage=rest_advantage,
        )
        pred = predictor.predict(features)

        # Build sorted feature importances for display
        importances = sorted(
            predictor.feature_importances.items(),
            key=lambda x: -x[1],
        )

        result = {
            "home": home.upper(),
            "away": away.upper(),
            "season": season,
            "week": week,
            "home_win_prob": pred.home_win_prob,
            "away_win_prob": pred.away_win_prob,
            "proj_spread": pred.proj_spread,
            "proj_total": pred.proj_total,
            "model_source": model_source,
            "success": True,
        }
    except Exception as e:
        logger.exception("NFL prediction failed")
        result = {"success": False, "error": str(e)}
        importances = []

    return _templates.TemplateResponse(
        request,
        "nfl_predict.html",
        {
            "result": result,
            "page_title": "NFL Game Predictor",
            "feature_importances": importances,
        },
    )
