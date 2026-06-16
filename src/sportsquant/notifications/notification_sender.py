"""Notification sender for Discord, Slack, and email."""

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import httpx

from sportsquant.notifications.config import NotificationConfig
from sportsquant.notifications.models import Alert
from sportsquant.notifications.formatter import AlertFormatter


class NotificationSender:
    """Send notifications via multiple channels."""

    def __init__(self, config: Optional[NotificationConfig] = None):
        """Initialize sender with config."""
        self.config = config or NotificationConfig.from_env()
        self.formatter = AlertFormatter()

    async def send_discord(self, alert: Alert) -> bool:
        """Send alert to Discord webhook."""
        if not self.config.discord_enabled or not self.config.discord_webhook_url:
            return False

        try:
            content = self.formatter.format(alert, channel="discord")
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.config.discord_webhook_url,
                    json={"content": content},
                    timeout=10.0,
                )
                return response.status_code == 204
        except Exception as e:
            print(f"Discord send error: {e}")
            return False

    async def send_slack(self, alert: Alert) -> bool:
        """Send alert to Slack webhook."""
        if not self.config.slack_enabled or not self.config.slack_webhook_url:
            return False

        try:
            content = self.formatter.format(alert, channel="slack")
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.config.slack_webhook_url,
                    json={"text": content},
                    timeout=10.0,
                )
                return response.status_code == 200
        except Exception as e:
            print(f"Slack send error: {e}")
            return False

    async def send_email(self, alert: Alert, subject: Optional[str] = None) -> bool:
        """Send alert via email."""
        if not self.config.email_enabled:
            return False

        if not self.config.email_to:
            return False

        try:
            content = self.formatter.format(alert, channel="email")

            if not subject:
                if alert.alert_type.value == "ev":
                    subject = f"+EV Alert: {alert.player_name}"
                elif alert.alert_type.value == "line_movement":
                    subject = f"Line Movement: {alert.player_name}"
                elif alert.alert_type.value == "injury":
                    subject = f"Injury Alert: {alert.player_name}"
                else:
                    subject = "SportsQuant Alert"

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.config.email_from or self.config.email_smtp_user
            msg["To"] = ", ".join(self.config.email_to)

            # Plain text version
            part1 = MIMEText(content, "plain")
            msg.attach(part1)

            # HTML version (basic)
            html_content = content.replace("\n", "<br>")
            part2 = MIMEText(html_content, "html")
            msg.attach(part2)

            # Send email
            context = ssl.create_default_context()
            with smtplib.SMTP(self.config.email_smtp_host, self.config.email_smtp_port) as server:
                server.starttls(context=context)
                if self.config.email_smtp_user and self.config.email_smtp_password:
                    server.login(self.config.email_smtp_user, self.config.email_smtp_password)
                server.sendmail(
                    msg["From"],
                    self.config.email_to,
                    msg.as_string(),
                )
            return True
        except Exception as e:
            print(f"Email send error: {e}")
            return False

    async def send_all(self, alert: Alert) -> dict[str, bool]:
        """Send alert to all enabled channels."""
        results = {}
        results["discord"] = await self.send_discord(alert)
        results["slack"] = await self.send_slack(alert)
        results["email"] = await self.send_email(alert)
        return results

    # Synchronous versions for CLI use
    def send_discord_sync(self, alert: Alert) -> bool:
        """Send alert to Discord webhook (sync)."""
        if not self.config.discord_enabled or not self.config.discord_webhook_url:
            return False

        try:
            content = self.formatter.format(alert, channel="discord")
            response = httpx.post(
                self.config.discord_webhook_url,
                json={"content": content},
                timeout=10.0,
            )
            return response.status_code == 204
        except Exception as e:
            print(f"Discord send error: {e}")
            return False

    def send_slack_sync(self, alert: Alert) -> bool:
        """Send alert to Slack webhook (sync)."""
        if not self.config.slack_enabled or not self.config.slack_webhook_url:
            return False

        try:
            content = self.formatter.format(alert, channel="slack")
            response = httpx.post(
                self.config.slack_webhook_url,
                json={"text": content},
                timeout=10.0,
            )
            return response.status_code == 200
        except Exception as e:
            print(f"Slack send error: {e}")
            return False

    def send_email_sync(self, alert: Alert, subject: Optional[str] = None) -> bool:
        """Send alert via email (sync)."""
        if not self.config.email_enabled:
            return False

        if not self.config.email_to:
            return False

        try:
            content = self.formatter.format(alert, channel="email")

            if not subject:
                if alert.alert_type.value == "ev":
                    subject = f"+EV Alert: {alert.player_name}"
                elif alert.alert_type.value == "line_movement":
                    subject = f"Line Movement: {alert.player_name}"
                elif alert.alert_type.value == "injury":
                    subject = f"Injury Alert: {alert.player_name}"
                else:
                    subject = "SportsQuant Alert"

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.config.email_from or self.config.email_smtp_user
            msg["To"] = ", ".join(self.config.email_to)

            part1 = MIMEText(content, "plain")
            msg.attach(part1)

            html_content = content.replace("\n", "<br>")
            part2 = MIMEText(html_content, "html")
            msg.attach(part2)

            context = ssl.create_default_context()
            with smtplib.SMTP(self.config.email_smtp_host, self.config.email_smtp_port) as server:
                server.starttls(context=context)
                if self.config.email_smtp_user and self.config.email_smtp_password:
                    server.login(self.config.email_smtp_user, self.config.email_smtp_password)
                server.sendmail(
                    msg["From"],
                    self.config.email_to,
                    msg.as_string(),
                )
            return True
        except Exception as e:
            print(f"Email send error: {e}")
            return False

    def send_all_sync(self, alert: Alert) -> dict[str, bool]:
        """Send alert to all enabled channels (sync)."""
        results = {}
        results["discord"] = self.send_discord_sync(alert)
        results["slack"] = self.send_slack_sync(alert)
        results["email"] = self.send_email_sync(alert)
        return results
