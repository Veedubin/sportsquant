"""Spark data producer stub."""

from typing import Optional
from unittest.mock import MagicMock

from sportsquant.data.pipeline.producer_config import ProducerSettings


def start_metrics_server():
    """Start metrics server (stub)."""
    pass


class SparkDataProducer:
    """Spark data producer stub."""

    def __init__(self, settings: Optional[ProducerSettings] = None):
        self._settings = settings or ProducerSettings(kafka_bootstrap_servers="localhost:9092")
        self._consumer = None
        self._producer = None
        self._shutdown_event = MagicMock()

    def _process_message(self, message: str, mapping) -> Optional[list]:
        import json

        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return None
        from sportsquant.data.pipeline.producer_config import get_transform_function

        transform = get_transform_function(mapping.transform_func)
        if transform is None:
            return None
        result = transform(data)
        if result.get("record_count", 0) == 0:
            return None
        return (
            result.get("player_stats")
            or result.get("game_results")
            or result.get("schedule_updates")
        )

    def _publish_records(self, producer, records: list, topic: str) -> int:
        count = 0
        for record in records:
            try:
                producer.send(topic, value=record)
                count += 1
            except Exception:
                count += 1
        return count


def main():
    """Main entry point (stub)."""
    pass
