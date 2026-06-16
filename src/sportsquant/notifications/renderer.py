"""Discord webhook payload renderer.

Converts InsightFeed to Discord webhook payloads with embed chunking support.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sportsquant.notifications.models import Event, Insight, InsightFeed, Presentation


@dataclass
class WebhookPayload:
    """Discord webhook payload ready for POST."""

    username: str = ""
    avatar_url: str = ""
    content: str = ""
    allowed_mentions: dict[str, list[str]] = field(default_factory=lambda: {"parse": []})
    embeds: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "username": self.username,
            "avatar_url": self.avatar_url,
            "content": self.content,
            "allowed_mentions": self.allowed_mentions,
            "embeds": self.embeds,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class RenderedMessage:
    """A rendered webhook message with optional image attachment."""

    payload: WebhookPayload
    image_bytes: bytes | None = None
    image_filename: str = "matchup_card.png"

    def has_image(self) -> bool:
        return self.image_bytes is not None and len(self.image_bytes) > 0


def _format_odds(american_odds: int) -> str:
    """Format American odds with sign."""
    if american_odds >= 0:
        return f"+{american_odds}"
    return str(american_odds)


def _build_insight_embed(insight: Insight, presentation: Presentation | None) -> dict[str, Any]:
    """Build a single insight embed from an Insight object."""

    # Build description
    lines = []

    # Insight statement
    if insight.statement:
        lines.append(insight.statement)

    lines.append("")  # Blank line

    # Pick line
    if insight.pick:
        pick = insight.pick
        line_str = f"{pick.line:g}" if pick.line == int(pick.line) else str(pick.line)
        subject = pick.subject_name
        side_word = "Over" if pick.side == "over" else "Under"
        if pick.side in ("home", "away"):
            side_word = "Home" if pick.side == "home" else "Away"
        if pick.side in ("yes", "no"):
            side_word = "Yes" if pick.side == "yes" else "No"

        if pick.subject_type == "player":
            lines.append(f"**Pick:** {subject} {side_word} {line_str} {pick.market_label}")
        else:
            lines.append(f"**Pick:** {subject} {pick.market_label} ({side_word})")

    # Books line
    if insight.pricing and "best_book" in insight.pricing:
        best_book = insight.pricing["best_book"]
        book_emoji = best_book.get("book_emoji", "")
        book_name = best_book.get("book_name", "")
        odds = _format_odds(best_book.get("american_odds", 0))
        if book_emoji and book_name:
            lines.append(f"**Books:** {book_emoji} {book_name} ({odds})")
        elif book_name:
            lines.append(f"**Books:** {book_name} ({odds})")

    # Add to betslip link
    if insight.deeplink_add_to_betslip_url:
        lines.append(f"[Add to betslip]({insight.deeplink_add_to_betslip_url})")

    description = "\n".join(lines)

    # Color from presentation (default to teal-ish)
    color = 4886754  # #0B644A in decimal
    if presentation:
        color = presentation.accent_color_decimal

    embed: dict[str, Any] = {
        "description": description,
        "color": color,
    }

    return embed


def render_feed_to_webhook_payloads(
    feed: InsightFeed,
    max_embeds_per_message: int = 10,
    max_total_embed_chars: int = 6000,
) -> list[RenderedMessage]:
    """Convert an InsightFeed to one or more Discord webhook messages.

    Handles:
    - Hero embed (matchup card + description)
    - Insight embeds (one per insight)
    - Chunking when > max_embeds_per_message
    - Character limit budgeting

    Args:
        feed: The InsightFeed to render
        max_embeds_per_message: Maximum embeds per Discord message (default 10)
        max_total_embed_chars: Maximum total characters across all embeds (default 6000)

    Returns:
        List of RenderedMessage objects ready for Discord webhook POST
    """
    if not feed.event:
        raise ValueError("InsightFeed must have an event")

    presentation = feed.presentation or Presentation()

    # Build hero embed
    hero_embed = _build_hero_embed(feed.event, presentation)

    # Build insight embeds
    insight_embeds = []
    for insight in feed.insights:
        embed = _build_insight_embed(insight, feed.presentation)
        insight_embeds.append(embed)

    # Sort insights by rank
    insight_embeds.sort(key=lambda e: feed.insights[insight_embeds.index(e)].rank)

    # Calculate available slots (1 for hero, rest for insights)
    max_insight_embeds = max_embeds_per_message - 1

    # Chunk into messages
    messages: list[RenderedMessage] = []
    current_insights: list[dict[str, Any]] = []
    current_char_count = 0

    # Get hero embed char count
    hero_chars = len(hero_embed.get("description", ""))

    def create_message(insights: list[dict[str, Any]]) -> RenderedMessage:
        embeds = [hero_embed] + insights

        # Add footer to last embed if not present
        if insights and "footer" not in insights[-1] and presentation.footer_text:
            embeds[-1]["footer"] = {"text": presentation.footer_text}

        payload = WebhookPayload(
            username=presentation.brand_name,
            avatar_url=presentation.brand_icon_url,
            content=_build_content_header(feed.event),  # type: ignore[arg-type]
            allowed_mentions={"parse": []},
            embeds=embeds,
        )

        return RenderedMessage(
            payload=payload,
            image_bytes=None,  # Set by caller if generating hero card
            image_filename="matchup_card.png",
        )

    for i, embed in enumerate(insight_embeds):
        embed_chars = len(embed.get("description", ""))

        # Check if adding this embed would exceed limits
        would_exceed_count = len(current_insights) >= max_insight_embeds
        would_exceed_chars = (current_char_count + hero_chars + embed_chars) > max_total_embed_chars

        if would_exceed_count or would_exceed_chars:
            # Save current message and start new one
            if current_insights:
                messages.append(create_message(current_insights))
            current_insights = []
            current_char_count = 0

        current_insights.append(embed)
        current_char_count += embed_chars

    # Don't forget the last message
    if current_insights:
        messages.append(create_message(current_insights))

    # If no insights, still send hero message
    if not messages:
        messages.append(create_message([]))

    return messages


def _build_hero_embed(event: Event, presentation: Presentation) -> dict[str, Any]:
    """Build the hero (matchup) embed."""
    title = (
        event.hero_card.title
        if event.hero_card
        else f"{event.away_team.abbr} @ {event.home_team.abbr}"
    )

    # Build description with deeplink substitution
    description = presentation.hero_description
    if event.deeplink_url:
        description = description.replace("DEEPLINK", event.deeplink_url)

    embed: dict[str, Any] = {
        "title": title,
        "description": description,
        "color": presentation.accent_color_decimal,
    }

    # Add image reference if hero card has image_asset_key
    if event.hero_card and event.hero_card.image_asset_key:
        embed["image"] = {"url": f"attachment://{event.hero_card.image_asset_key}"}

    return embed


def _build_content_header(event: Event) -> str:
    """Build the message content (text above embeds)."""
    away = event.away_team.short_name or event.away_team.name
    home = event.home_team.short_name or event.home_team.name
    time = event.display_time_local

    return f"Top insights 📈 for {away} @ {home} {time} 👇"
