"""Webhook payload models for external integrations.

Provides Pydantic models for bet placements, steam moves, and
prediction results, plus FastAPI webhook endpoints.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sportsquant.notifications.discord import get_notifier
from sportsquant.notifications.models import BetNotificationData, SteamNotificationData


# ---------------------------------------------------------------------------
# Data models (plain dataclasses, no Pydantic dependency required)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WebhookConfig:
    """Configuration for webhook."""

    url: str
    headers: dict[str, str] | None = None
    timeout_s: int = 30


@dataclass(frozen=True)
class BetRecommendation:
    """Single bet recommendation."""

    player_id: int
    player_name: str
    market: str
    line: float
    side: str
    ev_over: float
    ev_under: float


# ---------------------------------------------------------------------------
# Notification helpers
# ---------------------------------------------------------------------------


async def notify_bet_placed(data: BetNotificationData) -> bool:
    """Send a bet placement notification via the unified DiscordNotifier.

    Args:
        data: BetNotificationData with bet details.

    Returns:
        True if notification was sent successfully.
    """
    notifier = get_notifier()
    return await notifier.send_bet_alert(data)


async def notify_steam_move(data: SteamNotificationData) -> bool:
    """Send a steam move notification via the unified DiscordNotifier.

    Args:
        data: SteamNotificationData with movement details.

    Returns:
        True if notification was sent successfully.
    """
    notifier = get_notifier()
    return await notifier.send_steam_move_alert(data)


async def notify_prediction_ready(
    total_predictions: int,
    positive_edge_count: int,
    top_player: str,
    top_edge: float,
) -> bool:
    """Send a prediction ready notification.

    Args:
        total_predictions: Total number of predictions generated.
        positive_edge_count: Count of positive edge predictions.
        top_player: Player with highest edge.
        top_edge: Highest edge value.

    Returns:
        True if notification was sent successfully.
    """
    notifier = get_notifier()
    return await notifier.send_daily_summary(
        total_opportunities=total_predictions,
        top_plays=[{"player": top_player, "edge": top_edge}],
        ev_breakdown={},
    )


def build_recommendations_from_simulation(
    sim_results: dict[str, Any],
    min_edge: float = 0.02,
) -> list[BetRecommendation]:
    """Build BetRecommendation objects from simulation results.

    Args:
        sim_results: Simulation output dictionary.
        min_edge: Minimum edge threshold for recommendations.

    Returns:
        List of BetRecommendation objects.
    """
    recommendations: list[BetRecommendation] = []

    if not sim_results or "bets" not in sim_results:
        return recommendations

    for bet in sim_results["bets"]:
        edge = bet.get("edge", 0)
        if edge < min_edge:
            continue

        rec = BetRecommendation(
            player_id=bet.get("player_id", 0),
            player_name=bet.get("player_name", ""),
            market=bet.get("market", "pra"),
            line=bet.get("line", 0),
            side="over" if bet.get("ev_over", 0) > bet.get("ev_under", 0) else "under",
            ev_over=bet.get("ev_over", 0),
            ev_under=bet.get("ev_under", 0),
        )
        recommendations.append(rec)

    return recommendations
