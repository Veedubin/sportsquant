"""Unit tests for kafka_ignite_consumer.py (migrated from Sports-Platform)."""
# pylint: disable=protected-access,attribute-defined-outside-init

from unittest.mock import MagicMock

from sportsquant.data.pipeline.kafka_ignite_consumer import (
    ConsumerConfig,
    CacheManager,
    MessageRouter,
    _get_key_field_for_topic,
    KafkaIgniteConsumer,
    HealthCheckHandler,
)


class TestConsumerConfig:
    """Tests for ConsumerConfig dataclass."""

    def test_default_config(self):
        """Test default consumer configuration."""
        config = ConsumerConfig()
        assert config.kafka_bootstrap_servers == "kafka-cluster-kafka-bootstrap:9092"
        assert config.kafka_consumer_group == "kafka-ignite-consumer"
        assert config.batch_size == 100
        topics = config.kafka_topics
        assert len(topics) == 4 if topics else 0

    def test_custom_config(self):
        """Test custom consumer configuration."""
        config = ConsumerConfig(
            kafka_bootstrap_servers="custom-kafka:9092",
            batch_size=200,
        )
        assert config.kafka_bootstrap_servers == "custom-kafka:9092"
        assert config.batch_size == 200

    def test_topics_initialized(self):
        """Test that default topics are initialized."""
        config = ConsumerConfig()
        topics = config.kafka_topics
        assert topics and "nba-players" in topics
        assert "nba-games" in topics
        assert "nba-player-logs" in topics
        assert "nba-schedule" in topics


class TestCacheManager:
    """Tests for CacheManager class."""

    def test_init(self):
        """Test CacheManager initialization."""
        manager = CacheManager(host="localhost", port=10800)
        assert manager.host == "localhost"
        assert manager.port == 10800
        assert manager._client is None
        assert not manager._caches

    def test_get_cache_not_connected(self):
        """Test getting cache when not connected."""
        manager = CacheManager(host="localhost", port=10800)
        cache = manager.get_cache("test-cache")
        assert cache is None

    def test_write_batch_no_cache(self):
        """Test writing batch when cache doesn't exist."""
        manager = CacheManager(host="localhost", port=10800)
        result = manager.write_batch(
            cache_name="test-cache",
            entries=[("key1", {"value": 1})],
        )
        assert result == 0

    def test_write_no_cache(self):
        """Test writing single entry when cache doesn't exist."""
        manager = CacheManager(host="localhost", port=10800)
        result = manager.write(
            cache_name="test-cache",
            key="key1",
            value={"value": 1},
        )
        assert result is False

    def test_close_no_client(self):
        """Test closing when no client is connected."""
        manager = CacheManager(host="localhost", port=10800)
        # Should not raise an exception
        manager.close()


class TestMessageRouter:
    """Tests for MessageRouter class."""

    def setup_method(self):
        """Set up test fixtures."""
        self._cache_manager = MagicMock()
        self._router = MessageRouter(self._cache_manager)

    def test_get_cache_name_valid_topic(self):
        """Test getting cache name for valid topic."""
        cache_name = self._router.get_cache_name("nba-games")
        assert cache_name == "nba-games-cache"

    def test_get_cache_name_players(self):
        """Test getting cache name for players topic."""
        cache_name = self._router.get_cache_name("nba-players")
        assert cache_name == "nba-players-cache"

    def test_get_cache_name_player_logs(self):
        """Test getting cache name for player logs topic."""
        cache_name = self._router.get_cache_name("nba-player-logs")
        assert cache_name == "nba-player-stats"

    def test_get_cache_name_schedule(self):
        """Test getting cache name for schedule topic."""
        cache_name = self._router.get_cache_name("nba-schedule")
        assert cache_name == "nba-schedule-cache"

    def test_get_cache_name_unknown_topic(self):
        """Test getting cache name for unknown topic."""
        cache_name = self._router.get_cache_name("unknown-topic")
        assert cache_name is None

    def test_route_success(self):
        """Test routing message successfully."""
        self._cache_manager.write.return_value = True
        cache_name, success = self._router.route(
            topic="nba-games",
            key="game_123",
            value={"game_id": "game_123", "home_team": "Lakers"},
        )
        assert cache_name == "nba-games-cache"
        assert success is True

    def test_route_no_cache_configured(self):
        """Test routing message with no cache configured."""
        cache_name, success = self._router.route(
            topic="unknown-topic",
            key="key1",
            value={"data": "value"},
        )
        assert cache_name == ""
        assert success is False

    def test_route_generates_key(self):
        """Test routing generates key when not provided."""
        self._cache_manager.write.return_value = True
        _, success = self._router.route(
            topic="nba-games",
            key=None,
            value={"game_id": "game_123", "home_team": "Lakers"},
        )
        assert success is True
        self._cache_manager.write.assert_called_once()

    def test_generate_key_with_id_field(self):
        """Test key generation uses id field."""
        key = self._router._generate_key("nba-games", {"game_id": "game_123"})
        assert key == "nba-games:game_123"

    def test_generate_key_without_id_field(self):
        """Test key generation falls back to hash."""
        key = self._router._generate_key("nba-games", {"home_team": "Lakers"})
        assert key.startswith("nba-games:")


class TestGetKeyFieldForTopic:
    """Tests for _get_key_field_for_topic function."""

    def test_players_topic(self):
        """Test key field for players topic."""
        key_field = _get_key_field_for_topic("nba-players")
        assert key_field == "player_id"

    def test_games_topic(self):
        """Test key field for games topic."""
        key_field = _get_key_field_for_topic("nba-games")
        assert key_field == "game_id"

    def test_player_logs_topic(self):
        """Test key field for player logs topic."""
        key_field = _get_key_field_for_topic("nba-player-logs")
        assert key_field == "game_log_id"

    def test_schedule_topic(self):
        """Test key field for schedule topic."""
        key_field = _get_key_field_for_topic("nba-schedule")
        assert key_field == "game_id"

    def test_unknown_topic(self):
        """Test key field for unknown topic."""
        key_field = _get_key_field_for_topic("unknown")
        assert key_field is None


class TestKafkaIgniteConsumer:
    """Tests for KafkaIgniteConsumer class."""

    def test_init_default(self):
        """Test consumer initialization with defaults."""
        consumer = KafkaIgniteConsumer()
        assert consumer.config is not None
        assert consumer.cache_manager is None
        assert consumer.consumer is None
        assert consumer._running is False

    def test_init_custom_config(self):
        """Test consumer initialization with custom config."""
        config = ConsumerConfig(kafka_bootstrap_servers="custom:9092")
        consumer = KafkaIgniteConsumer(config)
        assert consumer.config.kafka_bootstrap_servers == "custom:9092"

    def test_stats_initialized(self):
        """Test stats dictionary is properly initialized."""
        consumer = KafkaIgniteConsumer()
        stats = consumer._stats
        assert stats["messages_consumed"] == 0
        assert stats["messages_written"] == 0
        assert stats["messages_failed"] == 0
        assert stats["batches_processed"] == 0

    def test_process_records_updates_stats(self):
        """Test processing records updates statistics."""
        consumer = KafkaIgniteConsumer()
        consumer.cache_manager = MagicMock()
        router = MessageRouter(consumer.cache_manager)

        # Create mock records
        mock_message = MagicMock()
        mock_message.key = "game_123"
        mock_message.value = {"game_id": "game_123"}

        mock_topic_partition = MagicMock()
        mock_topic_partition.topic = "nba-games"

        records = {mock_topic_partition: [mock_message]}  # type: ignore[dict-item]

        consumer._process_records(records, router)  # type: ignore[arg-type]

        stats = consumer._stats
        assert stats["messages_consumed"] == 1
        assert stats["messages_written"] == 1
        assert stats["messages_failed"] == 0
        assert stats["batches_processed"] == 1


class TestHealthCheckHandler:
    """Tests for HealthCheckHandler (basic)."""

    def test_handler_class_exists(self):
        """Test HealthCheckHandler class exists."""
        assert HealthCheckHandler

    def test_health_path_exists(self):
        """Test HealthCheckHandler has do_GET method."""
        handler = HealthCheckHandler.__dict__.get("do_GET")
        assert handler is not None


class TestMain:
    """Tests for main entry point (mocked)."""

    def test_main_entry_point(self):
        """Test main function exists."""
        from sportsquant.data.pipeline import kafka_ignite_consumer

        assert hasattr(kafka_ignite_consumer, "main")
        assert callable(kafka_ignite_consumer.main)
