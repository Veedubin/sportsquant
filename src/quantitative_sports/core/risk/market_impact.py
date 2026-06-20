"""
Market Impact Model and CLV-Based Throttling System

Implements:
1. Market impact modeling for bet sizing
2. Line movement tracking and reversal detection
3. CLV (Closing Line Value) based bet throttling
4. Integration with position sizing for risk management

Adapted from sports_analytics.model.market_impact
Changes: Replaced sports_analytics.util.logging with standard logging
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MarketImpactConfig:
    """Configuration for market impact modeling."""

    base_impact_factor: float = 0.001
    impact_decay_rate: float = 0.5
    max_impact_penalty: float = 0.5
    min_liquidity_threshold: float = 10000
    line_movement_window_minutes: int = 30


@dataclass
class LineMovement:
    """Track line movements for a specific bet."""

    book: str
    initial_line: float
    current_line: float
    movement_time: datetime
    movement_amount: float
    is_reversal: bool = False
    bet_id: str = ""


@dataclass(frozen=True)
class CLVThrottleConfig:
    """Configuration for CLV-based throttling."""

    enable_clv_throttling: bool = True
    max_stake_increase_on_clv: float = 1.5
    max_stake_decrease_on_clv: float = 0.5
    hard_cap_multiplier: float = 0.3


class MarketImpactModel:
    """Model for estimating market impact of bets."""

    def __init__(self, config: Optional[MarketImpactConfig] = None):
        self.config = config or MarketImpactConfig()
        self._movement_tracking: dict[str, LineMovement] = {}

    def estimate_impact(
        self,
        stake: float,
        market_liquidity: float,
        line_movements: list[LineMovement],
    ) -> float:
        """Estimate market impact of a potential bet.

        Args:
            stake: Proposed bet stake amount
            market_liquidity: Available liquidity in the market
            line_movements: List of recent line movements

        Returns:
            Estimated impact factor (0.0 to 1.0, higher = more impact)
        """
        if market_liquidity <= 0:
            return 1.0

        if market_liquidity < self.config.min_liquidity_threshold:
            liquidity_penalty = 1.0 - (market_liquidity / self.config.min_liquidity_threshold)
        else:
            liquidity_penalty = 0.0

        stake_ratio = stake / market_liquidity
        base_impact = self.config.base_impact_factor * stake_ratio

        if line_movements:
            recent_movements = [
                m
                for m in line_movements
                if m.movement_time
                > datetime.now(timezone.utc)
                - timedelta(minutes=self.config.line_movement_window_minutes)
            ]
            if recent_movements:
                movement_intensity = sum(abs(m.movement_amount) for m in recent_movements)
                movement_impact = min(movement_intensity * 0.1, 0.5)
            else:
                movement_impact = 0.0
        else:
            movement_impact = 0.0

        total_impact = base_impact + liquidity_penalty * 0.3 + movement_impact * 0.2

        return min(total_impact, 1.0)

    def compute_impact_penalty(self, impact: float) -> float:
        """Convert impact to penalty factor.

        Args:
            impact: Estimated impact (0.0 to 1.0)

        Returns:
            Penalty factor (0.0 to 1.0, where 1.0 = no penalty)
        """
        penalty = 1.0 - min(impact, self.config.max_impact_penalty)
        return max(penalty, 0.0)

    def track_line_movement(
        self,
        bet_id: str,
        book: str,
        initial_line: float,
    ) -> str:
        """Start tracking a line movement for a bet.

        Args:
            bet_id: Unique identifier for the bet
            book: Sportsbook identifier
            initial_line: Starting line value

        Returns:
            movement_id: Unique identifier for tracking
        """
        movement_id = str(uuid.uuid4())
        movement = LineMovement(
            book=book,
            initial_line=initial_line,
            current_line=initial_line,
            movement_time=datetime.now(timezone.utc),
            movement_amount=0.0,
            is_reversal=False,
            bet_id=bet_id,
        )
        self._movement_tracking[movement_id] = movement
        logger.debug("Started tracking line movement %s for bet %s", movement_id, bet_id)
        return movement_id

    def update_line_movement(
        self,
        movement_id: str,
        current_line: float,
        timestamp: Optional[datetime] = None,
    ) -> bool:
        """Update line movement with new value.

        Args:
            movement_id: Tracking ID from track_line_movement
            current_line: New line value
            timestamp: Optional timestamp, defaults to now

        Returns:
            True if updated successfully, False if not found
        """
        if movement_id not in self._movement_tracking:
            logger.warning("Movement ID %s not found", movement_id)
            return False

        movement = self._movement_tracking[movement_id]
        old_line = movement.current_line
        movement.current_line = current_line
        movement.movement_time = timestamp or datetime.now(timezone.utc)
        movement.movement_amount = current_line - movement.initial_line
        movement.is_reversal = self._detect_reversal_internal(movement)

        logger.debug(
            "Updated line movement %s: %s -> %s (amount: %s, reversal: %s)",
            movement_id,
            old_line,
            current_line,
            movement.movement_amount,
            movement.is_reversal,
        )
        return True

    def _detect_reversal_internal(self, movement: LineMovement) -> bool:
        """Internal method to detect if line has reversed from initial position."""
        if movement.initial_line == movement.current_line:
            return False
        initial_direction = 1 if movement.initial_line > 0 else -1
        current_direction = 1 if movement.current_line > 0 else -1
        return initial_direction != current_direction

    def detect_reversal(self, movement_id: str) -> bool:
        """Detect if line has reversed from initial position.

        Args:
            movement_id: Tracking ID from track_line_movement

        Returns:
            True if line has reversed, False otherwise
        """
        if movement_id not in self._movement_tracking:
            logger.warning("Movement ID %s not found", movement_id)
            return False
        return self._movement_tracking[movement_id].is_reversal

    def get_movement(self, movement_id: str) -> Optional[LineMovement]:
        """Get line movement data.

        Args:
            movement_id: Tracking ID

        Returns:
            LineMovement if found, None otherwise
        """
        return self._movement_tracking.get(movement_id)

    def get_all_movements_for_bet(self, bet_id: str) -> list[LineMovement]:
        """Get all line movements for a specific bet.

        Args:
            bet_id: Bet identifier

        Returns:
            List of LineMovement objects
        """
        return [m for m in self._movement_tracking.values() if m.bet_id == bet_id]


class CLVThrottler:
    """CLV-based bet sizing throttling system.

    Throttle rules:
    - improving: Allow 20% increase in stake
    - flat: Hold stake constant
    - degrading: Reduce 30% from base stake
    - hard_cap: Immediate line move against, reduce 50%
    - suspend: Reverse CLV detected, stop betting
    """

    THROTTLE_RULES = {
        "improving": 1.2,
        "flat": 1.0,
        "degrading": 0.7,
        "hard_cap": 0.5,
        "suspend": 0.0,
    }

    def __init__(self, config: Optional[CLVThrottleConfig] = None):
        self.config = config or CLVThrottleConfig()

    def get_throttle_multiplier(self, clv_trend: str, line_reversal: bool) -> float:
        """Get throttle multiplier based on CLV trend and line reversal.

        Args:
            clv_trend: CLV trend category ('improving', 'flat', 'degrading', 'hard_cap', 'suspend')
            line_reversal: Whether line has reversed against bet

        Returns:
            Multiplier to apply to base stake (0.0 to 1.2)
        """
        if line_reversal:
            return self.THROTTLE_RULES["hard_cap"]

        clv_trend = clv_trend.lower()
        if clv_trend not in self.THROTTLE_RULES:
            logger.warning("Unknown CLV trend: %s, using 'flat'", clv_trend)
            return self.THROTTLE_RULES["flat"]

        return self.THROTTLE_RULES[clv_trend]

    def apply_throttling(
        self,
        base_stake: float,
        clv_trend: str,
        impact_penalty: float,
    ) -> float:
        """Apply CLV throttling and market impact to position size.

        Args:
            base_stake: Original calculated stake
            clv_trend: CLV trend category
            impact_penalty: Market impact penalty factor (0.0 to 1.0)

        Returns:
            Throttled position size
        """
        if not self.config.enable_clv_throttling:
            return base_stake

        throttle_multiplier = self.get_throttle_multiplier(clv_trend, False)

        throttle_multiplier = max(
            self.config.max_stake_decrease_on_clv,
            min(self.config.max_stake_increase_on_clv, throttle_multiplier),
        )

        throttled_stake = base_stake * throttle_multiplier * impact_penalty

        logger.debug(
            "Applied throttling: base=%.2f, clv_trend=%s, impact_penalty=%.2f, result=%.2f",
            base_stake,
            clv_trend,
            impact_penalty,
            throttled_stake,
        )

        return throttled_stake

    def should_suspend_betting(self, clv_trend: str, line_reversal: bool) -> bool:
        """Determine if betting should be suspended for this market.

        Args:
            clv_trend: CLV trend category
            line_reversal: Whether line has reversed against bet

        Returns:
            True if betting should be suspended
        """
        if line_reversal:
            return True

        return clv_trend.lower() == "suspend"

    def classify_clv_trend(
        self,
        current_clv: float,
        previous_clv: float,
        clv_threshold: float = 0.01,
    ) -> str:
        """Classify CLV trend based on change.

        Args:
            current_clv: Current CLV value
            previous_clv: Previous CLV value
            clv_threshold: Threshold for significant change

        Returns:
            CLV trend category
        """
        clv_change = current_clv - previous_clv

        if clv_change > clv_threshold:
            return "improving"
        if clv_change < -clv_threshold:
            return "degrading"
        return "flat"

    def compute_adaptive_kelly(
        self,
        base_kelly: float,
        clv_trend: str,
        line_reversal: bool,
    ) -> float:
        """Compute Kelly fraction adjusted for CLV and line movements.

        Args:
            base_kelly: Original Kelly fraction
            clv_trend: CLV trend category
            line_reversal: Whether line has reversed

        Returns:
            Adjusted Kelly fraction
        """
        if self.should_suspend_betting(clv_trend, line_reversal):
            return 0.0

        throttle_multiplier = self.get_throttle_multiplier(clv_trend, line_reversal)

        adjusted_kelly = base_kelly * throttle_multiplier

        return max(0.0, adjusted_kelly)


__all__ = [
    "MarketImpactConfig",
    "MarketImpactModel",
    "CLVThrottleConfig",
    "CLVThrottler",
    "LineMovement",
]
