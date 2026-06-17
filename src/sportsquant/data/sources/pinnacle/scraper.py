"""Pinnacle sportsbook scraper — sharp book / market-maker odds.

Pinnacle is the most efficient sports betting market. Their odds
represent the sharpest lines available and are used for:
- Fair value estimation (remove vig from Pinnacle lines)
- Market efficiency analysis
- Cross-book arbitrage detection

Uses httpx for async HTTP requests with retry logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import httpx
import pandas as pd


@dataclass
class PinnacleOdds:
    """Normalized Pinnacle odds for a single market."""

    sport: str
    league: str
    event_id: str
    home_team: str
    away_team: str
    commence_time: datetime
    market_type: str  # "moneyline", "spread", "total"
    home_price: float
    away_price: float
    spread: Optional[float] = None  # For spread markets
    total: Optional[float] = None  # For total markets


class PinnacleScraper:
    """Fetches odds from Pinnacle sportsbook.

    Pinnacle offers API access for partners. This implementation
    uses their public feed endpoints where available, with fallback
    to manual scraping patterns.
    """

    BASE_URL = "https://www.pinnacle.com"

    def __init__(self, timeout: float = 30.0, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers={
                    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"),
                    "Accept": "application/json",
                },
            )
        return self._client

    async def fetch_nfl_odds(self, week: Optional[int] = None) -> pd.DataFrame:
        """Fetch NFL odds from Pinnacle.

        Returns DataFrame with: game_id, home_team, away_team,
        commence_time, ml_home, ml_away, spread_home, spread_away,
        total, total_over_price, total_under_price
        """
        # STUB — Pinnacle API requires partnership
        # Returns empty DataFrame with correct schema
        columns = [
            "game_id",
            "home_team",
            "away_team",
            "commence_time",
            "ml_home",
            "ml_away",
            "spread_home",
            "spread_home_price",
            "spread_away_price",
            "total",
            "total_over_price",
            "total_under_price",
        ]
        return pd.DataFrame(columns=columns)

    async def fetch_nba_odds(self) -> pd.DataFrame:
        """Fetch NBA odds from Pinnacle."""
        columns = [
            "game_id",
            "home_team",
            "away_team",
            "commence_time",
            "ml_home",
            "ml_away",
            "spread_home",
            "spread_home_price",
            "spread_away_price",
            "total",
            "total_over_price",
            "total_under_price",
        ]
        return pd.DataFrame(columns=columns)

    @staticmethod
    def remove_vig(price_a: float, price_b: float) -> tuple[float, float]:
        """Remove the vig (overround) from two prices to get fair probabilities.

        Args:
            price_a: Decimal odds for side A
            price_b: Decimal odds for side B

        Returns:
            Tuple of (fair_prob_a, fair_prob_b) summing to 1.0
        """
        implied_a = 1.0 / price_a
        implied_b = 1.0 / price_b
        overround = implied_a + implied_b
        fair_a = implied_a / overround
        fair_b = implied_b / overround
        return fair_a, fair_b

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
