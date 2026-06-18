"""Smoke tests for the SportsQuant v0.2.0 ops dashboard web UI.

Verifies:
- App factory produces a working FastAPI instance
- All 8 user-facing routes return 200
- Poller detail and log API return valid responses (DB mocked)
- Labs detail returns 404 for non-existent notebooks
- OpenAPI docs and schema endpoints are accessible
- Static mount is present

All DB-dependent routes use a mocked asyncpg pool so no live
database is required.  Routes that only read config or static
files (settings, docs, labs, static) need no mocking.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── Helpers ──────────────────────────────────────────────────────────


@pytest.fixture
def mocked_pool() -> MagicMock:
    """Return a MagicMock that behaves like an asyncpg pool.

    All query methods (fetch, fetchrow, fetchval, execute) return
    empty/null results so routes render gracefully without a DB.
    """
    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=[])
    pool.fetchrow = AsyncMock(return_value=None)
    pool.fetchval = AsyncMock(return_value=None)
    pool.execute = AsyncMock(return_value=None)
    return pool


@pytest.fixture
def client(mocked_pool: MagicMock) -> TestClient:
    """TestClient with ``get_pool`` patched in every route module.

    Each route module does ``from ...infra.db.connection import get_pool``
    at module-import time, so patching the source module
    (``sportsquant.infra.db.connection.get_pool``) does **not** affect
    the already-imported local references.  We must patch each consumer
    module's own reference instead.
    """
    from sportsquant.web.app import create_app

    app = create_app()

    # Patch get_pool in every route module that imports it.
    # Settings, docs, and labs routes do NOT use the DB.
    patcher_home = patch(
        "sportsquant.web.routes.home.get_pool", new=AsyncMock(return_value=mocked_pool)
    )
    patcher_metrics = patch(
        "sportsquant.web.routes.metrics.get_pool", new=AsyncMock(return_value=mocked_pool)
    )
    patcher_poller = patch(
        "sportsquant.web.routes.poller.get_pool", new=AsyncMock(return_value=mocked_pool)
    )

    patcher_home.start()
    patcher_metrics.start()
    patcher_poller.start()

    yield TestClient(app)

    patcher_poller.stop()
    patcher_metrics.stop()
    patcher_home.stop()


# ── App factory ─────────────────────────────────────────────────────


def test_app_factory_succeeds() -> None:
    """``create_app()`` returns a valid FastAPI app with v0.2.0 title."""
    from sportsquant.web.app import create_app

    app = create_app()
    assert app is not None
    assert app.title == "SportsQuant Dashboard"
    assert app.version == "0.2.0"


# ── Home ────────────────────────────────────────────────────────────


def test_home_returns_200(client: TestClient) -> None:
    """``GET /`` renders the poller overview page."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "SportsQuant Pollers" in resp.text


# ── Metrics ─────────────────────────────────────────────────────────


def test_metrics_returns_200(client: TestClient) -> None:
    """``GET /metrics`` renders the DB & poller metrics page."""
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "Metrics" in resp.text


# ── Labs ────────────────────────────────────────────────────────────


def test_labs_returns_200(client: TestClient) -> None:
    """``GET /labs`` renders the labs gallery page."""
    resp = client.get("/labs")
    assert resp.status_code == 200
    assert "Labs" in resp.text


def test_labs_detail_returns_404_for_nonexistent(client: TestClient) -> None:
    """``GET /labs/{name}`` returns 404 when the HTML file does not exist."""
    resp = client.get("/labs/01_getting_started")
    assert resp.status_code == 404

    resp = client.get("/labs/99_nonexistent")
    assert resp.status_code == 404


# ── Docs ────────────────────────────────────────────────────────────


def test_docs_returns_200(client: TestClient) -> None:
    """``GET /docs`` renders the documentation page."""
    resp = client.get("/docs")
    assert resp.status_code == 200
    assert "Documentation" in resp.text


# ── Settings ────────────────────────────────────────────────────────


def test_settings_get_returns_200(client: TestClient) -> None:
    """``GET /settings`` renders the read-only config page."""
    resp = client.get("/settings")
    assert resp.status_code == 200
    assert "Settings" in resp.text


def test_settings_post_delegates_to_get(client: TestClient) -> None:
    """``POST /settings`` delegates to the GET handler (read-only)."""
    resp = client.post("/settings")
    assert resp.status_code == 200
    assert "Settings" in resp.text


# ── Poller detail ───────────────────────────────────────────────────


def test_poller_detail_returns_200(client: TestClient) -> None:
    """``GET /poller/{name}`` renders the poller detail page."""
    resp = client.get("/poller/test_poller")
    assert resp.status_code == 200
    assert "test_poller" in resp.text


def test_poller_logs_api_returns_json(client: TestClient) -> None:
    """``GET /api/poller/{name}/logs?since=N`` returns JSON with expected keys."""
    resp = client.get("/api/poller/test_poller/logs?since=0")
    assert resp.status_code == 200
    body = resp.json()
    assert "logs" in body
    assert "max_id" in body
    assert isinstance(body["logs"], list)
    assert body["max_id"] == 0  # default since when no logs exist


# ── OpenAPI / Swagger ───────────────────────────────────────────────


def test_openapi_docs_accessible(client: TestClient) -> None:
    """``GET /api/docs`` serves the Swagger UI."""
    resp = client.get("/api/docs")
    assert resp.status_code == 200


def test_openapi_json_lists_all_routes(client: TestClient) -> None:
    """``GET /openapi.json`` lists all 8 user-facing paths."""
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"].keys()

    # All 8 user-facing routes
    assert "/" in paths
    assert "/poller/{name}" in paths
    assert "/api/poller/{name}/logs" in paths
    assert "/metrics" in paths
    assert "/labs" in paths
    assert "/labs/{name}" in paths
    assert "/docs" in paths
    assert "/settings" in paths


# ── Static files ────────────────────────────────────────────────────


def test_static_css_accessible(client: TestClient) -> None:
    """``GET /static/css/style.css`` returns the compiled stylesheet."""
    resp = client.get("/static/css/style.css")
    assert resp.status_code == 200
