"""ESPN injuries poller source for SportsQuant v0.2.0.

Provides an async HTTP fetcher and normalizing parser that turns raw ESPN
injuries JSON responses into flat ``injuries``-compatible row dicts ready for
the DB writer.  The poller calls :func:`fetch_and_parse` on a configurable
cadence (default: 15 minutes) and hands the result off to the persistence
layer.

ESPN's public injuries endpoint requires no authentication and is the legal
way to obtain injury data — no scraping of consumer sportsbook sites is
involved.

Configuration is via :class:`ESPNInjuriesConfig`, which reads from environment
variables with both a generic prefix (``ESPN_``) and a project-scoped prefix
(``SPORTSQUANT_POLLER_ESPN_``) so that the poller can be tuned independently
of any other ESPN consumers.

This module intentionally does **not** own retry logic or DB writes — those
concerns belong to the poller orchestrator and ``infra.db.writers``,
respectively.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic_settings import BaseSettings

from sportsquant.util.time_utils import utc_now_iso

logger = logging.getLogger(__name__)

__all__ = [
    "ESPNInjuriesConfig",
    "ESPNInjuriesError",
    "SPORT_ENDPOINTS",
    "fetch_espn_injuries",
    "parse_espn_injuries_to_rows",
    "fetch_and_parse",
]


# ──────────────────────────────────────────────
# Sport Endpoints
# ──────────────────────────────────────────────

SPORT_ENDPOINTS: dict[str, str] = {
    "nfl": "football/nfl",
    "nba": "basketball/nba",
    "mlb": "baseball/mlb",
    "nhl": "hockey/nhl",
}


# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────


class ESPNInjuriesConfig(BaseSettings):
    """Configuration for the ESPN injuries poller source.

    Values are sourced from environment variables.  Both the ``ESPN_``
    prefix and the ``SPORTSQUANT_POLLER_ESPN_`` prefix are accepted
    (the latter takes precedence when set) so that the poller can be
    configured independently of other ESPN consumers.

    Attributes:
        base_url: Base URL for the ESPN site API v2 endpoint.
        interval_seconds: Seconds between poller fetch cycles (default 900 = 15 min).
        request_timeout: HTTP request timeout in seconds.
        user_agent: User-Agent header sent with requests.
    """

    base_url: str = "https://site.api.espn.com/apis/site/v2/sports"
    interval_seconds: int = 900
    request_timeout: int = 30
    user_agent: str = "sportsquant/0.2.0"

    model_config = {  # type: ignore[typed-dict-unknown]
        "env_prefix": "SPORTSQUANT_POLLER_ESPN_",
        "env_aliases": {
            "base_url": "ESPN_BASE_URL",
            "interval_seconds": "ESPN_INJURIES_INTERVAL_SECONDS",
            "request_timeout": "ESPN_TIMEOUT",
            "user_agent": "ESPN_USER_AGENT",
        },
    }


# ──────────────────────────────────────────────
# Exception
# ──────────────────────────────────────────────


class ESPNInjuriesError(Exception):
    """Raised when the ESPN injuries API returns a non-success response.

    Attributes:
        status_code: The HTTP status code received.
        body: An excerpt of the response body (truncated for safety).
    """

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"ESPN injuries API error {status_code}: {body[:200]}")


# ──────────────────────────────────────────────
# Async Fetcher
# ──────────────────────────────────────────────


async def fetch_espn_injuries(
    sport: str,
    config: ESPNInjuriesConfig,
) -> dict[str, Any]:
    """Fetch raw injuries data from the ESPN site API.

    Performs an asynchronous GET to
    ``{base_url}/{sport_path}/injuries`` with the configured timeout
    and User-Agent header, and returns the parsed JSON dict.

    Args:
        sport: Sport slug — one of ``"nfl"``, ``"nba"``, ``"mlb"``, ``"nhl"``.
        config: Fully populated :class:`ESPNInjuriesConfig`.

    Returns:
        The raw JSON dict as returned by the ESPN injuries API.

    Raises:
        ValueError: If *sport* is not in :data:`SPORT_ENDPOINTS`.
        ESPNInjuriesError: On any non-200 HTTP response.
        ImportError: If ``httpx`` is not installed.
    """
    if sport not in SPORT_ENDPOINTS:
        raise ValueError(
            f"Unsupported sport {sport!r}. Must be one of: {', '.join(sorted(SPORT_ENDPOINTS))}"
        )

    import httpx  # noqa: F811 — lazy import so module loads without httpx

    sport_path = SPORT_ENDPOINTS[sport]
    url = f"{config.base_url}/{sport_path}/injuries"
    headers = {"User-Agent": config.user_agent}

    logger.info("ESPN injuries request: GET %s (sport=%s)", url, sport)

    async with httpx.AsyncClient(timeout=config.request_timeout) as client:
        response = await client.get(url, headers=headers)

    if response.status_code != 200:
        body_excerpt = response.text[:500]
        logger.error(
            "ESPN injuries API error: status=%d body=%.200s",
            response.status_code,
            body_excerpt,
        )
        raise ESPNInjuriesError(status_code=response.status_code, body=body_excerpt)

    data: dict[str, Any] = response.json()
    logger.info("ESPN injuries response: sport=%s", sport)
    return data


# ──────────────────────────────────────────────
# Parser
# ──────────────────────────────────────────────


def parse_espn_injuries_to_rows(
    data: dict[str, Any],
    sport: str,
) -> list[dict[str, Any]]:
    """Normalize raw ESPN injuries JSON into flat ``injuries`` rows.

    Walks each team entry in ``data["injuries"]``, then each player injury
    record, and emits one row per *(team, player, injury)* combination.
    Rows with a missing ``player_name`` are silently skipped.

    Args:
        data: Raw JSON dict as returned by :func:`fetch_espn_injuries`.
        sport: Sport slug (e.g. ``"nfl"``), used as the ``sport`` column.

    Returns:
        A list of dicts, each with keys: ``sport``, ``player_id``,
        ``player_name``, ``team``, ``position``, ``status``, ``detail``,
        ``ts``, ``source_raw``.
    """
    rows: list[dict[str, Any]] = []

    for team_entry in data.get("injuries") or []:
        if not isinstance(team_entry, dict):
            continue

        team_info = team_entry.get("team") or {}
        team_id = team_info.get("id", "")
        team_abbr = team_info.get("abbreviation") or team_info.get("id", "Unknown")

        for injury in team_entry.get("injuries") or []:
            if not isinstance(injury, dict):
                continue

            # Extract player / athlete info
            athlete = injury.get("athlete") or {}
            if isinstance(athlete, dict):
                player_id = (
                    str(athlete["id"])
                    if "id" in athlete
                    else f"{athlete.get('name', 'unknown')}_{team_id}"
                )
                player_name = (
                    athlete.get("displayName") or athlete.get("fullName") or athlete.get("name")
                )
                position_raw = athlete.get("position")
                if isinstance(position_raw, dict):
                    position = position_raw.get("abbreviation")
                else:
                    position = position_raw
            else:
                # Fallback: treat injury dict itself as the player source
                player_id = str(injury.get("id", f"unknown_{team_id}"))
                player_name = (
                    injury.get("displayName") or injury.get("fullName") or injury.get("name")
                )
                position = None

            # Skip rows with no player name — we need at least a name
            if not player_name:
                continue

            # Status
            status = injury.get("status", "Unknown")

            # Detail / description
            details = injury.get("details")
            if isinstance(details, dict):
                detail = details.get("detail")
            else:
                detail = None
            if not detail:
                detail = injury.get("longComment") or injury.get("shortComment")

            rows.append(
                {
                    "sport": sport,
                    "player_id": player_id,
                    "player_name": player_name,
                    "team": team_abbr,
                    "position": position,
                    "status": status,
                    "detail": detail,
                    "ts": utc_now_iso(),
                    "source_raw": json.dumps(injury),
                }
            )

    logger.info("Parsed %d injury rows for sport=%s", len(rows), sport)
    return rows


# ──────────────────────────────────────────────
# Convenience Wrapper
# ──────────────────────────────────────────────


async def fetch_and_parse(
    sport: str,
    config: ESPNInjuriesConfig,
) -> list[dict[str, Any]]:
    """Fetch injuries from the ESPN API and parse them into row dicts.

    This is the main entry point for the poller.  It calls
    :func:`fetch_espn_injuries` and then :func:`parse_espn_injuries_to_rows`,
    returning the normalized list ready for the DB writer.

    Args:
        sport: Sport slug — one of ``"nfl"``, ``"nba"``, ``"mlb"``, ``"nhl"``.
        config: Fully populated :class:`ESPNInjuriesConfig`.

    Returns:
        A list of ``injuries``-compatible row dicts.

    Raises:
        ValueError: If *sport* is not in :data:`SPORT_ENDPOINTS`.
        ESPNInjuriesError: On any non-200 ESPN API response.
        ImportError: If ``httpx`` is not installed.
    """
    data = await fetch_espn_injuries(sport, config)
    return parse_espn_injuries_to_rows(data, sport)
