"""SportsQuant Notification System.

Unified Discord notification module combining:
- Hero card builder (from sports-analytics)
- Alert models and formatter (from sports-bet)
- Rich Discord notifier (from Sports-Platform)
- Notification pipeline (unified orchestration)

Quick Start::

    from sportsquant.notifications import NotificationPipeline

    pipeline = NotificationPipeline()

    # Send EV alert
    pipeline.send_ev_alert(
        player_name="LeBron James",
        stat_type="points",
        line=25.5,
        side="Over",
        edge=0.05,
        confidence=72.0,
        market_prob=0.48,
        fair_prob=0.55,
        payout_multiplier=1.91,
        site="DraftKings",
    )

    # Rich Discord embeds (async)
    from sportsquant.notifications import DiscordNotifier, BetNotificationData

    notifier = DiscordNotifier()
    await notifier.send_bet_alert(BetNotificationData(...))

    # Send InsightFeed with hero cards
    from sportsquant.notifications import build_insight_feed, BuildFeedConfig

    feed = build_insight_feed(BuildFeedConfig(lines_csv=Path("lines.csv")))
    notifier.send_insight_feed(feed, generate_image=True)
"""

# ---------------------------------------------------------------------------
# Canonical data models (from sports-analytics + sports-bet + Sports-Platform)
# ---------------------------------------------------------------------------

from sportsquant.notifications.models import (
    # Discord Insight models
    Team,
    HeroCard,
    Event,
    BookPrice,
    Pick,
    Confidence,
    Insight,
    Presentation,
    InsightFeed,
    # Alert models
    AlertType,
    Alert,
    EVAlert,
    LineMovementAlert,
    InjuryAlert,
    SummaryAlert,
    # Discord embed / notification models
    NotificationType,
    DiscordEmbed,
    BetNotificationData,
    SteamNotificationData,
)

# ---------------------------------------------------------------------------
# Hero card generation (from sports-analytics)
# ---------------------------------------------------------------------------

from sportsquant.notifications.hero_card import (
    HeroCardConfig,
    generate_hero_card,
    get_hero_card_bytes,
    save_hero_card,
    hex_to_rgb,
    interpolate_color,
    download_team_logo,
    create_placeholder_logo,
)

# ---------------------------------------------------------------------------
# Feed builder (from sports-analytics)
# ---------------------------------------------------------------------------

from sportsquant.notifications.builder import (
    BuildFeedConfig,
    build_insight_feed,
    TEAM_INFO,
    BOOK_EMOJI_MAP,
)

# ---------------------------------------------------------------------------
# Webhook renderer (from sports-analytics)
# ---------------------------------------------------------------------------

from sportsquant.notifications.renderer import (
    WebhookPayload,
    RenderedMessage,
    render_feed_to_webhook_payloads,
)

# ---------------------------------------------------------------------------
# Discord sender (from sports-analytics)
# ---------------------------------------------------------------------------

from sportsquant.notifications.sender import (
    SendResult,
    DiscordSender,
    send_webhook,
)

# ---------------------------------------------------------------------------
# Configuration (from sports-bet)
# ---------------------------------------------------------------------------

from sportsquant.notifications.config import NotificationConfig

# ---------------------------------------------------------------------------
# Alert formatter (from sports-bet)
# ---------------------------------------------------------------------------

from sportsquant.notifications.formatter import AlertFormatter

# ---------------------------------------------------------------------------
# Alert queue (from sports-bet)
# ---------------------------------------------------------------------------

from sportsquant.notifications.queue import AlertQueue

# ---------------------------------------------------------------------------
# Notification sender (multi-channel, from sports-bet)
# ---------------------------------------------------------------------------

from sportsquant.notifications.notification_sender import NotificationSender

# ---------------------------------------------------------------------------
# Notification service (from sports-bet)
# ---------------------------------------------------------------------------

from sportsquant.notifications.service import (
    NotificationService,
    create_from_pipeline_result,
)

# ---------------------------------------------------------------------------
# Pipeline integration (from sports-bet)
# ---------------------------------------------------------------------------

from sportsquant.notifications.pipeline_integration import (
    EvaluatorNotifier,
    send_ev_alerts_from_pipeline,
    send_line_movement_alerts,
    send_daily_summary,
)

# ---------------------------------------------------------------------------
# Unified Discord facade (new - combines sports-analytics + Sports-Platform)
# ---------------------------------------------------------------------------

from sportsquant.notifications.discord import (
    DiscordNotifier,
    NotifierHolder,
    get_notifier,
    test_notification,
)

# ---------------------------------------------------------------------------
# Webhook models and helpers (from Sports-Platform)
# ---------------------------------------------------------------------------

from sportsquant.notifications.webhook import (
    WebhookConfig,
    BetRecommendation,
    notify_bet_placed,
    notify_steam_move,
    notify_prediction_ready,
    build_recommendations_from_simulation,
)

# ---------------------------------------------------------------------------
# Notification pipeline (new - unified orchestration)
# ---------------------------------------------------------------------------

from sportsquant.notifications.pipeline import NotificationPipeline

__all__ = [
    # --- Canonical data models ---
    "Team",
    "HeroCard",
    "Event",
    "BookPrice",
    "Pick",
    "Confidence",
    "Insight",
    "Presentation",
    "InsightFeed",
    "AlertType",
    "Alert",
    "EVAlert",
    "LineMovementAlert",
    "InjuryAlert",
    "SummaryAlert",
    "NotificationType",
    "DiscordEmbed",
    "BetNotificationData",
    "SteamNotificationData",
    # --- Hero card ---
    "HeroCardConfig",
    "generate_hero_card",
    "get_hero_card_bytes",
    "save_hero_card",
    "hex_to_rgb",
    "interpolate_color",
    "download_team_logo",
    "create_placeholder_logo",
    # --- Feed builder ---
    "BuildFeedConfig",
    "build_insight_feed",
    "TEAM_INFO",
    "BOOK_EMOJI_MAP",
    # --- Renderer ---
    "WebhookPayload",
    "RenderedMessage",
    "render_feed_to_webhook_payloads",
    # --- Sender ---
    "SendResult",
    "DiscordSender",
    "send_webhook",
    # --- Configuration ---
    "NotificationConfig",
    # --- Formatter ---
    "AlertFormatter",
    # --- Queue ---
    "AlertQueue",
    # --- Multi-channel sender ---
    "NotificationSender",
    # --- Service ---
    "NotificationService",
    "create_from_pipeline_result",
    # --- Pipeline integration ---
    "EvaluatorNotifier",
    "send_ev_alerts_from_pipeline",
    "send_line_movement_alerts",
    "send_daily_summary",
    # --- Unified Discord facade ---
    "DiscordNotifier",
    "NotifierHolder",
    "get_notifier",
    "test_notification",
    # --- Webhook ---
    "WebhookConfig",
    "BetRecommendation",
    "notify_bet_placed",
    "notify_steam_move",
    "notify_prediction_ready",
    "build_recommendations_from_simulation",
    # --- Pipeline ---
    "NotificationPipeline",
]
