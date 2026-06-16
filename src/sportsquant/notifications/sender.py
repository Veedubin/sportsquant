"""Discord webhook sender with 429 retry handling.

Handles posting webhook payloads to Discord with rate limit backoff.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import requests

from sportsquant.notifications.renderer import RenderedMessage

logger = logging.getLogger(__name__)


@dataclass
class SendResult:
    """Result of a webhook send operation."""

    success: bool
    message: str
    status_code: int | None = None
    response_body: str | None = None
    message_id: str | None = None


class DiscordSender:
    """Discord webhook sender with retry logic."""

    def __init__(
        self,
        webhook_url: str | None = None,
        max_retries: int = 3,
        base_backoff_seconds: float = 1.0,
    ):
        """Initialize the sender.

        Args:
            webhook_url: Discord webhook URL (optional, can pass to send methods)
            max_retries: Maximum retry attempts on 429 (default 3)
            base_backoff_seconds: Base backoff time in seconds (default 1.0)
        """
        self.webhook_url = webhook_url
        self.max_retries = max_retries
        self.base_backoff_seconds = base_backoff_seconds

    def send(
        self,
        payload: dict[str, Any],
        webhook_url: str | None = None,
        image_bytes: bytes | None = None,
        image_filename: str = "matchup_card.png",
    ) -> SendResult:
        """Send a webhook message to Discord.

        Args:
            payload: Webhook payload as dict
            webhook_url: Override webhook URL (uses instance URL if not provided)
            image_bytes: Optional PNG bytes for multipart upload
            image_filename: Filename for the image attachment

        Returns:
            SendResult with success status and details
        """
        url = webhook_url or self.webhook_url
        if not url:
            return SendResult(
                success=False,
                message="No webhook URL provided",
                status_code=None,
            )

        # Validate payload has required fields
        if not payload.get("content") and not payload.get("embeds"):
            return SendResult(
                success=False,
                message="Payload must have content or embeds",
                status_code=None,
            )

        # Ensure allowed_mentions is set to avoid pings
        if "allowed_mentions" not in payload:
            payload["allowed_mentions"] = {"parse": []}

        # Build request
        files: dict[str, Any] | None = None
        data: str | dict[str, Any] = payload

        if image_bytes:
            files = {"file": (image_filename, image_bytes, "image/png")}
            data = {"payload_json": payload}

        # Retry loop
        last_error: str = ""
        for attempt in range(self.max_retries + 1):
            try:
                response = requests.post(
                    url,
                    json=data if not files else None,
                    data=data if files else None,
                    files=files,
                    timeout=30.0,
                )

                # Check for 429 (rate limit)
                if response.status_code == 429:
                    # Parse retry-after header
                    retry_after = float(
                        response.headers.get("retry-after", self.base_backoff_seconds)
                    )
                    # Exponential backoff
                    backoff = self.base_backoff_seconds * (2**attempt) + retry_after
                    logger.warning(
                        "Discord rate limited, retrying in %.1fs (attempt %d/%d)",
                        backoff,
                        attempt + 1,
                        self.max_retries + 1,
                    )
                    time.sleep(backoff)
                    continue

                # Check for success
                if response.status_code in (200, 204):
                    # Try to extract message ID from response
                    message_id = None
                    try:
                        resp_data = response.json()
                        message_id = str(resp_data.get("id", ""))
                    except Exception:
                        pass

                    return SendResult(
                        success=True,
                        message="Message sent successfully",
                        status_code=response.status_code,
                        message_id=message_id,
                    )

                # Other error
                error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                logger.error("Discord webhook failed: %s", error_msg)
                return SendResult(
                    success=False,
                    message=error_msg,
                    status_code=response.status_code,
                    response_body=response.text[:500],
                )

            except requests.exceptions.Timeout:
                last_error = "Request timed out"
                logger.warning(
                    "Discord request timeout (attempt %d/%d)",
                    attempt + 1,
                    self.max_retries + 1,
                )

            except requests.exceptions.RequestException as e:
                last_error = f"Request failed: {str(e)}"
                logger.warning(
                    "Discord request error: %s (attempt %d/%d)",
                    e,
                    attempt + 1,
                    self.max_retries + 1,
                )

            # Wait before retry (exponential backoff)
            if attempt < self.max_retries:
                backoff = self.base_backoff_seconds * (2**attempt)
                time.sleep(backoff)

        # All retries exhausted
        return SendResult(
            success=False,
            message=f"Max retries exceeded. Last error: {last_error}",
            status_code=None,
        )

    def send_message(
        self,
        content: str,
        webhook_url: str | None = None,
        embeds: list[dict[str, Any]] | None = None,
    ) -> SendResult:
        """Send a simple text message with optional embeds.

        Args:
            content: Message content (text above embeds)
            webhook_url: Override webhook URL
            embeds: Optional list of embed dicts

        Returns:
            SendResult with success status
        """
        payload: dict[str, Any] = {
            "content": content,
        }
        if embeds:
            payload["embeds"] = embeds

        return self.send(payload=payload, webhook_url=webhook_url)

    def send_rendered_message(
        self,
        message: RenderedMessage,
        webhook_url: str | None = None,
    ) -> SendResult:
        """Send a RenderedMessage to Discord.

        Args:
            message: RenderedMessage with payload and optional image
            webhook_url: Override webhook URL

        Returns:
            SendResult with success status
        """
        return self.send(
            payload=message.payload.to_dict(),
            webhook_url=webhook_url,
            image_bytes=message.image_bytes if message.has_image() else None,
            image_filename=message.image_filename,
        )

    def send_rendered_messages(
        self,
        messages: list[RenderedMessage],
        webhook_url: str | None = None,
    ) -> list[SendResult]:
        """Send multiple RenderedMessages to Discord.

        Args:
            messages: List of RenderedMessage objects
            webhook_url: Override webhook URL

        Returns:
            List of SendResult objects (one per message)
        """
        results = []
        for i, message in enumerate(messages):
            logger.info("Sending message %d/%d to Discord", i + 1, len(messages))
            result = self.send_rendered_message(message, webhook_url)
            results.append(result)

            if not result.success:
                logger.error("Failed to send message %d: %s", i + 1, result.message)
            else:
                logger.info("Successfully sent message %d", i + 1)

            # Small delay between messages to avoid triggering rate limits
            if i < len(messages) - 1:
                time.sleep(0.5)

        return results


def send_webhook(
    webhook_url: str,
    payload: dict[str, Any],
    image_bytes: bytes | None = None,
    image_filename: str = "image.png",
) -> SendResult:
    """Convenience function to send a single webhook message.

    Args:
        webhook_url: Discord webhook URL
        payload: Webhook payload dict
        image_bytes: Optional image bytes for multipart upload
        image_filename: Filename for image attachment

    Returns:
        SendResult with success status
    """
    sender = DiscordSender()
    return sender.send(
        payload=payload,
        webhook_url=webhook_url,
        image_bytes=image_bytes,
        image_filename=image_filename,
    )
