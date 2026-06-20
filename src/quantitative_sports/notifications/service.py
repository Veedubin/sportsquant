"""Notification service orchestration.

Integrates the notification queue, formatter, and sender for the
Quant-Sports alert pipeline.
"""

import uuid
from typing import Optional

from quantitative_sports.notifications.config import NotificationConfig
from quantitative_sports.notifications.models import (
    EVAlert,
    LineMovementAlert,
    InjuryAlert,
    SummaryAlert,
)
from quantitative_sports.notifications.notification_sender import NotificationSender
from quantitative_sports.notifications.queue import AlertQueue


class NotificationService:
    """Service for sending alerts integrated with the pipeline."""

    def __init__(self, config: Optional[NotificationConfig] = None):
        """Initialize notification service."""
        self.config = config or NotificationConfig.from_env()
        self.sender = NotificationSender(self.config)
        self.queue = AlertQueue(self.config) if self.config.queue_enabled else None

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
    ) -> bool:
        """Send +EV alert if above threshold."""
        if not self.config.alert_on_ev:
            return False

        if edge < self.config.ev_threshold:
            return False

        if confidence < self.config.confidence_threshold:
            return False

        alert = EVAlert(
            id=str(uuid.uuid4()),
            player_name=player_name,
            stat_type=stat_type,
            line=line,
            recommended_side=side,
            edge=edge,
            confidence=confidence,
            market_prob=market_prob,
            fair_prob=fair_prob,
            payout_multiplier=payout_multiplier,
            site=site,
            stake=stake,
            message=f"+EV Alert: {player_name} {side} {line} {stat_type}",
        )

        # Queue or send immediately
        if self.queue and self.config.queue_enabled:
            return self.queue.enqueue(alert)
        else:
            results = self.sender.send_all_sync(alert)
            return any(results.values())

    def send_line_movement_alert(
        self,
        player_name: str,
        stat_type: str,
        previous_line: float,
        new_line: float,
        site: str,
        market_source: str = "",
    ) -> bool:
        """Send line movement alert if significant."""
        if not self.config.alert_on_line_movement:
            return False

        movement = abs(new_line - previous_line)
        if movement < self.config.line_movement_threshold:
            return False

        alert = LineMovementAlert(
            id=str(uuid.uuid4()),
            player_name=player_name,
            stat_type=stat_type,
            previous_line=previous_line,
            new_line=new_line,
            site=site,
            market_source=market_source,
            message=f"Line Movement: {player_name} {stat_type}",
        )

        if self.queue and self.config.queue_enabled:
            return self.queue.enqueue(alert)
        else:
            results = self.sender.send_all_sync(alert)
            return any(results.values())

    def send_injury_alert(
        self,
        player_name: str,
        team: str,
        status: str,
        affected_props: list[str],
        impact: str = "high",
    ) -> bool:
        """Send injury alert."""
        if not self.config.alert_on_injury:
            return False

        alert = InjuryAlert(
            id=str(uuid.uuid4()),
            player_name=player_name,
            team=team,
            player_status=status,
            affected_props=affected_props,
            impact=impact,
            message=f"Injury Alert: {player_name} ({team})",
        )

        if self.queue and self.config.queue_enabled:
            return self.queue.enqueue(alert)
        else:
            results = self.sender.send_all_sync(alert)
            return any(results.values())

    def send_summary_alert(
        self,
        total_opportunities: int,
        top_plays: list[dict],
        ev_breakdown: dict,
        sport: str = "NBA",
    ) -> bool:
        """Send daily summary alert."""
        if not self.config.alert_on_summary:
            return False

        alert = SummaryAlert(
            id=str(uuid.uuid4()),
            total_opportunities=total_opportunities,
            top_plays=top_plays,
            ev_breakdown=ev_breakdown,
            sport=sport,
            message=f"Daily Summary: {total_opportunities} opportunities",
        )

        if self.queue and self.config.queue_enabled:
            return self.queue.enqueue(alert)
        else:
            results = self.sender.send_all_sync(alert)
            return any(results.values())

    def process_queue(self) -> dict:
        """Process all pending alerts from queue."""
        if not self.queue:
            return {"processed": 0}

        alerts = self.queue.dequeue(limit=50)
        processed = 0

        for alert in alerts:
            results = self.sender.send_all_sync(alert)
            if any(results.values()):
                self.queue.mark_sent(alert.id)
                processed += 1
            else:
                self.queue.mark_failed(alert.id, "all channels failed")

        return {"processed": processed}


def create_from_pipeline_result(
    playable_df,
    site: str = "PrizePicks",
    config: Optional[NotificationConfig] = None,
) -> list[EVAlert]:
    """Create EV alerts from pipeline results DataFrame.

    Args:
        playable_df: DataFrame from AnalysisPipeline.playable_df
        site: Site name for the alerts
        config: Notification config

    Returns:
        List of EVAlert objects for high-confidence plays
    """
    if playable_df is None or playable_df.empty:
        return []

    config = config or NotificationConfig.from_env()
    alerts = []

    for _, row in playable_df.iterrows():
        edge = row.get("Edge_vs_Market", 0)
        confidence = row.get("Confidence", 0)

        if edge >= config.ev_threshold and confidence >= config.confidence_threshold:
            alert = EVAlert(
                id=str(uuid.uuid4()),
                player_name=row.get("Player", ""),
                stat_type=row.get("Stat", ""),
                line=row.get("PP_Line", 0),
                recommended_side=row.get("Recommended_Side", ""),
                edge=edge,
                confidence=confidence,
                market_prob=row.get("Market_Side_Prob", 0),
                fair_prob=row.get("Final_Prob_Side", 0),
                payout_multiplier=1.0,  # Set from site rules if available
                site=site,
                metadata={
                    "tier": row.get("PP_Tier", ""),
                    "market_source": row.get("Market_Source", ""),
                    "books_count": row.get("Books_All_Count", 0),
                },
            )
            alerts.append(alert)

    return alerts
