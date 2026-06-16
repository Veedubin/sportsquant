"""Unified Discord notification facade for SportsQuant.

Combines the hero card builder from sports-analytics with the notifier
from Sports-Platform, providing a single entry point for all Discord
notifications:

- send_bet_alert(bet_decision) — Rich embed for bet placements
- send_steam_move_alert(move_data) — Rich embed for line movements
- send_daily_summary(top_plays) — Daily summary embed
- send_insight_feed(feed) — Full InsightFeed with hero cards
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from sportsquant.notifications.models import (
    BetNotificationData,
    DiscordEmbed,
    InsightFeed,
    SteamNotificationData,
)
from sportsquant.notifications.hero_card import generate_hero_card
from sportsquant.notifications.renderer import (
    RenderedMessage,
    render_feed_to_webhook_payloads,
)
from sportsquant.notifications.sender import DiscordSender, SendResult

logger = logging.getLogger(__name__)

PLATFORM_NAME = "SportsQuant"


def _get_utc_timestamp() -> str:
    """Get current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _get_webhook_url() -> str | None:
    """Get Discord webhook URL from environment."""
    return os.getenv("DISCORD_WEBHOOK_URL") or os.getenv("SPORTSQUANT_DISCORD_WEBHOOK")


class DiscordNotifier:
    """Unified Discord notification facade.

    Combines:
    - Rich hero card / embed building (from sports-analytics)
    - Async webhook sending (from Sports-Platform)
    - Rate-limited sender (from sports-analytics)
    """

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        bot_name: str = "SportsQuant",
        avatar_url: Optional[str] = None,
        max_retries: int = 3,
    ):
        self.webhook_url = webhook_url or _get_webhook_url()
        self.bot_name = bot_name
        self.avatar_url = avatar_url
        self._sender = DiscordSender(
            webhook_url=self.webhook_url,
            max_retries=max_retries,
        )

    def is_configured(self) -> bool:
        """Check if Discord is configured."""
        return bool(self.webhook_url)

    # ------------------------------------------------------------------
    # High-level convenience methods
    # ------------------------------------------------------------------

    async def send_bet_alert(self, data: BetNotificationData) -> bool:
        """Send a bet placement notification with rich embed.

        Args:
            data: BetNotificationData with bet details.

        Returns:
            True if notification was sent successfully.
        """
        embed = DiscordEmbed(
            title="🎰 Bet Placed",
            description=f"Bet placed on **{data.player_name}**",
            color=0x00FF00,
            fields=[
                {"name": "📊 Market", "value": data.market.title(), "inline": True},
                {"name": "📏 Line", "value": f"{data.line}", "inline": True},
                {"name": "🎯 Side", "value": data.side.upper(), "inline": True},
                {"name": "💰 Stake", "value": f"${data.stake:.2f}", "inline": True},
                {"name": "📈 Odds", "value": f"{data.odds:.2f}", "inline": True},
                {"name": "📉 Edge", "value": f"{data.edge:.1%}", "inline": True},
            ],
            footer={"text": PLATFORM_NAME},
            timestamp=_get_utc_timestamp(),
        )

        return await self._send_async(embeds=[embed])

    async def send_steam_move_alert(self, data: SteamNotificationData) -> bool:
        """Send a steam move notification with rich embed.

        Args:
            data: SteamNotificationData with movement details.

        Returns:
            True if notification was sent successfully.
        """
        color = 0xFF0000 if data.direction == "up" else 0x0000FF
        emoji = "📈" if data.direction == "up" else "📉"

        embed = DiscordEmbed(
            title=f"{emoji} Steam Move Detected",
            description=f"Line movement detected for **{data.player_name}**",
            color=color,
            fields=[
                {"name": "📊 Market", "value": data.market.title(), "inline": True},
                {"name": "📏 Old Line", "value": f"{data.old_line}", "inline": True},
                {"name": "📏 New Line", "value": f"{data.new_line}", "inline": True},
                {"name": "🔄 Direction", "value": data.direction.upper(), "inline": True},
                {"name": "📊 Movement", "value": f"{data.movement_pct:.1f}%", "inline": True},
            ],
            footer={"text": PLATFORM_NAME},
            timestamp=_get_utc_timestamp(),
        )

        return await self._send_async(embeds=[embed])

    async def send_daily_summary(
        self,
        total_opportunities: int,
        top_plays: list[dict[str, Any]],
        ev_breakdown: dict[str, int],
        sport: str = "NBA",
    ) -> bool:
        """Send a daily summary notification with rich embed.

        Args:
            total_opportunities: Total number of +EV opportunities.
            top_plays: List of top play dicts.
            ev_breakdown: Dict mapping site -> count of plays.
            sport: Sport league.

        Returns:
            True if notification was sent successfully.
        """
        fields: list[dict[str, object]] = [
            {"name": "📊 Total Opportunities", "value": str(total_opportunities), "inline": True},
        ]

        if top_plays:
            play_lines = []
            for i, play in enumerate(top_plays[:5], 1):
                play_lines.append(
                    f"{i}. {play.get('player', 'N/A')} {play.get('side', '')} "
                    f"{play.get('line', '')} - Edge: +{play.get('edge', 0):.1f}%"
                )
            fields.append(
                {
                    "name": "🏆 Top Plays",
                    "value": "\n".join(play_lines),
                    "inline": False,
                }
            )

        if ev_breakdown:
            breakdown_lines = [f"{site}: {count} plays" for site, count in ev_breakdown.items()]
            fields.append(
                {
                    "name": "📈 EV Breakdown",
                    "value": "\n".join(breakdown_lines),
                    "inline": False,
                }
            )

        embed = DiscordEmbed(
            title=f"📊 Daily Summary - {sport}",
            description="Today's best opportunities",
            color=0x9B59B6,
            fields=fields,
            footer={"text": PLATFORM_NAME},
            timestamp=_get_utc_timestamp(),
        )

        return await self._send_async(embeds=[embed])

    async def send_system_alert(
        self,
        alert_type: str,
        message: str,
        severity: str = "info",
    ) -> bool:
        """Send a system alert notification."""
        colors = {
            "info": 0x3498DB,
            "warning": 0xFFAA00,
            "error": 0xFF0000,
            "success": 0x00FF00,
        }
        emojis = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "🚨",
            "success": "✅",
        }

        embed = DiscordEmbed(
            title=f"{emojis.get(severity, 'ℹ️')} System Alert: {alert_type}",
            description=message,
            color=colors.get(severity, 0x3498DB),
            fields=[
                {"name": "🔔 Type", "value": alert_type.title(), "inline": True},
                {"name": "⚡ Severity", "value": severity.upper(), "inline": True},
            ],
            footer={"text": PLATFORM_NAME},
            timestamp=_get_utc_timestamp(),
        )

        return await self._send_async(embeds=[embed])

    # ------------------------------------------------------------------
    # InsightFeed / hero card support
    # ------------------------------------------------------------------

    def send_insight_feed(
        self,
        feed: InsightFeed,
        generate_image: bool = False,
    ) -> list[SendResult]:
        """Send an InsightFeed as Discord webhook messages with hero cards.

        Args:
            feed: The InsightFeed to render and send.
            generate_image: Whether to generate a hero card PNG image.

        Returns:
            List of SendResult objects, one per message.
        """
        messages = render_feed_to_webhook_payloads(feed)

        if generate_image and feed.event:
            try:
                hero_bytes = generate_hero_card(feed.event)
                if messages:
                    messages[0].image_bytes = hero_bytes
            except Exception as e:
                logger.warning("Failed to generate hero card image: %s", e)

        return self._sender.send_rendered_messages(messages)

    def send_insight_feed_async_prep(
        self,
        feed: InsightFeed,
        generate_image: bool = False,
    ) -> list[RenderedMessage]:
        """Prepare InsightFeed for async sending.

        Returns RenderedMessages that can be sent later via
        _sender.send_rendered_messages().
        """
        messages = render_feed_to_webhook_payloads(feed)

        if generate_image and feed.event:
            try:
                hero_bytes = generate_hero_card(feed.event)
                if messages:
                    messages[0].image_bytes = hero_bytes
            except Exception as e:
                logger.warning("Failed to generate hero card image: %s", e)

        return messages

    # ------------------------------------------------------------------
    # Low-level methods
    # ------------------------------------------------------------------

    async def _send_async(
        self,
        content: Optional[str] = None,
        embeds: Optional[list[DiscordEmbed]] = None,
    ) -> bool:
        """Send a message to Discord via async httpx.

        Args:
            content: Simple text content.
            embeds: List of DiscordEmbed objects.

        Returns:
            True if successful.
        """
        if not self.webhook_url:
            logger.debug("Discord webhook not configured, skipping notification")
            return False

        payload: dict[str, Any] = {}

        if content:
            payload["content"] = content

        payload["username"] = self.bot_name
        if self.avatar_url:
            payload["avatar_url"] = self.avatar_url

        if embeds:
            payload["embeds"] = [self._serialize_embed(e) for e in embeds]

        if not payload:
            logger.warning("Empty Discord payload, nothing to send")
            return False

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                return True

        except httpx.HTTPError as exc:
            logger.error("Failed to send Discord notification: %s", exc)
            return False

    def send_sync(
        self,
        content: Optional[str] = None,
        embeds: Optional[list[DiscordEmbed]] = None,
    ) -> SendResult:
        """Send a message to Discord synchronously via the rate-limited sender.

        Args:
            content: Simple text content.
            embeds: List of DiscordEmbed objects.

        Returns:
            SendResult with success status.
        """
        payload: dict[str, Any] = {}

        if content:
            payload["content"] = content

        payload["username"] = self.bot_name
        if self.avatar_url:
            payload["avatar_url"] = self.avatar_url

        if embeds:
            payload["embeds"] = [self._serialize_embed(e) for e in embeds]

        return self._sender.send(payload=payload)

    @staticmethod
    def _serialize_embed(embed: DiscordEmbed) -> dict[str, Any]:
        """Serialize DiscordEmbed to Discord API format."""
        result: dict[str, Any] = {
            "title": embed.title,
            "description": embed.description,
            "color": embed.color,
        }

        if embed.fields:
            result["fields"] = [
                {
                    "name": f["name"],
                    "value": f["value"],
                    "inline": f.get("inline", False),
                }
                for f in embed.fields
            ]

        if embed.footer:
            result["footer"] = {"text": embed.footer.get("text", "")}

        if embed.timestamp:
            result["timestamp"] = embed.timestamp

        if embed.media:
            if "thumbnail" in embed.media:
                result["thumbnail"] = {"url": embed.media["thumbnail"]}
            if "image" in embed.media:
                result["image"] = {"url": embed.media["image"]}

        return result


# ---------------------------------------------------------------------------
# Singleton convenience
# ---------------------------------------------------------------------------

_notifier_instance: Optional[DiscordNotifier] = None


class NotifierHolder:
    """Holder class for singleton notifier to avoid global statement."""

    _instance: Optional[DiscordNotifier] = None

    @classmethod
    def get_notifier(cls) -> DiscordNotifier:
        """Get or create the global Discord notifier."""
        if cls._instance is None:
            cls._instance = DiscordNotifier()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance (for testing)."""
        cls._instance = None


def get_notifier() -> DiscordNotifier:
    """Get or create the global Discord notifier."""
    return NotifierHolder.get_notifier()


async def test_notification() -> bool:
    """Test if Discord notifications are working."""
    notifier = NotifierHolder.get_notifier()

    if not notifier.is_configured():
        logger.warning("Discord not configured, skipping test notification")
        return False

    embed = DiscordEmbed(
        title="🧪 Test Notification",
        description=f"This is a test notification from {PLATFORM_NAME}",
        color=0x00FF00,
        fields=[
            {"name": "✅ Status", "value": "Working!", "inline": True},
            {
                "name": "⏰ Time",
                "value": _get_utc_timestamp().split("T")[1].split(".")[0],
                "inline": True,
            },
        ],
        footer={"text": PLATFORM_NAME},
        timestamp=_get_utc_timestamp(),
    )

    return await notifier._send_async(embeds=[embed])
