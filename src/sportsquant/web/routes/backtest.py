"""Backtest route handlers for the SportsQuant web UI.

Renders the backtest form (GET) and processes backtest runs (POST).
"""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates

from ..paths import TEMPLATES_DIR

router = APIRouter()
_templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/", response_class=HTMLResponse)
async def backtest_form(request: Request) -> HTMLResponse:
    """Render the backtest form with no results."""
    return _templates.TemplateResponse(
        request,
        "backtest.html",
        {"result": None, "page_title": "Backtest"},
    )


@router.post("/", response_class=HTMLResponse)
async def backtest_run(
    request: Request,
    strategy: str = Form("value"),
    bankroll: float = Form(1000.0),
    kelly_fraction: float = Form(0.25),
    min_edge: float = Form(0.02),
    n_simulations: int = Form(1000),
) -> HTMLResponse:
    """Run a simulated backtest with the given parameters."""
    try:
        import random

        random.seed(42)  # Deterministic for demo purposes

        # Simulate backtest results based on strategy parameters
        # In production, this would use the actual backtesting engine
        n_bets = n_simulations
        edge = min_edge + random.gauss(0, 0.01)

        # Expected win rate with value betting at given edge
        base_win_rate = 0.52 + edge
        wins = sum(1 for _ in range(n_bets) if random.random() < base_win_rate)
        win_rate = wins / n_bets

        # ROI calculation (simplified with -110 odds)
        avg_odds_decimal = 1.909  # -110 American odds
        profit_per_win = avg_odds_decimal - 1.0
        roi_pct = (win_rate * profit_per_win - (1 - win_rate)) * 100

        # Sharpe-like ratio (simplified)
        returns = [
            (profit_per_win if random.random() < base_win_rate else -1.0)
            for _ in range(min(n_bets, 500))
        ]
        avg_return = sum(returns) / len(returns) if returns else 0.0
        std_return = (
            (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5 if returns else 1.0
        )
        sharpe = avg_return / std_return if std_return > 0 else 0.0

        # Max drawdown (simplified)
        cumulative = 0.0
        peak = 0.0
        max_drawdown = 0.0
        for r in returns:
            cumulative += r * bankroll * kelly_fraction
            peak = max(peak, cumulative)
            drawdown = (peak - cumulative) / bankroll if bankroll > 0 else 0
            max_drawdown = max(max_drawdown, drawdown)

        result = {
            "strategy": strategy,
            "bankroll": bankroll,
            "kelly_fraction": kelly_fraction,
            "min_edge": min_edge,
            "n_simulations": n_simulations,
            "n_bets": n_bets,
            "wins": wins,
            "win_rate": f"{win_rate:.1%}",
            "win_rate_raw": round(win_rate, 4),
            "roi": f"{roi_pct:+.2f}%",
            "roi_raw": round(roi_pct, 2),
            "sharpe": round(sharpe, 3),
            "max_drawdown": f"{max_drawdown:.1%}",
            "max_drawdown_raw": round(max_drawdown, 4),
        }
    except Exception as e:
        result = {"error": str(e)}

    return _templates.TemplateResponse(
        request,
        "backtest.html",
        {"result": result, "page_title": "Backtest"},
    )
