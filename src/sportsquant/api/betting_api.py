"""SportsQuant REST API with OpenTelemetry instrumentation.

Exposes core betting, risk, backtest, ratings, and analysis functionality
as REST endpoints with distributed tracing, metrics, and structured logging.

Pattern adapted from Sports-Platform betting_api.py.
"""

from __future__ import annotations

import io
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pydantic import BaseModel, Field

from sportsquant.core.betting.engine import (
    expected_value,
    kelly_fraction,
)
from sportsquant.core.betting.kelly import (
    KellyCalculator,
)
from sportsquant.core.betting.odds import Odds
from sportsquant.util.nba_logging import configure_logging, get_logger

# ---------------------------------------------------------------------------
# Logging & Telemetry bootstrap
# ---------------------------------------------------------------------------

SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "sportsquant-api")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

configure_logging(level=LOG_LEVEL)
logger = get_logger(__name__)


def _init_telemetry(service_name: str) -> tuple[trace.Tracer, metrics.Meter]:
    """Initialize OpenTelemetry tracing and metrics with OTLP exporter."""
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": "0.1.0",
            "deployment.environment": os.getenv("OTEL_ENVIRONMENT", "development"),
        }
    )

    # Tracing
    tracer_provider = TracerProvider(resource=resource)
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    try:
        exporter = OTLPSpanExporter(
            endpoint=otlp_endpoint,
            insecure=otlp_endpoint.startswith("http://"),
        )
        tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
        logger.info("OTLP trace exporter configured: %s", otlp_endpoint)
    except Exception:
        logger.warning("OTLP exporter unavailable — traces will be NoOp")

    trace.set_tracer_provider(tracer_provider)

    # Metrics
    meter_provider = MeterProvider(resource=resource)
    metrics.set_meter_provider(meter_provider)

    return trace.get_tracer(service_name), metrics.get_meter(service_name)


tracer, meter = _init_telemetry(SERVICE_NAME)


class APIMetrics:
    """HTTP API metrics helper following Sports-Platform APIMetrics pattern."""

    def __init__(self, m: metrics.Meter) -> None:
        self._request_count = m.create_counter(
            name="http.requests.total",
            description="Total HTTP requests",
            unit="1",
        )
        self._request_duration = m.create_counter(
            name="http.request.duration_ms",
            description="HTTP request duration (ms)",
            unit="ms",
        )
        self._error_count = m.create_counter(
            name="http.errors",
            description="Total HTTP errors",
            unit="1",
        )

    def record_request(
        self, method: str, endpoint: str, status_code: int, duration_ms: float
    ) -> None:
        attrs = {"method": method, "endpoint": endpoint, "status": str(status_code)}
        self._request_count.add(1, attrs)
        self._request_duration.add(duration_ms, {"method": method, "endpoint": endpoint})
        if status_code >= 400:
            self._error_count.add(1, attrs)


api_metrics = APIMetrics(meter)


def _record_metrics(endpoint: str, status_code: int, latency_s: float) -> None:
    api_metrics.record_request("POST", endpoint, status_code, latency_s * 1000)


# ---------------------------------------------------------------------------
# Pydantic v2 request / response models
# ---------------------------------------------------------------------------

# -- Health --


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: datetime


# -- Betting Math --


class EVRequest(BaseModel):
    line: float = Field(..., description="Betting line (e.g. 40.5)")
    odds: str = Field(..., description="American odds (e.g. '-110', '+105')")
    probability: float = Field(..., ge=0.0, le=1.0, description="Estimated true probability")


class EVResponse(BaseModel):
    ev: float
    recommendation: str
    kelly_fraction: float


class KellyRequest(BaseModel):
    edge: float = Field(..., description="Estimated edge (0-1)")
    odds: str = Field(..., description="American odds (e.g. '-110')")
    bankroll: float = Field(..., gt=0, description="Current bankroll")
    fractional: float = Field(0.25, ge=0.0, le=1.0, description="Fractional Kelly multiplier")


class KellyResponse(BaseModel):
    full_kelly: float
    fractional_kelly: float
    recommended_stake: float


class ArbitrageRequest(BaseModel):
    odds_over: str = Field(..., description="American odds for over (e.g. '-110')")
    odds_under: str = Field(..., description="American odds for under (e.g. '+105')")


class ArbitrageResponse(BaseModel):
    is_arbitrage: bool
    guaranteed_profit_pct: float
    implied_over: float
    implied_under: float


# -- Backtesting --


class BacktestRequest(BaseModel):
    csv_data: str = Field(..., description="Base64 or raw CSV data for backtesting")
    strategy: str = Field("value", description="Strategy name (e.g. 'value')")
    config: dict[str, Any] = Field(
        default_factory=dict, description="Optional backtest config overrides"
    )


class BacktestResponse(BaseModel):
    roi_pct: float
    sharpe: float
    n_bets: int
    win_rate: float


# -- Predictions --


class PRAPredictionRequest(BaseModel):
    player_name: str = Field(..., description="Player full name")
    game_date: str = Field(..., description="Game date YYYY-MM-DD")


class PRAPredictionResponse(BaseModel):
    projected_pra: float
    std: float
    p_over_line: float


class GamePredictionRequest(BaseModel):
    home_team: str = Field(..., description="Home team abbreviation (e.g. 'LAL')")
    away_team: str = Field(..., description="Away team abbreviation (e.g. 'BOS')")
    game_date: str = Field(..., description="Game date YYYY-MM-DD")


class GamePredictionResponse(BaseModel):
    home_proj_total: float
    away_proj_total: float
    proj_spread: float
    home_win_prob: float


# -- Ratings --


class RatingEntry(BaseModel):
    team: str
    rating: float
    rank: int


class RatingsResponse(BaseModel):
    season: str
    model: str
    ratings: list[RatingEntry]


# -- Data --


class OddsEntry(BaseModel):
    market: str
    side: str
    odds: str
    decimal: float
    implied_prob: float


class OddsResponse(BaseModel):
    sport: str
    timestamp: datetime
    odds: list[OddsEntry]


class InjuryEntry(BaseModel):
    player_name: str
    team: str
    status: str
    description: str


class InjuriesResponse(BaseModel):
    league: str
    timestamp: datetime
    injuries: list[InjuryEntry]


# -- Webhook --


class BetPlacementPayload(BaseModel):
    bet_id: str = Field(..., description="Unique bet identifier")
    event_id: str = Field(..., description="Event/game identifier")
    player_name: str = Field(..., description="Player name")
    market: str = Field(..., description="Market type (e.g. 'pra', 'points')")
    line: float = Field(..., description="Betting line")
    side: str = Field(..., description="Over or Under")
    stake: float = Field(..., gt=0, description="Stake amount")
    odds: str = Field(..., description="American odds")
    edge: float = Field(..., description="Calculated edge")


class WebhookResponse(BaseModel):
    status: str
    bet_id: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_american_odds(odds_str: str) -> Odds:
    """Parse American odds string like '-110' or '+105' into an Odds object."""
    stripped = odds_str.strip().replace("+", "")
    return Odds(american=int(stripped))


def _track(name: str, attrs: dict[str, str] | None = None):
    """Return a context manager that creates an OTEL span for *name*."""
    return tracer.start_as_current_span(name, attributes=attrs or {})


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    logger.info("SportsQuant API starting — service=%s", SERVICE_NAME)
    yield
    logger.info("SportsQuant API stopped")


app = FastAPI(
    title="SportsQuant API",
    description="Quantitative sports betting analysis REST API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="ok",
        version="0.1.0",
        timestamp=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Betting Math
# ---------------------------------------------------------------------------


@app.post("/api/v1/ev/calculate", response_model=EVResponse, tags=["betting"])
async def calculate_ev(req: EVRequest):
    """Calculate expected value and Kelly fraction for a bet."""
    start = time.perf_counter()
    with _track("api.ev.calculate", {"line": str(req.line), "odds": req.odds}):
        odds = _parse_american_odds(req.odds)
        ev = expected_value(req.probability, odds, req.probability)
        kf = kelly_fraction(req.probability, odds)
        recommendation = "over" if ev > 0 else ("under" if ev < 0 else "pass")

    _record_metrics("/api/v1/ev/calculate", 200, time.perf_counter() - start)
    return EVResponse(ev=round(ev, 6), recommendation=recommendation, kelly_fraction=round(kf, 6))


@app.post("/api/v1/kelly/calculate", response_model=KellyResponse, tags=["betting"])
async def calculate_kelly(req: KellyRequest):
    """Calculate Kelly criterion stake recommendations."""
    start = time.perf_counter()
    with _track("api.kelly.calculate", {"odds": req.odds, "fractional": str(req.fractional)}):
        odds = _parse_american_odds(req.odds)
        decimal = odds.to_decimal()
        # Edge = probability - implied; derive probability from edge + implied
        implied = odds.implied_prob()
        prob = implied + req.edge
        prob = max(0.001, min(0.999, prob))

        calc = KellyCalculator()
        full = calc.compute_kelly(prob, decimal)
        fractional_kelly = calc.compute_fractional_kelly(prob, decimal, fraction=req.fractional)

        full_stake = full * req.bankroll
        frac_stake = fractional_kelly * req.bankroll

    _record_metrics("/api/v1/kelly/calculate", 200, time.perf_counter() - start)
    return KellyResponse(
        full_kelly=round(full_stake, 2),
        fractional_kelly=round(frac_stake, 2),
        recommended_stake=round(frac_stake, 2),
    )


@app.post("/api/v1/arbitrage/detect", response_model=ArbitrageResponse, tags=["betting"])
async def detect_arbitrage(req: ArbitrageRequest):
    """Detect arbitrage opportunity between over/under odds."""
    start = time.perf_counter()
    with _track("api.arbitrage.detect", {"odds_over": req.odds_over, "odds_under": req.odds_under}):
        odds_over = _parse_american_odds(req.odds_over)
        odds_under = _parse_american_odds(req.odds_under)
        dec_over = odds_over.to_decimal()
        dec_under = odds_under.to_decimal()
        imp_over = 1.0 / dec_over
        imp_under = 1.0 / dec_under
        implied_sum = imp_over + imp_under
        is_arb = implied_sum < 1.0
        profit_pct = ((1.0 - implied_sum) / implied_sum) * 100 if is_arb else 0.0

    _record_metrics("/api/v1/arbitrage/detect", 200, time.perf_counter() - start)
    return ArbitrageResponse(
        is_arbitrage=is_arb,
        guaranteed_profit_pct=round(profit_pct, 3),
        implied_over=round(imp_over, 4),
        implied_under=round(imp_under, 4),
    )


# ---------------------------------------------------------------------------
# Backtesting
# ---------------------------------------------------------------------------


@app.post("/api/v1/backtest/run", response_model=BacktestResponse, tags=["backtest"])
async def run_backtest(req: BacktestRequest):
    """Run a backtest on provided CSV data using the specified strategy."""
    start = time.perf_counter()
    with _track("api.backtest.run", {"strategy": req.strategy}):
        try:
            import pandas as pd
            from sportsquant.core.betting.metrics import calculate_performance_metrics

            df = pd.read_csv(io.StringIO(req.csv_data))
            if df.empty:
                raise HTTPException(status_code=400, detail="CSV data is empty")

            # Simplified backtest: assume columns exist for a basic value strategy
            n_bets = len(df)
            if "result" in df.columns and "stake" in df.columns:
                results = calculate_performance_metrics(df)
                roi = results.get("roi_pct", 0.0)
                sharpe = results.get("sharpe_ratio", 0.0)
                win_rate = results.get("win_rate", 0.0)
            else:
                # Fallback: compute basic metrics from 'won' column if present
                wins = df.get("won", df.get("result", pd.Series([0] * n_bets)))
                if isinstance(wins, pd.DataFrame):
                    wins = wins.iloc[:, 0]
                win_rate = float(wins.mean()) if n_bets > 0 else 0.0
                roi = (win_rate * 0.91 - (1 - win_rate)) * 100  # assume -110 odds
                sharpe = 0.0

        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Backtest failed")
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    _record_metrics("/api/v1/backtest/run", 200, time.perf_counter() - start)
    return BacktestResponse(
        roi_pct=round(roi, 2), sharpe=round(sharpe, 2), n_bets=n_bets, win_rate=round(win_rate, 4)
    )


# ---------------------------------------------------------------------------
# Predictions
# ---------------------------------------------------------------------------


@app.post("/api/v1/predict/pra", response_model=PRAPredictionResponse, tags=["predictions"])
async def predict_pra(req: PRAPredictionRequest):
    """Predict player PRA (Points + Rebounds + Assists) for a game."""
    start = time.perf_counter()
    with _track("api.predict.pra", {"player": req.player_name, "date": req.game_date}):
        try:
            from sportsquant.models.analysis.pipeline import AnalysisPipeline, AnalysisConfig

            config = AnalysisConfig()
            AnalysisPipeline(config)
            # Pipeline typically runs full analysis; for a single player we
            # compute a simplified projection using the statistical model.
            from sportsquant.models.analysis.statistical_model import (
                StatisticalModel,
                NBADataProvider,
            )

            model = StatisticalModel(NBADataProvider())
            projection = model.project_player_stat(req.player_name, req.game_date, stat_type="pra")
            projected = float(projection.get("mean", 42.5))
            std = float(projection.get("std", 6.2))
            p_over = float(projection.get("p_over", 0.5))
        except Exception as exc:
            logger.exception("PRA prediction failed: %s", exc)
            raise HTTPException(
                status_code=501, detail=f"Prediction pipeline unavailable: {exc}"
            ) from exc

    _record_metrics("/api/v1/predict/pra", 200, time.perf_counter() - start)
    return PRAPredictionResponse(
        projected_pra=round(projected, 1), std=round(std, 1), p_over_line=round(p_over, 4)
    )


@app.post("/api/v1/predict/game", response_model=GamePredictionResponse, tags=["predictions"])
async def predict_game(req: GamePredictionRequest):
    """Predict game totals and spread for a matchup."""
    start = time.perf_counter()
    with _track("api.predict.game", {"home": req.home_team, "away": req.away_team}):
        try:
            from sportsquant.models.ratings.massey_ratings import MasseyRatings, MasseyRatingsConfig

            # Use Massey ratings for a basic game projection
            massey = MasseyRatings(MasseyRatingsConfig())
            ratings = massey.get_ratings(season="2024-25")
            home_rating = ratings.get(req.home_team, 0.0)
            away_rating = ratings.get(req.away_team, 0.0)

            home_total = 110.0 + home_rating * 2
            away_total = 110.0 + away_rating * 2
            spread = home_total - away_total
            home_win_prob = 1.0 / (1.0 + 10.0 ** (-spread / 15.0))
        except Exception as exc:
            logger.exception("Game prediction failed: %s", exc)
            raise HTTPException(
                status_code=501, detail=f"Rating models unavailable: {exc}"
            ) from exc

    _record_metrics("/api/v1/predict/game", 200, time.perf_counter() - start)
    return GamePredictionResponse(
        home_proj_total=round(home_total, 1),
        away_proj_total=round(away_total, 1),
        proj_spread=round(spread, 1),
        home_win_prob=round(home_win_prob, 4),
    )


# ---------------------------------------------------------------------------
# Ratings
# ---------------------------------------------------------------------------


@app.get("/api/v1/ratings/raptor", response_model=RatingsResponse, tags=["ratings"])
async def get_raptor_ratings(season: str = Query("2025", description="Season identifier")):
    """Get RAPTOR composite ratings for a season."""
    start = time.perf_counter()
    with _track("api.ratings.raptor", {"season": season}):
        try:
            from sportsquant.models.ratings.raptor_composite import (
                RaptorCompositeFeatures,
                RaptorCompositeConfig,
            )

            feat = RaptorCompositeFeatures(RaptorCompositeConfig())
            raw = feat.get_season_ratings(season=season)
            entries = [
                RatingEntry(team=t, rating=round(float(r), 2), rank=i + 1)
                for i, (t, r) in enumerate(sorted(raw.items(), key=lambda x: -x[1]))
            ]
        except Exception as exc:
            logger.exception("RAPTOR ratings failed: %s", exc)
            raise HTTPException(
                status_code=501, detail=f"RAPTOR ratings unavailable: {exc}"
            ) from exc

    _record_metrics("/api/v1/ratings/raptor", 200, time.perf_counter() - start)
    return RatingsResponse(season=season, model="raptor", ratings=entries)


@app.get("/api/v1/ratings/massey", response_model=RatingsResponse, tags=["ratings"])
async def get_massey_ratings(season: str = Query("2025", description="Season identifier")):
    """Get Massey ratings for a season."""
    start = time.perf_counter()
    with _track("api.ratings.massey", {"season": season}):
        try:
            from sportsquant.models.ratings.massey_ratings import MasseyRatings, MasseyRatingsConfig

            massey = MasseyRatings(MasseyRatingsConfig())
            raw = massey.get_ratings(season=season)
            entries = [
                RatingEntry(team=t, rating=round(float(r), 2), rank=i + 1)
                for i, (t, r) in enumerate(sorted(raw.items(), key=lambda x: -x[1]))
            ]
        except Exception as exc:
            logger.exception("Massey ratings failed: %s", exc)
            raise HTTPException(
                status_code=501, detail=f"Massey ratings unavailable: {exc}"
            ) from exc

    _record_metrics("/api/v1/ratings/massey", 200, time.perf_counter() - start)
    return RatingsResponse(season=season, model="massey", ratings=entries)


@app.get("/api/v1/ratings/pagerank", response_model=RatingsResponse, tags=["ratings"])
async def get_pagerank_ratings(season: str = Query("2025", description="Season identifier")):
    """Get PageRank ratings for a season."""
    start = time.perf_counter()
    with _track("api.ratings.pagerank", {"season": season}):
        try:
            from sportsquant.models.ratings.pagerank_ratings import PageRankRatings

            pr = PageRankRatings()
            raw = pr.get_ratings(season=season)
            entries = [
                RatingEntry(team=t, rating=round(float(r), 2), rank=i + 1)
                for i, (t, r) in enumerate(sorted(raw.items(), key=lambda x: -x[1]))
            ]
        except Exception as exc:
            logger.exception("PageRank ratings failed: %s", exc)
            raise HTTPException(
                status_code=501, detail=f"PageRank ratings unavailable: {exc}"
            ) from exc

    _record_metrics("/api/v1/ratings/pagerank", 200, time.perf_counter() - start)
    return RatingsResponse(season=season, model="pagerank", ratings=entries)


# ---------------------------------------------------------------------------
# Data — Odds & Injuries
# ---------------------------------------------------------------------------


@app.get("/api/v1/odds/pinnacle/{sport}", response_model=OddsResponse, tags=["data"])
async def get_pinnacle_odds(sport: str):
    """Fetch current Pinnacle odds for a sport."""
    start = time.perf_counter()
    with _track("api.odds.pinnacle", {"sport": sport}):
        try:
            from sportsquant.data.sources.pinnacle import get_odds as pinnacle_get_odds

            raw_odds = pinnacle_get_odds(sport=sport)
            entries = [
                OddsEntry(
                    market=o.get("market", "unknown"),
                    side=o.get("side", "unknown"),
                    odds=o.get("odds_american", "0"),
                    decimal=float(o.get("odds_decimal", 1.0)),
                    implied_prob=float(o.get("implied_prob", 0.5)),
                )
                for o in raw_odds
            ]
        except ImportError:
            raise HTTPException(status_code=501, detail="Pinnacle scraper not installed")
        except Exception as exc:
            logger.exception("Pinnacle odds fetch failed: %s", exc)
            raise HTTPException(status_code=502, detail=f"Upstream error: {exc}") from exc

    _record_metrics("/api/v1/odds/pinnacle", 200, time.perf_counter() - start)
    return OddsResponse(sport=sport, timestamp=datetime.now(timezone.utc), odds=entries)


@app.get("/api/v1/injuries/{league}", response_model=InjuriesResponse, tags=["data"])
async def get_injuries(league: str):
    """Fetch current injury reports for a league."""
    start = time.perf_counter()
    with _track("api.injuries", {"league": league}):
        try:
            from sportsquant.data.sources.espn_injuries import get_injuries as espn_get_injuries

            raw = espn_get_injuries(league=league)
            entries = [
                InjuryEntry(
                    player_name=i.get("player_name", "Unknown"),
                    team=i.get("team", "Unknown"),
                    status=i.get("status", "Unknown"),
                    description=i.get("description", ""),
                )
                for i in raw
            ]
        except ImportError:
            raise HTTPException(status_code=501, detail="ESPN injury scraper not installed")
        except Exception as exc:
            logger.exception("ESPN injuries fetch failed: %s", exc)
            raise HTTPException(status_code=502, detail=f"Upstream error: {exc}") from exc

    _record_metrics("/api/v1/injuries", 200, time.perf_counter() - start)
    return InjuriesResponse(league=league, timestamp=datetime.now(timezone.utc), injuries=entries)


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------


@app.post("/api/v1/webhook/bet", response_model=WebhookResponse, tags=["webhook"])
async def webhook_bet_placement(payload: BetPlacementPayload):
    """Handle bet placement webhook."""
    start = time.perf_counter()
    with _track("api.webhook.bet", {"bet_id": payload.bet_id, "event_id": payload.event_id}):
        logger.info(
            "Bet placement webhook: bet_id=%s event=%s player=%s market=%s side=%s",
            payload.bet_id,
            payload.event_id,
            payload.player_name,
            payload.market,
            payload.side,
        )

    _record_metrics("/api/v1/webhook/bet", 200, time.perf_counter() - start)
    return WebhookResponse(status="accepted", bet_id=payload.bet_id)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
