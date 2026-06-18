"""Odds API poller source for SportsQuant v0.2.0.

Provides an async HTTP fetcher and normalizing parser that turns raw Odds API
JSON responses into flat ``odds_ticks``-compatible row dicts ready for the DB
writer.  The poller calls :func:`fetch_and_parse` on a configurable cadence
(default: daily) and hands the result off to the persistence layer.

Configuration is via :class:`OddsAPIConfig`, which reads from environment
variables with both a generic prefix (``ODDS_API_``) and a project-scoped
prefix (``SPORTSQUANT_POLLER_ODDS_API_``) so that the poller can be tuned
independently of any other Odds API consumers.

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
    "OddsAPIConfig",
    "OddsAPIError",
    "fetch_odds_api_events",
    "parse_odds_api_to_ticks",
    "fetch_and_parse",
]


# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────


class OddsAPIConfig(BaseSettings):
    """Configuration for the Odds API poller source.

    Values are sourced from environment variables.  Both the ``ODDS_API_``
    prefix and the ``SPORTSQUANT_POLLER_ODDS_API_`` prefix are accepted
    (the latter takes precedence when set) so that the poller can be
    configured independently of other Odds API consumers.

    Attributes:
        api_key: The Odds API key (required for live requests).
        base_url: Base URL for the Odds API v4 endpoint.
        regions: Comma-separated region filter (e.g. ``"us"``).
        markets: Comma-separated market types to fetch.
        odds_format: Odds format — ``"american"`` or ``"decimal"``.
        bookmakers: Comma-separated bookmaker keys; empty means all.
        interval_seconds: Seconds between poller fetch cycles (default 86400 = daily).
        request_timeout: HTTP request timeout in seconds.
    """

    api_key: str = ""
    base_url: str = "https://api.the-odds-api.com/v4"
    regions: str = "us"
    markets: str = "h2h,spreads,totals"
    odds_format: str = "american"
    bookmakers: str = ""
    interval_seconds: int = 86400
    request_timeout: int = 30

    model_config = {  # type: ignore[typed-dict-unknown]
        "env_prefix": "SPORTSQUANT_POLLER_ODDS_API_",
        "env_aliases": {
            "api_key": "ODDS_API_KEY",
            "base_url": "ODDS_API_BASE_URL",
            "regions": "ODDS_API_REGIONS",
            "markets": "ODDS_API_MARKETS",
            "odds_format": "ODDS_API_ODDS_FORMAT",
            "bookmakers": "ODDS_API_BOOKMAKERS",
            "interval_seconds": "ODDS_API_INTERVAL_SECONDS",
            "request_timeout": "ODDS_API_TIMEOUT",
        },
    }


# ──────────────────────────────────────────────
# Exception
# ──────────────────────────────────────────────


class OddsAPIError(Exception):
    """Raised when the Odds API returns a non-success response.

    Attributes:
        status_code: The HTTP status code received.
        body: An excerpt of the response body (truncated for safety).
    """

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"Odds API error {status_code}: {body[:200]}")


# ──────────────────────────────────────────────
# Async Fetcher
# ──────────────────────────────────────────────


async def fetch_odds_api_events(
    sport: str,
    config: OddsAPIConfig,
) -> list[dict[str, Any]]:
    """Fetch raw odds events from The Odds API.

    Performs an asynchronous GET to
    ``{base_url}/sports/{sport}/odds/`` with the configured query parameters
    and returns the parsed JSON list of event dicts.

    Args:
        sport: Odds API sport key (e.g. ``"americanfootball_nfl"``).
        config: Fully populated :class:`OddsAPIConfig`.

    Returns:
        A list of raw event dicts as returned by the Odds API.

    Raises:
        OddsAPIError: On any non-200 HTTP response.
        ImportError: If ``httpx`` is not installed.
    """
    import httpx  # noqa: F811 — lazy import so module loads without httpx

    url = f"{config.base_url}/sports/{sport}/odds/"
    params: dict[str, str] = {
        "apiKey": config.api_key,
        "regions": config.regions,
        "markets": config.markets,
        "oddsFormat": config.odds_format,
    }
    if config.bookmakers:
        params["bookmakers"] = config.bookmakers

    logger.info("Odds API request: GET %s (sport=%s)", url, sport)

    async with httpx.AsyncClient(timeout=config.request_timeout) as client:
        response = await client.get(url, params=params)

    if response.status_code != 200:
        body_excerpt = response.text[:500]
        logger.error(
            "Odds API error: status=%d body=%.200s",
            response.status_code,
            body_excerpt,
        )
        raise OddsAPIError(status_code=response.status_code, body=body_excerpt)

    events: list[dict[str, Any]] = response.json()
    logger.info("Odds API response: %d events for sport=%s", len(events), sport)
    return events


# ──────────────────────────────────────────────
# Parser
# ──────────────────────────────────────────────


def parse_odds_api_to_ticks(
    events: list[dict[str, Any]],
    sport: str,
) -> list[dict[str, Any]]:
    """Normalize raw Odds API events into flat ``odds_ticks`` rows.

    Walks each event's ``bookmakers → markets → outcomes`` hierarchy and
    emits one row per *(event, bookmaker, market, outcome)* combination.
    Rows with missing critical fields (event_id, book, market, selection,
    price) are silently skipped.

    Args:
        events: Raw event list as returned by :func:`fetch_odds_api_events`.
        sport: The Odds API sport key (used as the ``sport`` and ``league``
            columns in each row).

    Returns:
        A list of dicts, each with keys: ``sport``, ``league``, ``event_id``,
        ``book``, ``market``, ``selection``, ``price``, ``line``, ``ts``,
        ``source_raw``.
    """
    ticks: list[dict[str, Any]] = []

    for event in events:
        if not isinstance(event, dict):
            continue

        event_id = event.get("id")
        if not event_id:
            continue

        for bookmaker in event.get("bookmakers") or []:
            if not isinstance(bookmaker, dict):
                continue
            book = bookmaker.get("key")
            if not book:
                continue

            for market in bookmaker.get("markets") or []:
                if not isinstance(market, dict):
                    continue
                market_key = market.get("key")
                if not market_key:
                    continue

                for outcome in market.get("outcomes") or []:
                    if not isinstance(outcome, dict):
                        continue

                    selection = outcome.get("name")
                    price = outcome.get("price")

                    # Skip rows missing critical fields
                    if not selection or price is None:
                        continue

                    ticks.append(
                        {
                            "sport": sport,
                            "league": sport.upper(),
                            "event_id": event_id,
                            "book": book,
                            "market": market_key,
                            "selection": selection,
                            "price": int(outcome["price"]),
                            "line": outcome.get("point"),
                            "ts": utc_now_iso(),
                            "source_raw": json.dumps(outcome),
                        }
                    )

    logger.info("Parsed %d odds_ticks rows from %d events", len(ticks), len(events))
    return ticks


# ──────────────────────────────────────────────
# Convenience Wrapper
# ──────────────────────────────────────────────


async def fetch_and_parse(
    sport: str,
    config: OddsAPIConfig,
) -> list[dict[str, Any]]:
    """Fetch odds from the Odds API and parse them into tick rows.

    This is the main entry point for the poller.  It calls
    :func:`fetch_odds_api_events` and then :func:`parse_odds_api_to_ticks`,
    returning the normalized list ready for the DB writer.

    Args:
        sport: Odds API sport key (e.g. ``"americanfootball_nfl"``).
        config: Fully populated :class:`OddsAPIConfig`.

    Returns:
        A list of ``odds_ticks``-compatible row dicts.

    Raises:
        OddsAPIError: On any non-200 Odds API response.
        ImportError: If ``httpx`` is not installed.
    """
    events = await fetch_odds_api_events(sport, config)
    return parse_odds_api_to_ticks(events, sport)
