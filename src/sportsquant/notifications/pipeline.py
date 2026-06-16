"""Notification pipeline for SportsQuant.

Wires together:
- Queue management (from sports-bet)
- Formatter (from sports-bet)
- Discord sender (unified facade)
- Pipeline integration hooks (from sports-bet)

Usage::

    from sportsquant.notifications.pipeline import NotificationPipeline

    pipeline = NotificationPipeline()
    pipeline.send_ev_alert(
        player_name="LeBron James",
        stat_type="points",
        line=25.5,
        side="Over",
        edge=0.05,
        confidence=0.72,
        market_prob=0.48,
        fair_prob=0.55,
        payout_multiplier=1.91,
        site="DraftKings",
    )

    # Send daily summary
    pipeline.send_daily_summary(
        total_opportunities=15,
        top_plays=[...],
        ev_breakdown={"DraftKings": 8, "FanDuel": 7},
    )

    # Process queued alerts
    pipeline.process_queue()
"""

from __future__ import annotations

import logging
from typing import Optional

from sportsquant.notifications.config import NotificationConfig
from sportsquant.notifications.discord import DiscordNotifier
from sportsquant.notifications.formatter import AlertFormatter
from sportsquant.notifications.queue import AlertQueue
from sportsquant.notifications.notification_sender import NotificationSender
from sportsquant.notifications.service import NotificationService

logger = logging.getLogger(__name__)


class NotificationPipeline:
    """Unified notification pipeline combining queue, formatter, and Discord.

    This is the main entry point for all SportsQuant notifications.
    It wires together:

    1. AlertQueue — persistent SQLite queue with rate limiting
    2. AlertFormatter — formats alerts for different channels
    3. NotificationSender — multi-channel sender (Discord, Slack, email)
    4. DiscordNotifier — rich Discord embed sender (unified facade)
    5. NotificationService — high-level service methods
    """

    def __init__(self, config: Optional[NotificationConfig] = None):
        """Initialize the notification pipeline.

        Args:
            config: NotificationConfig. If None, loads from environment.
        """
        self.config = config or NotificationConfig.from_env()
        self._service = NotificationService(self.config)
        self._queue = AlertQueue(self.config) if self.config.queue_enabled else None
        self._formatter = AlertFormatter()
        self._sender = NotificationSender(self.config)
        self._discord = DiscordNotifier(webhook_url=self.config.discord_webhook_url)

    # ------------------------------------------------------------------
    # EV Alerts
    # ------------------------------------------------------------------

    def send_ev_alert(
        self,
        player_name: str,
        stat_type: str,
        line: float,
        side: str,
        edge: float,
        confidence: float,
        market_prob: float,
        fair_prob: float,
        payout_multiplier: float,
        site: str,
        stake: Optional[float] = None,
        use_queue: bool = True,
    ) -> bool:
        """Send a +EV alert through the pipeline.

        If queue is enabled, the alert is enqueued for batch processing.
        Otherwise, it is sent immediately via all channels.

        Args:
            player_name: Player name.
            stat_type: Stat type (points, rebounds, etc.).
            line: Betting line.
            side: Recommended side (Over/Under).
            edge: Expected value (0.0-1.0).
            confidence: Model confidence (0-100).
            market_prob: Market probability.
            fair_prob: Fair probability.
            payout_multiplier: Payout multiplier.
            site: Sportsbook name.
            stake: Optional stake amount.
            use_queue: Whether to queue the alert.

        Returns:
            True if alert was queued/sent successfully.
        """
        return self._service.send_ev_alert(
            player_name=player_name,
            stat_type=stat_type,
            line=line,
            side=side,
            edge=edge,
            confidence=confidence,
            market_prob=market_prob,
            fair_prob=fair_prob,
            payout_multiplier=payout_multiplier,
            site=site,
            stake=stake,
        )

    # ------------------------------------------------------------------
    # Line Movement Alerts
    # ------------------------------------------------------------------

    def send_line_movement_alert(
        self,
        player_name: str,
        stat_type: str,
        previous_line: float,
        new_line: float,
        site: str,
        market_source: str = "",
        use_queue: bool = True,
    ) -> bool:
        """Send a line movement alert through the pipeline.

        Args:
            player_name: Player name.
            stat_type: Stat type.
            previous_line: Previous line value.
            new_line: New line value.
            site: Sportsbook name.
            market_source: Source of the line movement.
            use_queue: Whether to queue the alert.

        Returns:
            True if alert was queued/sent successfully.
        """
        return self._service.send_line_movement_alert(
            player_name=player_name,
            stat_type=stat_type,
            previous_line=previous_line,
            new_line=new_line,
            site=site,
            market_source=market_source,
        )

    # ------------------------------------------------------------------
    # Injury Alerts
    # ------------------------------------------------------------------

    def send_injury_alert(
        self,
        player_name: str,
        team: str,
        status: str,
        affected_props: list[str],
        impact: str = "high",
    ) -> bool:
        """Send an injury alert through the pipeline.

        Args:
            player_name: Injured player name.
            team: Team name.
            status: Injury status (out, doubtful, questionable, probable).
            affected_props: List of affected prop markets.
            impact: Impact level (high, medium, low).

        Returns:
            True if alert was queued/sent successfully.
        """
        return self._service.send_injury_alert(
            player_name=player_name,
            team=team,
            status=status,
            affected_props=affected_props,
            impact=impact,
        )

    # ------------------------------------------------------------------
    # Daily Summary
    # ------------------------------------------------------------------

    def send_daily_summary(
        self,
        total_opportunities: int,
        top_plays: list[dict],
        ev_breakdown: dict,
        sport: str = "NBA",
    ) -> bool:
        """Send a daily summary alert through the pipeline.

        Args:
            total_opportunities: Total number of +EV opportunities.
            top_plays: List of top play dicts.
            ev_breakdown: Dict mapping site -> count of plays.
            sport: Sport league.

        Returns:
            True if alert was queued/sent successfully.
        """
        return self._service.send_summary_alert(
            total_opportunities=total_opportunities,
            top_plays=top_plays,
            ev_breakdown=ev_breakdown,
            sport=sport,
        )

    # ------------------------------------------------------------------
    # Rich Discord Notifications (async)
    # ------------------------------------------------------------------

    async def send_rich_bet_alert(
        self,
        player_name: str,
        market: str,
        line: float,
        side: str,
        stake: float,
        odds: float,
        edge: float,
    ) -> bool:
        """Send a rich Discord embed for a bet placement.

        This uses the unified DiscordNotifier for rich embeds
        (not the simple text-based AlertFormatter).

        Args:
            player_name: Player name.
            market: Market type.
            line: Betting line.
            side: Bet side.
            stake: Stake amount.
            odds: Decimal odds.
            edge: Expected edge.

        Returns:
            True if sent successfully.
        """
        from sportsquant.notifications.models import BetNotificationData

        data = BetNotificationData(
            player_name=player_name,
            market=market,
            line=line,
            side=side,
            stake=stake,
            odds=odds,
            edge=edge,
        )
        return await self._discord.send_bet_alert(data)

    async def send_rich_steam_move_alert(
        self,
        player_name: str,
        market: str,
        old_line: float,
        new_line: float,
        direction: str,
        movement_pct: float,
    ) -> bool:
        """Send a rich Discord embed for a steam move.

        Args:
            player_name: Player name.
            market: Market type.
            old_line: Previous line.
            new_line: New line.
            direction: Movement direction (up/down).
            movement_pct: Percentage of movement.

        Returns:
            True if sent successfully.
        """
        from sportsquant.notifications.models import SteamNotificationData

        data = SteamNotificationData(
            player_name=player_name,
            market=market,
            old_line=old_line,
            new_line=new_line,
            direction=direction,
            movement_pct=movement_pct,
        )
        return await self._discord.send_steam_move_alert(data)

    # ------------------------------------------------------------------
    # Queue Processing
    # ------------------------------------------------------------------

    def process_queue(self) -> dict:
        """Process all pending alerts from the queue.

        Returns:
            Dict with number of processed alerts.
        """
        return self._service.process_queue()

    def get_queue_stats(self) -> dict:
        """Get queue statistics.

        Returns:
            Dict with pending, sent, and failed counts.
        """
        if self._queue:
            return self._queue.get_stats()
        return {"pending": 0, "sent": 0, "failed": 0}

    # ------------------------------------------------------------------
    # Direct Discord Access
    # ------------------------------------------------------------------

    @property
    def discord(self) -> DiscordNotifier:
        """Access the Discord notifier for advanced operations."""
        return self._discord

    @property
    def service(self) -> NotificationService:
        """Access the notification service for advanced operations."""
        return self._service

    @property
    def formatter(self) -> AlertFormatter:
        """Access the alert formatter."""
        return self._formatter
