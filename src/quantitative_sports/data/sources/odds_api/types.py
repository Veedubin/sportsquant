"""Odds API types stub."""

from dataclasses import dataclass


@dataclass
class PlayerInfo:
    """Player info model."""

    player_id: int
    player_name: str
    team_abbr: str
