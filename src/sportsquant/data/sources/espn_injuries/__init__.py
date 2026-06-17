"""ESPN injuries data source."""

from sportsquant.data.sources.espn_injuries.scraper import (
    ESPNInjuryScraper,
    InjuryReport,
    InjuryStatus,
)

__all__ = ["ESPNInjuryScraper", "InjuryReport", "InjuryStatus"]
