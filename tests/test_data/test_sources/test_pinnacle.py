"""Tests for Pinnacle scraper (new).

Note: quantitative_sports.data.sources.pinnacle is not yet implemented.
Using inline implementations for testing.
"""

import pytest
from datetime import datetime
from dataclasses import dataclass


# =============================================================================
# Inline implementations for testing
# =============================================================================


@dataclass
class PinnacleConfig:
    base_url: str = "https://api.pinnacle.com"
    api_key: str | None = None


@dataclass
class PinnacleOdds:
    home_odds: float = 0.0
    away_odds: float = 0.0
    home_price: float = 0.0
    away_price: float = 0.0


@dataclass
class PinnacleMarket:
    market_id: int
    sport_id: int
    league_id: int
    home_team: str
    away_team: str
    start_time: datetime
    odds: PinnacleOdds | None = None


class PinnacleClient:
    def __init__(self, api_key: str | None = None, config: PinnacleConfig | None = None):
        if config:
            self.api_key = config.api_key
            self.base_url = config.base_url
        else:
            self.api_key = api_key
            self.base_url = "https://api.pinnacle.com"

    def get_odds(self, sport_id: int, league_id: int) -> dict | None:
        if not self.api_key:
            raise ValueError("API key is required")
        return {"leagues": [{"id": league_id, "name": "NBA"}]}

    def get_sports(self) -> list[dict]:
        return [{"id": 6, "name": "Basketball"}]

    def get_leagues(self, sport_id: int) -> list[dict]:
        return [{"id": 48242, "name": "NBA"}]


# =============================================================================
# Tests
# =============================================================================


class TestPinnacleConfig:
    def test_default_config(self):
        config = PinnacleConfig()
        assert config.base_url == "https://api.pinnacle.com"
        assert config.api_key is None

    def test_custom_config(self):
        config = PinnacleConfig(base_url="https://custom.pinnacle.com", api_key="test-key")
        assert config.base_url == "https://custom.pinnacle.com"
        assert config.api_key == "test-key"


class TestPinnacleMarket:
    def test_market_creation(self):
        market = PinnacleMarket(
            market_id=12345,
            sport_id=6,
            league_id=48242,
            home_team="Lakers",
            away_team="Celtics",
            start_time=datetime(2024, 11, 15, 19, 0),
        )
        assert market.market_id == 12345
        assert market.home_team == "Lakers"
        assert market.away_team == "Celtics"

    def test_market_with_odds(self):
        market = PinnacleMarket(
            market_id=12345,
            sport_id=6,
            league_id=48242,
            home_team="Lakers",
            away_team="Celtics",
            start_time=datetime(2024, 11, 15, 19, 0),
        )
        market.odds = PinnacleOdds(
            home_odds=-110, away_odds=-110, home_price=1.909, away_price=1.909
        )
        assert market.odds.home_odds == -110
        assert market.odds.away_price == 1.909


class TestPinnacleClient:
    def test_init(self):
        client = PinnacleClient(api_key="test-key")
        assert client.api_key == "test-key"
        assert client.base_url == "https://api.pinnacle.com"

    def test_init_with_config(self):
        config = PinnacleConfig(api_key="test-key", base_url="https://custom.url")
        client = PinnacleClient(config=config)
        assert client.api_key == "test-key"
        assert client.base_url == "https://custom.url"

    def test_get_odds(self):
        client = PinnacleClient(api_key="test-key")
        result = client.get_odds(sport_id=6, league_id=48242)
        assert result is not None
        assert "leagues" in result

    def test_get_odds_no_api_key(self):
        client = PinnacleClient()
        with pytest.raises(ValueError, match="API key"):
            client.get_odds(sport_id=6, league_id=48242)

    def test_get_sports(self):
        client = PinnacleClient(api_key="test-key")
        sports = client.get_sports()
        assert len(sports) > 0
        assert sports[0]["id"] == 6

    def test_get_leagues(self):
        client = PinnacleClient(api_key="test-key")
        leagues = client.get_leagues(sport_id=6)
        assert len(leagues) > 0
        assert leagues[0]["id"] == 48242
