"""Unit tests for producer_config.py (migrated from Sports-Platform)."""
# pylint: disable=wrong-import-position

import os
from unittest.mock import patch

from sportsquant.data.pipeline.producer_config import (
    TopicMapping,
    NBA_TOPIC_MAPPINGS,
    ProducerSettings,
    create_producer_config,
    create_kafka_producer,
    transform_player_stats,
    transform_game_results,
    transform_schedule_updates,
    get_transform_function,
)


class TestTopicMapping:
    """Tests for TopicMapping dataclass."""

    def test_topic_mapping_creation(self):
        """Test TopicMapping creation."""
        mapping = TopicMapping(
            source_topic="test-source",
            spark_topic="test-spark",
            transform_func="test_transform",
        )
        assert mapping.source_topic == "test-source"
        assert mapping.spark_topic == "test-spark"
        assert mapping.transform_func == "test_transform"


class TestNBATopicMappings:
    """Tests for NBA topic mappings."""

    def test_nba_mappings_exist(self):
        """Test that NBA topic mappings are defined."""
        assert len(NBA_TOPIC_MAPPINGS) == 3

    def test_player_logs_mapping(self):
        """Test player logs mapping configuration."""
        mapping = NBA_TOPIC_MAPPINGS[0]
        assert mapping.source_topic == "nba-player-logs"
        assert mapping.spark_topic == "sports-analytics-player-stats"
        assert mapping.transform_func == "transform_player_stats"

    def test_games_mapping(self):
        """Test games mapping configuration."""
        mapping = NBA_TOPIC_MAPPINGS[1]
        assert mapping.source_topic == "nba-games"
        assert mapping.spark_topic == "sports-analytics-game-results"
        assert mapping.transform_func == "transform_game_results"

    def test_schedule_mapping(self):
        """Test schedule mapping configuration."""
        mapping = NBA_TOPIC_MAPPINGS[2]
        assert mapping.source_topic == "nba-schedule"
        assert mapping.spark_topic == "sports-analytics-schedule-updates"
        assert mapping.transform_func == "transform_schedule_updates"


class TestProducerSettings:
    """Tests for ProducerSettings dataclass."""

    def test_default_settings(self):
        """Test default producer settings."""
        settings = ProducerSettings(kafka_bootstrap_servers="localhost:9092")
        assert settings.batch_size == 100
        assert settings.linger_ms == 50
        assert settings.buffer_memory == 33554432
        assert settings.acks == "all"
        assert settings.retries == 3
        assert settings.compression_type == "gzip"

    def test_custom_settings(self):
        """Test custom producer settings."""
        settings = ProducerSettings(
            kafka_bootstrap_servers="kafka:9092",
            batch_size=200,
            linger_ms=100,
        )
        assert settings.batch_size == 200
        assert settings.linger_ms == 100

    @patch.dict(
        os.environ,
        {
            "KAFKA_BOOTSTRAP_SERVERS": "custom-kafka:9092",
            "PRODUCER_BATCH_SIZE": "250",
        },
    )
    def test_from_env(self):
        """Test creating settings from environment variables."""
        settings = ProducerSettings.from_env()
        assert settings.kafka_bootstrap_servers == "custom-kafka:9092"
        assert settings.batch_size == 250

    def test_from_env_defaults(self):
        """Test default environment values."""
        with patch.dict(os.environ, {}, clear=True):
            settings = ProducerSettings.from_env()
            assert "sports-cluster-kafka-bootstrap:9092" in settings.kafka_bootstrap_servers
            assert settings.batch_size == 100


class TestCreateProducerConfig:
    """Tests for create_producer_config function."""

    def test_create_producer_config(self):
        """Test creating producer configuration dictionary."""
        settings = ProducerSettings(kafka_bootstrap_servers="localhost:9092")
        config = create_producer_config(settings)
        assert config["bootstrap_servers"] == "localhost:9092"
        assert config["acks"] == "all"
        assert config["retries"] == 3
        assert config["batch_size"] == 100


class TestTransformFunctions:
    """Tests for data transformation functions."""

    def test_transform_player_stats_with_rowset(self, sample_player_stats):
        """Test transforming player stats with rowSet."""
        result = transform_player_stats(sample_player_stats)
        assert "player_stats" in result
        assert "record_count" in result
        assert result["record_count"] == 2

    def test_transform_player_stats_empty_rowset(self):
        """Test transforming empty player stats rowset."""
        # When rowSet is empty, it falls back to returning the dict as-is
        result = transform_player_stats({"rowSet": [], "headers": []})
        # Empty lists fall through to else branch which returns [data] for dicts
        assert "record_count" in result

    def test_transform_player_stats_fallback(self):
        """Test transforming dict without rowSet."""
        result = transform_player_stats({"key": "value"})
        assert result["record_count"] == 1

    def test_transform_game_results_with_rowset(self, sample_game_results):
        """Test transforming game results with rowSet."""
        result = transform_game_results(sample_game_results)
        assert "game_results" in result
        assert "record_count" in result
        assert result["record_count"] == 2

    def test_transform_game_results_empty_rowset(self):
        """Test transforming empty game results rowset."""
        # When rowSet is empty, it falls back to returning the dict as-is
        result = transform_game_results({"rowSet": [], "headers": []})
        # Empty lists fall through to the else branch
        assert "record_count" in result

    def test_transform_schedule_updates_with_games(self, sample_schedule_updates):
        """Test transforming schedule updates with games list."""
        result = transform_schedule_updates(sample_schedule_updates)
        assert "schedule_updates" in result
        assert "record_count" in result
        assert result["record_count"] == 2

    def test_transform_schedule_updates_list(self):
        """Test transforming schedule as list."""
        games = [{"game_id": "1"}, {"game_id": "2"}]
        result = transform_schedule_updates({"games": games})
        assert result["record_count"] == 2

    def test_transform_schedule_updates_empty(self):
        """Test transforming empty schedule."""
        result = transform_schedule_updates({"games": []})
        assert result["record_count"] == 0


class TestGetTransformFunction:
    """Tests for get_transform_function function."""

    def test_get_transform_player_stats(self):
        """Test getting player stats transform function."""
        func = get_transform_function("transform_player_stats")
        assert func is not None
        assert callable(func)

    def test_get_transform_game_results(self):
        """Test getting game results transform function."""
        func = get_transform_function("transform_game_results")
        assert func is not None
        assert callable(func)

    def test_get_transform_schedule_updates(self):
        """Test getting schedule updates transform function."""
        func = get_transform_function("transform_schedule_updates")
        assert func is not None
        assert callable(func)

    def test_get_transform_nonexistent(self):
        """Test getting nonexistent transform function."""
        func = get_transform_function("nonexistent_transform")
        assert func is None


class TestCreateKafkaProducer:
    """Tests for create_kafka_producer function."""

    def test_create_kafka_producer_default(self):
        """Test creating Kafka producer with default settings."""
        with patch("sportsquant.data.pipeline.producer_config.KafkaProducer") as mock:
            create_kafka_producer()
            mock.assert_called_once()
            call_kwargs = mock.call_args[1]
            assert "bootstrap_servers" in call_kwargs

    def test_create_kafka_producer_custom(self):
        """Test creating Kafka producer with custom settings."""
        with patch("sportsquant.data.pipeline.producer_config.KafkaProducer") as mock:
            settings = ProducerSettings(kafka_bootstrap_servers="custom:9092")
            create_kafka_producer(settings)
            mock.assert_called_once()
            call_kwargs = mock.call_args[1]
            assert call_kwargs["bootstrap_servers"] == "custom:9092"
