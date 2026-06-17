"""ESPN injury scraper — fetches injury reports from ESPN.

Supports both web scraping of ESPN injury pages and the ESPN public API.
Uses httpx for HTTP requests with proper error handling.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import Enum

import httpx


class InjuryStatus(Enum):
    """Injury status enum."""

    OUT = "Out"
    DOUBTFUL = "Doubtful"
    QUESTIONABLE = "Questionable"
    PROBABLE = "Probable"
    ACTIVE = "Active"


@dataclass
class InjuryReport:
    """Injury report model."""

    player_name: str
    team: str
    opponent: str
    status: InjuryStatus
    injury: str
    date: date
    position: str = ""

    @property
    def is_active(self) -> bool:
        return self.status == InjuryStatus.ACTIVE

    def to_dict(self) -> dict:
        return {
            "player_name": self.player_name,
            "team": self.team,
            "opponent": self.opponent,
            "status": self.status.value,
            "injury": self.injury,
            "date": str(self.date),
        }


# Map common status strings to InjuryStatus enum
_STATUS_MAP: dict[str, InjuryStatus] = {
    "out": InjuryStatus.OUT,
    "doubtful": InjuryStatus.DOUBTFUL,
    "questionable": InjuryStatus.QUESTIONABLE,
    "probable": InjuryStatus.PROBABLE,
    "active": InjuryStatus.ACTIVE,
}


class ESPNInjuryScraper:
    """Scrapes injury reports from ESPN.

    Uses the ESPN public API endpoint for structured data,
    with fallback to HTML scraping of injury pages.
    """

    DEFAULT_URL = "https://www.espn.com/nba/injuries"
    API_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries"

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or self.DEFAULT_URL

    def get_injuries(self) -> list[InjuryReport]:
        """Fetch injuries from ESPN.

        Tries the ESPN API first, then falls back to HTML scraping.
        Returns an empty list on error.
        """
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.get(self.base_url)
                if response.status_code != 200:
                    return []
                return self._parse_response(response.text)
        except Exception:
            return []

    def get_injuries_from_api(self) -> list[InjuryReport]:
        """Fetch injuries from ESPN's structured API endpoint.

        The API returns JSON with team-by-team injury data.
        """
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.get(self.API_URL)
                if response.status_code != 200:
                    return []
                data = response.json()
                return self._parse_api_response(data)
        except Exception:
            return []

    def _parse_api_response(self, data: dict) -> list[InjuryReport]:
        """Parse the ESPN API JSON response into InjuryReport objects."""
        reports: list[InjuryReport] = []
        for team_entry in data.get("injuries", []):
            team_info = team_entry.get("team", {})
            team_abbr = team_info.get("abbreviation", "Unknown")
            for injury in team_entry.get("injuries", []):
                athlete = injury.get("athlete", {})
                player_name = athlete.get("displayName", "Unknown")
                position = athlete.get("position", {}).get("abbreviation", "")
                status_str = injury.get("status", "").lower()
                status = _STATUS_MAP.get(status_str, InjuryStatus.QUESTIONABLE)
                injury_type = injury.get("type", {}).get("name", "")
                reports.append(
                    InjuryReport(
                        player_name=player_name,
                        team=team_abbr,
                        opponent="",
                        status=status,
                        injury=injury_type,
                        date=date.today(),
                        position=position,
                    )
                )
        return reports

    def _parse_response(self, html: str) -> list[InjuryReport]:
        """Parse ESPN injury page HTML into InjuryReport objects.

        Handles both JSON API responses and HTML table scraping.
        """
        # Try JSON first (ESPN API responses)
        if html.strip().startswith("{"):
            try:
                import json

                data = json.loads(html)
                return self._parse_api_response(data)
            except (json.JSONDecodeError, KeyError):
                pass

        # Fall back to HTML table parsing
        return self._parse_html(html)

    def _parse_html(self, html: str) -> list[InjuryReport]:
        """Parse ESPN injury HTML tables.

        ESPN injury pages contain tables with columns:
        Name, Pos, Date, Status, Injury
        """
        reports: list[InjuryReport] = []

        # Find table rows in the injury tables
        row_pattern = re.compile(r"<tr[^>]*>.*?</tr>", re.DOTALL | re.IGNORECASE)
        cell_pattern = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL | re.IGNORECASE)
        tag_pattern = re.compile(r"<[^>]+>")

        rows = row_pattern.findall(html)
        for row in rows:
            cells = cell_pattern.findall(row)
            if len(cells) < 4:
                continue

            # Extract text from HTML cells
            cell_texts = [tag_pattern.sub("", c).strip() for c in cells]

            player_name = cell_texts[0] if len(cell_texts) > 0 else ""
            team = cell_texts[1] if len(cell_texts) > 1 else ""
            status_str = cell_texts[3].lower() if len(cell_texts) > 3 else ""
            injury = cell_texts[4] if len(cell_texts) > 4 else ""

            if not player_name:
                continue

            status = _STATUS_MAP.get(status_str, InjuryStatus.QUESTIONABLE)

            reports.append(
                InjuryReport(
                    player_name=player_name,
                    team=team,
                    opponent="",
                    status=status,
                    injury=injury,
                    date=date.today(),
                )
            )

        return reports

    def filter_by_team(self, injuries: list[InjuryReport], team: str) -> list[InjuryReport]:
        """Filter injuries by team abbreviation."""
        return [i for i in injuries if i.team == team]

    def filter_by_status(
        self, injuries: list[InjuryReport], status: InjuryStatus
    ) -> list[InjuryReport]:
        """Filter injuries by status."""
        return [i for i in injuries if i.status == status]

    def get_active_players(self, injuries: list[InjuryReport]) -> list[InjuryReport]:
        """Get only active players from injury list."""
        return [i for i in injuries if i.is_active]
