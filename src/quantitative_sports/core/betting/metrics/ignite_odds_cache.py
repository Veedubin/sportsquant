"""
Ignite-based odds caching with TTL and credit tracking.

Provides:
- Odds caching with TTL in Apache Ignite
- Credit usage tracking in Ignite
- Budget monitoring with alerts
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

try:
    from pyignite import Client
    from pyignite.cache import Cache

    _PYIGNITE_AVAILABLE = True
except ImportError:
    Client = None  # type: ignore[assignment]
    Cache = None  # type: ignore[assignment]
    _PYIGNITE_AVAILABLE = False

logger = logging.getLogger(__name__)


ODDS_CACHE_TTL_SECONDS = 300
CREDIT_CACHE_TTL_SECONDS = 60


@dataclass
class IgniteOddsCacheConfig:
    """Configuration for Ignite odds cache."""

    host: str = "127.0.0.1"
    port: int = 10800
    ignite_version: str = "2.15.0"
    connection_timeout_ms: int = 10000
    max_retries: int = 3
    username: Optional[str] = None
    password: Optional[str] = None


class IgniteOddsCache:
    """Ignite-based cache for odds data with TTL support."""

    def __init__(self, config: Optional[IgniteOddsCacheConfig] = None):
        self.config = config or IgniteOddsCacheConfig()
        self._client: Optional[Client] = None
        self._cache: Optional[Cache] = None
        self._credit_cache: Optional[Cache] = None

    def connect(self) -> None:
        """Connect to Ignite cluster."""
        try:
            self._client = Client(
                host=self.config.host,
                port=self.config.port,
                version=self.config.ignite_version,
                connection_timeout=self.config.connection_timeout_ms,
                max_retries=self.config.max_retries,
                username=self.config.username,
                password=self.config.password,
            )
            self._client.connect()
            self._cache = self._client.get_or_create_cache("odds_api_cache")
            self._credit_cache = self._client.get_or_create_cache("credit_tracking")
            logger.info(
                "Connected to Ignite cluster at %s:%s",
                self.config.host,
                self.config.port,
            )
        except Exception as e:
            logger.error("Failed to connect to Ignite: %s", e)
            raise

    def disconnect(self) -> None:
        """Disconnect from Ignite cluster."""
        if self._client:
            self._client.close()
            self._client = None
            self._cache = None
            self._credit_cache = None

    def _get_cache(self) -> Cache:
        if self._cache is None:
            self.connect()
        assert self._cache is not None
        return self._cache

    def _get_credit_cache(self) -> Cache:
        if self._credit_cache is None:
            self.connect()
        assert self._credit_cache is not None
        return self._credit_cache

    def _make_odds_key(self, sport: str, event_id: str) -> str:
        return f"odds_api:{sport}:{event_id}"

    def _make_credit_key(self, sport: str) -> str:
        return f"odds_api:credits:{sport}"

    def get_odds(self, sport: str, event_id: str) -> Optional[dict[str, Any]]:
        """Get cached odds for an event."""
        try:
            cache = self._get_cache()
            key = self._make_odds_key(sport, event_id)
            data = cache.get(key)
            if data:
                result = json.loads(data)
                stored_time = datetime.fromisoformat(result.get("cached_at", "2000-01-01"))
                age_seconds = (datetime.now(timezone.utc) - stored_time).total_seconds()
                if age_seconds < ODDS_CACHE_TTL_SECONDS:
                    logger.debug("Cache hit for %s", key)
                    return result
                cache.remove(key)  # type: ignore[attr-defined]
                logger.debug("Cache expired for %s", key)
            return None
        except Exception as e:  # pylint: disable=W0718
            logger.warning("Failed to get odds from cache: %s", e)
            return None

    def set_odds(self, sport: str, event_id: str, odds_data: dict[str, Any]) -> None:
        """Cache odds with timestamp."""
        try:
            cache = self._get_cache()
            key = self._make_odds_key(sport, event_id)
            odds_data["cached_at"] = datetime.now(timezone.utc).isoformat()
            cache.put(key, json.dumps(odds_data))
            logger.debug("Cached odds for %s", key)
        except Exception as e:  # pylint: disable=W0718
            logger.warning("Failed to cache odds: %s", e)

    def invalidate_odds(self, sport: str, event_id: str) -> None:
        """Invalidate cached odds for an event."""
        try:
            cache = self._get_cache()
            key = self._make_odds_key(sport, event_id)
            cache.remove(key)  # type: ignore[attr-defined]
            logger.debug("Invalidated cache for %s", key)
        except Exception as e:  # pylint: disable=W0718
            logger.warning("Failed to invalidate cache: %s", e)

    def get_credit_usage(self, sport: str) -> int:
        """Get current credit usage for a sport."""
        try:
            cache = self._get_credit_cache()
            key = self._make_credit_key(sport)
            data = cache.get(key)
            if data:
                parsed = json.loads(data)
                return parsed.get("used_credits", 0)
            return 0
        except Exception as e:  # pylint: disable=W0718
            logger.warning("Failed to get credit usage: %s", e)
            return 0

    def set_credit_usage(self, sport: str, used_credits: int, monthly_limit: int) -> None:
        """Update credit usage for a sport."""
        try:
            cache = self._get_credit_cache()
            key = self._make_credit_key(sport)
            data = {
                "used_credits": used_credits,
                "monthly_limit": monthly_limit,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            cache.put(key, json.dumps(data))
            logger.debug("Updated credit usage for %s: %d/%d", sport, used_credits, monthly_limit)
        except Exception as e:  # pylint: disable=W0718
            logger.warning("Failed to set credit usage: %s", e)

    def increment_credit_usage(self, sport: str, credit_amount: int, monthly_limit: int) -> int:
        """Atomically increment credit usage and return new value."""
        current = self.get_credit_usage(sport)
        new_total = current + credit_amount
        self.set_credit_usage(sport, new_total, monthly_limit)
        return new_total

    def get_budget_status(self, sport: str, monthly_limit: int) -> dict[str, Any]:
        """Get current budget status for a sport."""
        used = self.get_credit_usage(sport)
        remaining = monthly_limit - used
        usage_percent = (used / monthly_limit * 100) if monthly_limit > 0 else 0

        return {
            "used_credits": used,
            "monthly_limit": monthly_limit,
            "remaining_credits": remaining,
            "usage_percent": usage_percent,
            "is_warning": usage_percent >= 80,
            "is_critical": usage_percent >= 95,
        }


class CreditBudgetMonitor:
    """Monitor credit budget and send alerts."""

    def __init__(
        self,
        ignite_cache: IgniteOddsCache,
        monthly_limit: int = 5000000,
        warning_threshold: float = 0.80,
        critical_threshold: float = 0.95,
    ):
        self.cache = ignite_cache
        self.monthly_limit = monthly_limit
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self._alerts_sent: dict[str, datetime] = {}

    def check_budget(self, sport: str) -> dict[str, Any]:
        """Check budget and return status with alert flags."""
        status = self.cache.get_budget_status(sport, self.monthly_limit)
        now = datetime.now(timezone.utc)

        if status["is_critical"] and "critical" not in self._alerts_sent:
            logger.critical(
                "CRITICAL: Credit budget at %.1f%% (%s remaining) for %s",
                status["usage_percent"],
                status["remaining_credits"],
                sport,
            )
            self._alerts_sent["critical"] = now
            status["alert_triggered"] = "critical"
        elif status["is_warning"] and "warning" not in self._alerts_sent:
            logger.warning(
                "WARNING: Credit budget at %.1f%% (%s remaining) for %s",
                status["usage_percent"],
                status["remaining_credits"],
                sport,
            )
            self._alerts_sent["warning"] = now
            status["alert_triggered"] = "warning"
        else:
            status["alert_triggered"] = None

        return status

    def can_spend(self, sport: str, amount: int) -> bool:
        """Check if there's budget to spend the specified amount."""
        status = self.cache.get_budget_status(sport, self.monthly_limit)
        return status["remaining_credits"] >= amount

    def record_usage(self, sport: str, credits_used: int) -> dict[str, Any]:
        """Record credit usage and return updated budget status."""
        self.cache.increment_credit_usage(sport, credits_used, self.monthly_limit)
        return self.check_budget(sport)

    def reset_alerts(self) -> None:
        """Reset sent alert tracking."""
        self._alerts_sent.clear()


def create_ignite_odds_cache(
    host: str = "127.0.0.1",
    port: int = 10800,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> IgniteOddsCache:
    """Factory function to create Ignite odds cache."""
    config = IgniteOddsCacheConfig(
        host=host,
        port=port,
        username=username,
        password=password,
    )
    cache = IgniteOddsCache(config)
    cache.connect()
    return cache


def create_credit_monitor(
    ignite_cache: IgniteOddsCache,
    monthly_limit: int = 5000000,
) -> CreditBudgetMonitor:
    """Factory function to create credit budget monitor."""
    return CreditBudgetMonitor(
        ignite_cache=ignite_cache,
        monthly_limit=monthly_limit,
    )
