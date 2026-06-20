"""Poller detail route for the Quant-Sports ops dashboard.

Renders a drill-down view for a single poller showing run history,
success-rate stats, and a live log tail with JS refresh.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from quantitative_sports.infra.db.connection import get_pool
from quantitative_sports.infra.db.queries import get_poller_logs, get_poller_runs, get_poller_success_rates

router = APIRouter()


@router.get("/poller/{name}", response_class=HTMLResponse)
async def poller_detail(request: Request, name: str) -> HTMLResponse:
    """Render the poller detail page with runs, stats, and logs."""
    pool = await get_pool()
    runs = await get_poller_runs(pool, name, limit=50)
    rates = await get_poller_success_rates(pool, hours=24 * 7)
    logs = await get_poller_logs(pool, name, limit=100)

    # Find the rate record for this specific poller
    rate = next((r for r in rates if r["poller_name"] == name), {})

    return request.app.state.templates.TemplateResponse(
        request,
        "poller.html",
        {
            "request": request,
            "poller_name": name,
            "runs": runs,
            "rate": rate,
            "logs": logs,
            "page_title": name,
        },
    )


@router.get("/api/poller/{name}/logs")
async def poller_logs_api(name: str, since: int = 0) -> JSONResponse:
    """Return new log lines for a poller since the given ID.

    Used by the JS refresh button on the poller detail page to
    fetch incremental log lines without a full page reload.
    """
    pool = await get_pool()
    logs = await get_poller_logs(pool, name, limit=100, since_id=since)
    max_id = max((log["id"] for log in logs), default=since)
    return JSONResponse({"logs": logs, "max_id": max_id})
