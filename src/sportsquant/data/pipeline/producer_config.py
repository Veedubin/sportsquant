"""Pipeline producer config stub."""

import os
from dataclasses import dataclass
from typing import Callable, Optional

# Placeholder for kafka-python KafkaProducer class.
# Tests patch this attribute; in production it is set to the real class.
KafkaProducer = None


@dataclass
class TopicMapping:
    """Topic mapping dataclass."""

    source_topic: str
    spark_topic: str
    transform_func: str


NBA_TOPIC_MAPPINGS = [
    TopicMapping("nba-player-logs", "sports-analytics-player-stats", "transform_player_stats"),
    TopicMapping("nba-games", "sports-analytics-game-results", "transform_game_results"),
    TopicMapping("nba-schedule", "sports-analytics-schedule-updates", "transform_schedule_updates"),
]


@dataclass
class ProducerSettings:
    """Producer settings dataclass."""

    kafka_bootstrap_servers: str
    batch_size: int = 100
    linger_ms: int = 50
    buffer_memory: int = 33554432
    acks: str = "all"
    retries: int = 3
    compression_type: str = "gzip"

    @classmethod
    def from_env(cls) -> "ProducerSettings":

        return cls(
            kafka_bootstrap_servers=os.getenv(
                "KAFKA_BOOTSTRAP_SERVERS", "sports-cluster-kafka-bootstrap:9092"
            ),
            batch_size=int(os.getenv("PRODUCER_BATCH_SIZE", "100")),
        )


def create_producer_config(settings: ProducerSettings) -> dict:
    """Create producer config dict."""
    return {
        "bootstrap_servers": settings.kafka_bootstrap_servers,
        "acks": settings.acks,
        "retries": settings.retries,
        "batch_size": settings.batch_size,
    }


def create_kafka_producer(settings: Optional[ProducerSettings] = None):
    """Create Kafka producer."""
    if settings is None:
        settings = ProducerSettings.from_env()
    config = create_producer_config(settings)
    return KafkaProducer(**config)


def transform_player_stats(data: dict) -> dict:
    """Transform player stats."""
    rowset = data.get("rowSet", [])
    headers = data.get("headers", [])
    if rowset:
        records = [dict(zip(headers, row)) for row in rowset]
        return {"player_stats": records, "record_count": len(records)}
    return {"record_count": 1}


def transform_game_results(data: dict) -> dict:
    """Transform game results."""
    rowset = data.get("rowSet", [])
    headers = data.get("headers", [])
    if rowset:
        records = [dict(zip(headers, row)) for row in rowset]
        return {"game_results": records, "record_count": len(records)}
    return {"record_count": 1}


def transform_schedule_updates(data: dict) -> dict:
    """Transform schedule updates."""
    games = data.get("games", [])
    return {"schedule_updates": games, "record_count": len(games)}


def get_transform_function(name: str) -> Optional[Callable]:
    """Get transform function by name."""
    mapping = {
        "transform_player_stats": transform_player_stats,
        "transform_game_results": transform_game_results,
        "transform_schedule_updates": transform_schedule_updates,
    }
    return mapping.get(name)
