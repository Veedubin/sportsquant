"""Poller configuration model for SportsQuant v0.2.0.

Provides :class:`PollerConfig`, a ``pydantic-settings`` model that aggregates
all poller subsystem configurations into a single top-level object read on
startup.  Individual source configs (Odds API, ESPN injuries) are nested as
sub-models so that each source keeps its own ``env_prefix`` and validation
rules while remaining accessible through the parent config.

Environment variables use the ``SPORTSQUANT_POLLER_`` prefix.  Nested configs
retain their own prefixes (e.g. ``SPORTSQUANT_POLLER_ODDS_API_``) and are
resolved independently by ``pydantic-settings``.

Defaults are chosen so that ``PollerConfig()`` works out of the box for local
development — only ``odds_api.api_key`` needs to be set to enable the Odds API
source.

Helper functions:
    - :func:`get_active_sports` — split the comma-separated ``active_sports``
      field into a clean list.
    - :func:`is_odds_api_enabled` — check whether the Odds API source is
      configured (non-empty API key).
    - :func:`is_espn_enabled` — check whether the ESPN source is enabled
      (always True for now; a kill-switch field may be added later).
"""

from __future__ import annotations

import logging

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from sportsquant.infra.db.connection import DBConfig
from sportsquant.infra.poller.sources.espn_injuries import ESPNInjuriesConfig
from sportsquant.infra.poller.sources.odds_api import OddsAPIConfig

logger = logging.getLogger(__name__)

__all__ = [
    "PollerConfig",
    "get_active_sports",
    "is_odds_api_enabled",
    "is_espn_enabled",
]

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

KNOWN_SPORTS: frozenset[str] = frozenset({"nfl", "nba", "mlb", "nhl"})
"""Sports that the poller recognises.  Used by the ``active_sports`` validator."""


# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────


class PollerConfig(BaseSettings):
    """Top-level poller configuration.

    Aggregates database, Odds API, and ESPN injuries sub-configs alongside
    scheduler selection, sport filtering, and retry behaviour.

    Values are sourced from environment variables with the
    ``SPORTSQUANT_POLLER_`` prefix.  Nested sub-configs retain their own
    prefixes (e.g. ``SPORTSQUANT_POLLER_ODDS_API_``) and are resolved
    independently by ``pydantic-settings``.

    Attributes:
        scheduler: Orchestrator backend — ``"prefect"`` or ``"cron"``.
        active_sports: Comma-separated list of sports to poll (e.g. ``"nfl,nba"``).
        db: TimescaleDB connection config.
        odds_api: Odds API source config.
        espn: ESPN injuries source config.
        prefect_api_url: URL of the Prefect server API.
        log_level: Python logging level (e.g. ``"INFO"``, ``"DEBUG"``).
        max_retries: Maximum retry attempts per poll cycle.
        retry_delay: Seconds to wait between retries.
    """

    scheduler: str = "prefect"
    active_sports: str = "nfl,nba"
    db: DBConfig = DBConfig()
    odds_api: OddsAPIConfig = OddsAPIConfig()
    espn: ESPNInjuriesConfig = ESPNInjuriesConfig()
    prefect_api_url: str = "http://localhost:4200/api"
    log_level: str = "INFO"
    max_retries: int = 3
    retry_delay: int = 30

    model_config = SettingsConfigDict(  # type: ignore[typed-dict-unknown]
        env_prefix="SPORTSQUANT_POLLER_",
    )

    @field_validator("scheduler")
    @classmethod
    def _validate_scheduler(cls, v: str) -> str:
        """Ensure the scheduler is one of the supported backends."""
        allowed = {"prefect", "cron"}
        if v not in allowed:
            raise ValueError(
                f"Unsupported scheduler {v!r}. Must be one of: {', '.join(sorted(allowed))}"
            )
        return v

    @field_validator("active_sports")
    @classmethod
    def _validate_active_sports(cls, v: str) -> str:
        """Ensure every sport in the comma-separated list is recognised."""
        sports = [s.strip() for s in v.split(",") if s.strip()]
        unknown = [s for s in sports if s not in KNOWN_SPORTS]
        if unknown:
            raise ValueError(
                f"Unknown sport(s): {', '.join(unknown)}. "
                f"Known sports: {', '.join(sorted(KNOWN_SPORTS))}"
            )
        return v


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def get_active_sports(config: PollerConfig) -> list[str]:
    """Split the comma-separated ``active_sports`` field into a clean list.

    Strips whitespace and drops empty entries so that
    ``"nfl, nba,""`` normalises to ``["nfl", "nba"]``.

    Args:
        config: A fully populated :class:`PollerConfig` instance.

    Returns:
        A list of sport slugs (e.g. ``["nfl", "nba"]``).
    """
    return [s.strip() for s in config.active_sports.split(",") if s.strip()]


def is_odds_api_enabled(config: PollerConfig) -> bool:
    """Check whether the Odds API source is configured.

    The Odds API requires a non-empty ``api_key`` to function.  When the key
    is empty (the default), the source is considered disabled.

    Args:
        config: A fully populated :class:`PollerConfig` instance.

    Returns:
        ``True`` if ``config.odds_api.api_key`` is non-empty, ``False``
        otherwise.
    """
    return bool(config.odds_api.api_key)


def is_espn_enabled(config: PollerConfig) -> bool:
    """Check whether the ESPN injuries source is enabled.

    ESPN's public injuries endpoint requires no authentication, so the source
    is always enabled.  A kill-switch field may be added in a future release.

    Args:
        config: A fully populated :class:`PollerConfig` instance.

    Returns:
        Always ``True`` (for now).
    """
    return True
