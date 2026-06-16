"""SportsQuant REST API package.

Exposes core betting, risk, backtest, ratings, and analysis functionality
as FastAPI endpoints with OpenTelemetry instrumentation.

Entry point: ``sportsquant-api = "sportsquant.api.betting_api:app"``
"""

from sportsquant.api.betting_api import app

__all__ = ["app"]
