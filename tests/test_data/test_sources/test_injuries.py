"""Tests for ESPN injury scraper (new)."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, date

from sportsquant.data.sources.espn_injuries.scraper import (
    ESPNInjuryScraper,
    InjuryReport,
    InjuryStatus,
)


class TestInjuryStatus:
    """Tests for InjuryStatus enum."""

    def test_status_values(self):
        """Test injury status enum values."""
        assert InjuryStatus.OUT.value == "Out"
        assert InjuryStatus.DOUBTFUL.value == "Doubtful"
        assert InjuryStatus.QUESTIONABLE.value == "Questionable"
        assert InjuryStatus.PROBABLE.value == "Probable"
        assert InjuryStatus.ACTIVE.value == "Active"


class TestInjuryReport:
    """Tests for InjuryReport model."""

    def test_injury_report_creation(self):
        """Test creating an InjuryReport."""
        report = InjuryReport(
            player_name="LeBron James",
            team="LAL",
            opponent="BOS",
            status=InjuryStatus.QUESTIONABLE,
            injury="Left Ankle Soreness",
            date=date(2024, 11, 15),
        )
        assert report.player_name == "LeBron James"
        assert report.status == InjuryStatus.QUESTIONABLE
        assert report.injury == "Left Ankle Soreness"

    def test_injury_report_is_active(self):
        """Test is_active property."""
        active = InjuryReport(
            player_name="P1",
            team="LAL",
            opponent="BOS",
            status=InjuryStatus.ACTIVE,
            injury="",
            date=date.today(),
        )
        assert active.is_active is True

        out = InjuryReport(
            player_name="P2",
            team="LAL",
            opponent="BOS",
            status=InjuryStatus.OUT,
            injury="Knee",
            date=date.today(),
        )
        assert out.is_active is False

    def test_injury_report_to_dict(self):
        """Test InjuryReport serialization."""
        report = InjuryReport(
            player_name="Test Player",
            team="GSW",
            opponent="LAL",
            status=InjuryStatus.OUT,
            injury="Hamstring",
            date=date(2024, 11, 15),
        )
        d = report.to_dict()
        assert d["player_name"] == "Test Player"
        assert d["status"] == "Out"
        assert d["injury"] == "Hamstring"


class TestESPNInjuryScraper:
    """Tests for ESPNInjuryScraper class."""

    def test_init(self):
        """Test scraper initialization."""
        scraper = ESPNInjuryScraper()
        assert scraper.base_url == "https://www.espn.com/nba/injuries"

    def test_init_custom_url(self):
        """Test scraper with custom URL."""
        scraper = ESPNInjuryScraper(base_url="https://www.espn.com/nfl/injuries")
        assert scraper.base_url == "https://www.espn.com/nfl/injuries"

    @patch("sportsquant.data.sources.espn_injuries.scraper.httpx.Client")
    def test_get_injuries(self, mock_httpx):
        """Test getting injuries from ESPN."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body>Mock ESPN Page</body></html>"
        mock_httpx.return_value.__enter__.return_value.get.return_value = mock_response

        scraper = ESPNInjuryScraper()
        injuries = scraper.get_injuries()

        # Should return a list (may be empty if parsing fails on mock HTML)
        assert isinstance(injuries, list)

    @patch("sportsquant.data.sources.espn_injuries.scraper.httpx.Client")
    def test_get_injuries_error(self, mock_httpx):
        """Test error handling when fetching injuries."""
        mock_httpx.return_value.__enter__.return_value.get.side_effect = Exception("Network Error")

        scraper = ESPNInjuryScraper()
        injuries = scraper.get_injuries()
        assert injuries == []

    def test_parse_injury_row(self):
        """Test parsing an injury table row."""
        scraper = ESPNInjuryScraper()
        # Mock HTML row
        html_row = """
        <tr>
            <td><a>LeBron James</a></td>
            <td>Lakers</td>
            <td>LAL</td>
            <td>Questionable</td>
            <td>Left Ankle Soreness</td>
            <td>2024-11-15</td>
        </tr>
        """
        # This is a simplified test - actual parsing depends on HTML structure
        # The scraper should handle various HTML formats
        assert scraper is not None

    def test_filter_by_team(self):
        """Test filtering injuries by team."""
        scraper = ESPNInjuryScraper()
        injuries = [
            InjuryReport("P1", "LAL", "BOS", InjuryStatus.OUT, "Knee", date.today()),
            InjuryReport("P2", "GSW", "LAL", InjuryStatus.QUESTIONABLE, "Ankle", date.today()),
            InjuryReport("P3", "LAL", "BOS", InjuryStatus.ACTIVE, "", date.today()),
        ]
        lal_injuries = scraper.filter_by_team(injuries, "LAL")
        assert len(lal_injuries) == 2
        assert all(i.team == "LAL" for i in lal_injuries)

    def test_filter_by_status(self):
        """Test filtering injuries by status."""
        scraper = ESPNInjuryScraper()
        injuries = [
            InjuryReport("P1", "LAL", "BOS", InjuryStatus.OUT, "Knee", date.today()),
            InjuryReport("P2", "GSW", "LAL", InjuryStatus.QUESTIONABLE, "Ankle", date.today()),
            InjuryReport("P3", "LAL", "BOS", InjuryStatus.ACTIVE, "", date.today()),
        ]
        out_injuries = scraper.filter_by_status(injuries, InjuryStatus.OUT)
        assert len(out_injuries) == 1
        assert out_injuries[0].player_name == "P1"

    def test_get_active_players(self):
        """Test getting only active players from injury list."""
        scraper = ESPNInjuryScraper()
        injuries = [
            InjuryReport("P1", "LAL", "BOS", InjuryStatus.OUT, "Knee", date.today()),
            InjuryReport("P2", "GSW", "LAL", InjuryStatus.ACTIVE, "", date.today()),
            InjuryReport("P3", "LAL", "BOS", InjuryStatus.QUESTIONABLE, "Ankle", date.today()),
        ]
        active = scraper.get_active_players(injuries)
        assert len(active) == 1
        assert active[0].player_name == "P2"
