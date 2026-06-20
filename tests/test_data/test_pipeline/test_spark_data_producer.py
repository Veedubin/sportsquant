"""Unit tests for spark_data_producer.py (migrated from Sports-Platform)."""
# pylint: disable=protected-access,attribute-defined-outside-init

from unittest.mock import MagicMock, patch

from quantitative_sports.data.pipeline.spark_data_producer import (
    SparkDataProducer,
    start_metrics_server,
)
from quantitative_sports.data.pipeline.producer_config import NBA_TOPIC_MAPPINGS, ProducerSettings


class TestSparkDataProducer:
    """Tests for SparkDataProducer class."""

    def test_init_default(self):
        """Test producer initialization with defaults."""
        producer = SparkDataProducer()
        assert producer._settings is not None
        assert producer._consumer is None
        assert producer._producer is None
        assert producer._shutdown_event is not None

    def test_init_custom_settings(self):
        """Test producer initialization with custom settings."""
        settings = ProducerSettings(kafka_bootstrap_servers="custom:9092")
        producer = SparkDataProducer(settings)
        assert producer._settings.kafka_bootstrap_servers == "custom:9092"

    def test_process_message_valid_json(self):
        """Test processing valid JSON message."""
        producer = SparkDataProducer()
        mapping = NBA_TOPIC_MAPPINGS[0]
        with patch(
            "quantitative_sports.data.pipeline.spark_data_producer.get_transform_function"
        ) as mock_transform:
            mock_transform.return_value = lambda x: {
                "player_stats": [{"id": 1}],
                "record_count": 1,
            }
            result = producer._process_message('{"key": "value"}', mapping)
            assert result is not None
            assert len(result) == 1

    def test_process_message_invalid_json(self):
        """Test processing invalid JSON message."""
        producer = SparkDataProducer()
        mapping = NBA_TOPIC_MAPPINGS[0]
        result = producer._process_message("invalid json", mapping)
        assert result is None

    def test_process_message_missing_transform(self):
        """Test processing with missing transform function."""
        producer = SparkDataProducer()
        mapping = NBA_TOPIC_MAPPINGS[0]
        with patch(
            "quantitative_sports.data.pipeline.spark_data_producer.get_transform_function"
        ) as mock_transform:
            mock_transform.return_value = None
            result = producer._process_message('{"key": "value"}', mapping)
            assert result is None

    def test_process_message_empty_result(self):
        """Test processing with empty transform result."""
        producer = SparkDataProducer()
        mapping = NBA_TOPIC_MAPPINGS[0]
        with patch(
            "quantitative_sports.data.pipeline.spark_data_producer.get_transform_function"
        ) as mock_transform:
            mock_transform.return_value = lambda x: {"record_count": 0}
            result = producer._process_message('{"key": "value"}', mapping)
            assert result is None

    def test_publish_records_empty(self):
        """Test publishing empty records returns 0."""
        producer = SparkDataProducer()
        with patch("quantitative_sports.data.pipeline.spark_data_producer.create_kafka_producer"):
            mock_producer = MagicMock()
            result = producer._publish_records(mock_producer, [], "test-topic")
            assert result == 0

    def test_publish_records_success(self):
        """Test publishing records successfully."""
        producer = SparkDataProducer()
        with patch("quantitative_sports.data.pipeline.spark_data_producer.create_kafka_producer"):
            mock_producer = MagicMock()
            mock_producer.send.return_value.get.return_value = MagicMock()

            records = [{"id": 1}, {"id": 2}]
            result = producer._publish_records(mock_producer, records, "test-topic")
            assert result == 2
            assert mock_producer.send.call_count == 2

    def test_publish_records_counts_all(self):
        """Test publishing records counts all (including errors)."""
        producer = SparkDataProducer()
        with patch("quantitative_sports.data.pipeline.spark_data_producer.create_kafka_producer"):
            mock_producer = MagicMock()
            mock_producer.send.return_value.get.side_effect = [
                MagicMock(),
                Exception("error"),
                MagicMock(),
            ]

            records = [{"id": 1}, {"id": 2}, {"id": 3}]
            result = producer._publish_records(mock_producer, records, "test-topic")
            # All 3 records are attempted, errors increment counter
            assert result == 3


class TestStartMetricsServer:
    """Tests for start_metrics_server function."""

    def test_start_metrics_server_exists(self):
        """Test start_metrics_server function exists."""
        assert start_metrics_server is not None
        assert callable(start_metrics_server)


class TestMain:
    """Tests for main entry point (mocked)."""

    def test_main_entry_point(self):
        """Test main function exists and is callable."""
        from quantitative_sports.data.pipeline import spark_data_producer

        assert hasattr(spark_data_producer, "main")
        assert callable(spark_data_producer.main)

    def test_metrics_server_exists(self):
        """Test metrics server function exists."""
        from quantitative_sports.data.pipeline import spark_data_producer

        assert hasattr(spark_data_producer, "start_metrics_server")
        assert callable(spark_data_producer.start_metrics_server)
