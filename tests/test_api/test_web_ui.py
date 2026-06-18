"""Smoke tests for the SportsQuant web UI.

Verifies:
- App factory produces a working FastAPI instance
- All 5 GET routes return 200
- All 2 POST routes return 200
- Dashboard template renders with current stats
- NFL prediction page renders with form
- OpenAPI docs endpoint is accessible

Uses Starlette TestClient (no live network required).
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from sportsquant.web.app import app

    return TestClient(app)


def test_app_factory_succeeds() -> None:
    from sportsquant.web.app import app

    assert app is not None
    assert app.title == "SportsQuant Dashboard"


def test_dashboard_route_returns_200() -> None:
    client = _client()
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.text
    assert "SportsQuant Dashboard" in body
    assert "762" in body  # current test count


def test_dashboard_lists_nfl_modules() -> None:
    client = _client()
    body = client.get("/").text
    assert "NFL Modules" in body
    assert "NFL Game Predictor (XGBoost ensemble)" in body
    assert "Multi-book Odds Aggregator" in body
    assert "Middling Detection" in body


def test_ev_route_returns_200() -> None:
    client = _client()
    resp = client.get("/ev/")
    assert resp.status_code == 200
    assert "EV Calculator" in resp.text


def test_backtest_route_returns_200() -> None:
    client = _client()
    resp = client.get("/backtest/")
    assert resp.status_code == 200
    assert "Backtest" in resp.text


def test_ratings_route_returns_200() -> None:
    client = _client()
    resp = client.get("/ratings/")
    assert resp.status_code == 200
    assert "Power Ratings" in resp.text


def test_nfl_predict_get_returns_form() -> None:
    client = _client()
    resp = client.get("/nfl-predict/")
    assert resp.status_code == 200
    body = resp.text
    assert "NFL Game Predictor" in body
    assert 'name="home"' in body
    assert 'name="away"' in body
    assert "Predict Outcome" in body


def test_nfl_predict_post_renders_prediction() -> None:
    client = _client()
    resp = client.post(
        "/nfl-predict/",
        data={
            "home": "KC",
            "away": "BAL",
            "season": 2024,
            "week": 10,
            "home_ppg_for": 28.0,
            "home_ppg_against": 20.0,
            "home_yards_per_play": 5.8,
            "home_turnover_rate": 1.2,
            "home_qb_rating": 100.0,
            "away_ppg_for": 20.0,
            "away_ppg_against": 24.0,
            "away_yards_per_play": 5.0,
            "away_turnover_rate": 1.6,
            "away_qb_rating": 85.0,
            "rest_advantage": 0.0,
            "model_path": "",
        },
    )
    assert resp.status_code == 200
    body = resp.text
    assert "KC" in body
    assert "BAL" in body
    # Prediction output should mention percentages
    assert "%" in body
    # Should show feature importances section
    assert "feature importances" in body.lower()


def test_ev_post_handles_calculation() -> None:
    client = _client()
    resp = client.post(
        "/ev/",
        data={
            "line": 47.5,
            "odds": -110,
            "prob": 0.55,
        },
    )
    assert resp.status_code == 200
    assert "EV Calculator" in resp.text


def test_openapi_docs_accessible() -> None:
    client = _client()
    resp = client.get("/api/docs")
    assert resp.status_code == 200


def test_openapi_json_lists_routes() -> None:
    client = _client()
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"].keys()
    # All 5 user-facing pages registered
    assert "/" in paths
    assert "/ev/" in paths
    assert "/backtest/" in paths
    assert "/ratings/" in paths
    assert "/nfl-predict/" in paths


def test_static_css_accessible() -> None:
    client = _client()
    # Static mount should be present
    resp = client.get("/static/css/style.css")
    assert resp.status_code == 200
