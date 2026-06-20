"""Pipeline integration hooks for notifications.

Add this to your analysis pipeline to send alerts:

    from quantitative_sports.notifications.service import NotificationService

    # After getting playable props
    service = NotificationService()
    service.send_ev_alert(...)

    # Or create alerts from pipeline results
    from quantitative_sports.notifications.pipeline_integration import send_ev_alerts_from_pipeline
    send_ev_alerts_from_pipeline(pipeline, site="PrizePicks")

    # For evaluator results
    from quantitative_sports.notifications.pipeline_integration import EvaluatorNotifier
    notifier = EvaluatorNotifier()
    notifier.process_results(evaluation_results, site="PrizePicks")
"""

from typing import Optional

from quantitative_sports.notifications.config import NotificationConfig
from quantitative_sports.notifications.models import EVAlert
from quantitative_sports.notifications.service import NotificationService, create_from_pipeline_result


class EvaluatorNotifier:
    """Processes evaluation results and sends notifications for high-value opportunities.

    This class takes results from any evaluator (PrizePicks, Underdog, FanDuel),
    filters by configured thresholds, and queues alerts via AlertQueue.
    """

    def __init__(
        self,
        config: Optional[NotificationConfig] = None,
        min_ev: float = 0.03,
        min_confidence: float = 0.55,
    ):
        """Initialize the evaluator notifier.

        Args:
            config: Notification config. Uses env vars if not provided.
            min_ev: Minimum expected value threshold (0.03 = 3% EV).
            min_confidence: Minimum confidence threshold (0.55 = 55%).
        """
        self._config = config or NotificationConfig.from_env()
        self._service = NotificationService(self._config)
        self._min_ev = min_ev
        self._min_confidence = min_confidence

    def process_results(
        self,
        evaluation_results: list,
        site: str,
    ) -> list[EVAlert]:
        """Process evaluation results and send notifications for high-value plays.

        Args:
            evaluation_results: List of EvaluationResult objects from an evaluator.
            site: Site name (prizepicks, underdog, fanduel).

        Returns:
            List of EVAlert objects that were sent/queued.
        """
        alerts = []

        for result in evaluation_results:
            # Filter by thresholds
            if result.ev < self._min_ev:
                continue
            if result.confidence < self._min_confidence:
                continue

            # Map evaluator side to notification side
            side = self._map_side(result.recommended_side, site)

            # Send notification
            success = self._service.send_ev_alert(
                player_name=result.player_name,
                stat_type=result.stat_type,
                line=result.line,
                side=side,
                edge=result.ev,
                confidence=result.confidence,
                market_prob=result.market_prob,
                fair_prob=result.fair_prob,
                payout_multiplier=result.payout_multiplier,
                site=site,
                stake=result.suggested_stake,
            )

            if success:
                alerts.append(
                    EVAlert(
                        id=f"{site}_{result.player_name}_{result.stat_type}",
                        player_name=result.player_name,
                        stat_type=result.stat_type,
                        line=result.line,
                        recommended_side=side,
                        edge=result.ev,
                        confidence=result.confidence,
                        market_prob=result.market_prob,
                        fair_prob=result.fair_prob,
                        payout_multiplier=result.payout_multiplier,
                        site=site,
                        stake=result.suggested_stake,
                        message=f"+EV Alert: {result.player_name} {side} {result.line:g} {result.stat_type}",
                    )
                )

        return alerts

    def _map_side(self, evaluator_side: str, site: str) -> str:
        """Map evaluator side terminology to notification side.

        Args:
            evaluator_side: Side from evaluator (More, Less, Higher, Lower).
            site: Site name.

        Returns:
            Mapped side (OVER, UNDER, HIGHER, LOWER).
        """
        side_lower = evaluator_side.lower()

        if site == "underdog":
            if side_lower in ("higher", "more"):
                return "HIGHER"
            return "LOWER"
        else:
            # PrizePicks, FanDuel, DraftKings use Over/Under
            if side_lower in ("more", "over"):
                return "OVER"
            return "UNDER"

    def set_thresholds(self, min_ev: float, min_confidence: float) -> None:
        """Update notification thresholds.

        Args:
            min_ev: New minimum EV threshold.
            min_confidence: New minimum confidence threshold.
        """
        self._min_ev = min_ev
        self._min_confidence = min_confidence

    def get_stats(self) -> dict:
        """Get notification queue statistics.

        Returns:
            Dict with pending, sent, and failed counts.
        """
        if self._service.queue:
            return self._service.queue.get_stats()
        return {"pending": 0, "sent": 0, "failed": 0}


def send_ev_alerts_from_pipeline(
    playable_df,
    site: str = "PrizePicks",
    config: Optional[NotificationConfig] = None,
    use_queue: bool = True,
) -> list[EVAlert]:
    """Send EV alerts from pipeline results.

    Args:
        playable_df: DataFrame from AnalysisPipeline.playable_df
        site: Site name for alerts
        config: Notification config
        use_queue: Whether to queue alerts (True) or send immediately (False)

    Returns:
        List of created EVAlert objects
    """
    alerts = create_from_pipeline_result(playable_df, site, config)

    if not alerts:
        return []

    service = NotificationService(config)

    sent = []
    for alert in alerts:
        if use_queue and service.queue:
            service.queue.enqueue(alert)
            sent.append(alert)
        else:
            results = service.sender.send_all_sync(alert)
            if any(results.values()):
                sent.append(alert)

    return sent


def send_line_movement_alerts(
    line_changes: list[dict],
    site: str = "PrizePicks",
    config: Optional[NotificationConfig] = None,
) -> int:
    """Send alerts for significant line movements.

    Args:
        line_changes: List of dicts with keys:
            - player_name: str
            - stat_type: str
            - previous_line: float
            - new_line: float
            - market_source: str
        site: Site name for alerts
        config: Notification config

    Returns:
        Number of alerts sent
    """
    config = config or NotificationConfig.from_env()
    service = NotificationService(config)
    count = 0

    for change in line_changes:
        success = service.send_line_movement_alert(
            player_name=change["player_name"],
            stat_type=change["stat_type"],
            previous_line=change["previous_line"],
            new_line=change["new_line"],
            site=site,
            market_source=change.get("market_source", ""),
        )
        if success:
            count += 1

    return count


def send_daily_summary(
    total_opportunities: int,
    top_plays: list[dict],
    ev_breakdown: dict,
    sport: str = "NBA",
    config: Optional[NotificationConfig] = None,
) -> bool:
    """Send daily summary alert.

    Args:
        total_opportunities: Total number of +EV opportunities found
        top_plays: List of top play dicts with player, side, line, edge
        ev_breakdown: Dict mapping site -> count of plays
        sport: Sport league (default NBA)
        config: Notification config

    Returns:
        True if alert was queued/sent
    """
    service = NotificationService(config)
    return service.send_summary_alert(
        total_opportunities=total_opportunities,
        top_plays=top_plays,
        ev_breakdown=ev_breakdown,
        sport=sport,
    )
