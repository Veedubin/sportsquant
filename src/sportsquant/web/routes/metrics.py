"""Metrics route for the SportsQuant web dashboard.

Renders a page showing TimescaleDB storage metrics and poller
throughput: table row counts, 24-hour deltas, disk sizes, and
hourly pull volume per source.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from sportsquant.infra.db.connection import get_pool
from sportsquant.infra.db.queries import (
    get_db_size,
    get_recent_poll_volume,
    get_table_stats,
    refresh_db_metrics,
)

router = APIRouter()


@router.get("/metrics", response_class=HTMLResponse)
async def metrics(request: Request) -> HTMLResponse:
    """Render the metrics page with DB storage and poller throughput."""
    pool = await get_pool()
    # Refresh the materialized view first so we have latest counts
    await refresh_db_metrics(pool)
    table_stats = await get_table_stats(pool)
    db_size = await get_db_size(pool)
    pull_volume = await get_recent_poll_volume(pool, hours=24)
    return request.app.state.templates.TemplateResponse(
        request,
        "metrics.html",
        {
            "request": request,
            "table_stats": table_stats,
            "db_size": db_size,
            "pull_volume": pull_volume,
        },
        )
