"""ESPN injury scraper stub."""

from dataclasses import dataclass
from datetime import date
from enum import Enum


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


class ESPNInjuryScraper:
    """ESPN injury scraper stub."""

    def __init__(self, base_url: str = "https://www.espn.com/nba/injuries"):
        self.base_url = base_url

    def get_injuries(self) -> list:
        return []

    def filter_by_team(self, injuries: list, team: str) -> list:
        return [i for i in injuries if i.team == team]

    def filter_by_status(self, injuries: list, status: InjuryStatus) -> list:
        return [i for i in injuries if i.status == status]

    def get_active_players(self, injuries: list) -> list:
        return [i for i in injuries if i.is_active]
