"""Notification configuration from environment variables."""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class NotificationConfig:
    """Configuration for notification system.

    All settings can be overridden via environment variables.
    """

    # Alert thresholds
    ev_threshold: float = 0.03  # 3% edge minimum for alerts
    line_movement_threshold: float = 0.5  # 0.5 point movement
    confidence_threshold: float = 60.0  # 60% confidence minimum

    # Discord
    discord_webhook_url: Optional[str] = field(
        default_factory=lambda: os.getenv("DISCORD_WEBHOOK_URL")
    )
    discord_enabled: bool = field(default_factory=lambda: bool(os.getenv("DISCORD_WEBHOOK_URL")))

    # Slack
    slack_webhook_url: Optional[str] = field(default_factory=lambda: os.getenv("SLACK_WEBHOOK_URL"))
    slack_enabled: bool = field(default_factory=lambda: bool(os.getenv("SLACK_WEBHOOK_URL")))

    # Email
    email_smtp_host: str = field(
        default_factory=lambda: os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com")
    )
    email_smtp_port: int = field(default_factory=lambda: int(os.getenv("EMAIL_SMTP_PORT", "587")))
    email_smtp_user: Optional[str] = field(default_factory=lambda: os.getenv("EMAIL_SMTP_USER"))
    email_smtp_password: Optional[str] = field(
        default_factory=lambda: os.getenv("EMAIL_SMTP_PASSWORD")
    )
    email_from: Optional[str] = field(default_factory=lambda: os.getenv("EMAIL_FROM"))
    email_to: list[str] = field(
        default_factory=lambda: (
            os.getenv("EMAIL_TO", "").split(",") if os.getenv("EMAIL_TO") else []
        )
    )
    email_enabled: bool = field(
        default_factory=lambda: bool(os.getenv("EMAIL_SMTP_USER") and os.getenv("EMAIL_TO"))
    )

    # Queue settings
    queue_db_path: str = "data/notifications/alerts.db"
    queue_enabled: bool = True

    # Rate limiting
    max_alerts_per_minute: int = 10
    max_alerts_per_hour: int = 100

    # Alert preferences
    alert_on_ev: bool = True
    alert_on_line_movement: bool = True
    alert_on_injury: bool = True
    alert_on_summary: bool = True
    summary_time: str = "09:00"  # Daily summary time (HH:MM)

    @classmethod
    def from_env(cls) -> "NotificationConfig":
        """Create config from environment variables."""
        return cls(
            ev_threshold=float(os.getenv("ALERT_THRESHOLD", "0.03")),
            line_movement_threshold=float(os.getenv("LINE_MOVEMENT_THRESHOLD", "0.5")),
            confidence_threshold=float(os.getenv("CONFIDENCE_THRESHOLD", "60.0")),
            discord_webhook_url=os.getenv("DISCORD_WEBHOOK_URL"),
            slack_webhook_url=os.getenv("SLACK_WEBHOOK_URL"),
            email_smtp_host=os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com"),
            email_smtp_port=int(os.getenv("EMAIL_SMTP_PORT", "587")),
            email_smtp_user=os.getenv("EMAIL_SMTP_USER"),
            email_smtp_password=os.getenv("EMAIL_SMTP_PASSWORD"),
            email_from=os.getenv("EMAIL_FROM"),
            email_to=[e.strip() for e in os.getenv("EMAIL_TO", "").split(",") if e.strip()],
            queue_db_path=os.getenv("ALERT_QUEUE_DB", "data/notifications/alerts.db"),
            max_alerts_per_minute=int(os.getenv("MAX_ALERTS_PER_MINUTE", "10")),
            max_alerts_per_hour=int(os.getenv("MAX_ALERTS_PER_HOUR", "100")),
            alert_on_ev=os.getenv("ALERT_ON_EV", "true").lower() == "true",
            alert_on_line_movement=os.getenv("ALERT_ON_LINE_MOVEMENT", "true").lower() == "true",
            alert_on_injury=os.getenv("ALERT_ON_INJURY", "true").lower() == "true",
            alert_on_summary=os.getenv("ALERT_ON_SUMMARY", "true").lower() == "true",
            summary_time=os.getenv("SUMMARY_TIME", "09:00"),
        )

    def is_enabled(self) -> bool:
        """Check if any notification channel is enabled."""
        return self.discord_enabled or self.slack_enabled or self.email_enabled
