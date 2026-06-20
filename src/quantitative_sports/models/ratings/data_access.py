"""
Data Access Layer for Sports Platform Feature Engineering

This module provides a unified interface for accessing data from:
- TimescaleDB: Player statistics and game data
- Apache Ignite: Distributed caching for player indices, opponent strength, features
- Kafka: Real-time player stats and schedule topics

Data Sources:
- Kafka topic 'sports-analytics-player-stats': Real-time player statistics
- Kafka topic 'sports-schedules': Game schedules (compacted topic)
- TimescaleDB: Historical player stats, game data

Cache Layer (Apache Ignite):
- Player indices: Cache key format 'player:{player_id}'
- Opponent strength: Cache key format 'opponent_strength:{team_abbr}'
- Feature storage: Cache key format 'features:{game_id}:{player_id}'

Usage:
    >>> from quantitative_sports.models.ratings.data_access import DataAccess
    >>> data_access = DataAccess()
    >>> player_stats = await data_access.get_player_stats("lebron-james-2544")
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

import pandas as pd

try:
    from pyignite import Client as _IgniteClient

    IGNITE_AVAILABLE = True
except ImportError:
    _IgniteClient = None
    IGNITE_AVAILABLE = False

IgniteClientType = Optional[_IgniteClient]

try:
    import psycopg2 as _psycopg2
    from psycopg2 import Error as _psycopg2_Error

    PSYCOPG2_AVAILABLE = True
except ImportError:
    _psycopg2 = None
    _psycopg2_Error = None
    PSYCOPG2_AVAILABLE = False

try:
    from pyignite import Client as _IgniteClient

    IGNITE_AVAILABLE = True
except ImportError:
    _IgniteClient = None
    IGNITE_AVAILABLE = False

try:
    import psycopg2 as _psycopg2
    from psycopg2 import Error as _psycopg2_Error

    PSYCOPG2_AVAILABLE = True
except ImportError:
    _psycopg2 = None
    _psycopg2_Error = None
    PSYCOPG2_AVAILABLE = False

try:
    from confluent_kafka import Consumer

    KAFKA_AVAILABLE = True
except ImportError:
    Consumer = None
    KAFKA_AVAILABLE = False

_IgniteClientType = Any if _IgniteClient is None else _IgniteClient


@dataclass(frozen=True)
class DataAccessConfig:
    """Configuration for data access layer."""

    ignite_host: str = "sports-ignite"
    ignite_port: int = 10800
    kafka_bootstrap_servers: str = "sports-cluster-kafka-bootstrap:9092"
    stats_topic: str = "sports-analytics-player-stats"
    schedule_topic: str = "sports-schedules"
    timescale_dsn: str = "postgresql://postgres:postgres@timescaledb:5432/sports_analytics"


class IgniteCache:
    """Apache Ignite cache client for distributed caching.

    Replaces Redis for:
    - Player indices caching
    - Opponent strength caching
    - Feature storage and retrieval
    """

    def __init__(self, config: DataAccessConfig | None = None) -> None:
        """Initialize Ignite cache client.

        Args:
            config: Data access configuration.
        """
        self.config = config or DataAccessConfig()
        self._client: Any = None
        if IGNITE_AVAILABLE:
            pass  # Delay connection until needed

    def connect(self) -> None:
        """Establish connection to Apache Ignite cluster."""
        if not IGNITE_AVAILABLE:
            return
        if self._client is None and _IgniteClient:
            self._client = _IgniteClient(host=self.config.ignite_host, port=self.config.ignite_port)
            self._client.connect()

    def close(self) -> None:
        """Close Ignite connection."""
        if self._client:
            self._client.close()
            self._client = None

    def get(self, key: str) -> Any:
        """Get value from cache.

        Args:
            key: Cache key.

        Returns:
            Cached value or None if not found.
        """
        if not IGNITE_AVAILABLE:
            return None
        self.connect()
        cache = self._client.get_or_create_cache("sports_features")
        try:
            value = cache.get(key)
            if value:
                return json.loads(value)
            return None
        except (TypeError, ValueError):
            return None

    def put(self, key: str, value: Any, _ttl_seconds: int = 3600) -> None:
        """Put value in cache.

        Args:
            key: Cache key.
            value: Value to cache (will be JSON serialized).
            ttl_seconds: Time-to-live in seconds (reserved for future use with
                cache implementations that support TTL expiration).
        """
        if not IGNITE_AVAILABLE:
            return
        self.connect()
        cache = self._client.get_or_create_cache("sports_features")
        cache.put(key, json.dumps(value))

    def get_player_index(self, player_id: str) -> dict[str, Any] | None:
        """Get player index from cache.

        Args:
            player_id: Player identifier.

        Returns:
            Player index dictionary or None if not found.
        """
        return self.get(f"player:{player_id}")

    def put_player_index(self, player_id: str, index_data: dict[str, Any]) -> None:
        """Store player index in cache.

        Args:
            player_id: Player identifier.
            index_data: Player index data.
        """
        self.put(f"player:{player_id}", index_data)

    def get_opponent_strength(self, team_abbr: str) -> dict[str, float] | None:
        """Get opponent strength ratings from cache.

        Args:
            team_abbr: Team abbreviation.

        Returns:
            Opponent strength dictionary or None if not found.
        """
        return self.get(f"opponent_strength:{team_abbr}")

    def put_opponent_strength(self, team_abbr: str, strength_data: dict[str, float]) -> None:
        """Store opponent strength ratings in cache.

        Args:
            team_abbr: Team abbreviation.
            strength_data: Strength ratings data.
        """
        self.put(f"opponent_strength:{team_abbr}", strength_data)

    def get_features(self, game_id: str, player_id: str) -> dict[str, Any] | None:
        """Get computed features from cache.

        Args:
            game_id: Game identifier.
            player_id: Player identifier.

        Returns:
            Feature dictionary or None if not found.
        """
        return self.get(f"features:{game_id}:{player_id}")

    def put_features(self, game_id: str, player_id: str, features: dict[str, Any]) -> None:
        """Store computed features in cache.

        Args:
            game_id: Game identifier.
            player_id: Player identifier.
            features: Computed feature values.
        """
        self.put(f"features:{game_id}:{player_id}", features)


class TimescaleDBClient:
    """TimescaleDB client for historical player statistics.

    Reads player stats and game data from TimescaleDB tables.
    """

    def __init__(self, config: DataAccessConfig | None = None) -> None:
        """Initialize TimescaleDB client.

        Args:
            config: Data access configuration.
        """
        self.config = config or DataAccessConfig()
        self._connection = None

    def connect(self) -> Any:
        """Establish connection to TimescaleDB."""
        if not PSYCOPG2_AVAILABLE:
            return None
        try:
            if self._connection is None or (
                self._connection is not None and self._connection.closed
            ):
                assert _psycopg2 is not None
                self._connection = _psycopg2.connect(self.config.timescale_dsn)
            return self._connection
        except ImportError:
            return None
        try:
            if self._connection is None or (
                self._connection is not None and self._connection.closed
            ):
                self._connection = _psycopg2.connect(self.config.timescale_dsn)
            return self._connection
        except ImportError:
            return None

    def close(self) -> None:
        """Close database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None

    def get_player_stats(
        self,
        player_id: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100,
    ) -> pd.DataFrame:
        """Fetch player statistics from TimescaleDB.

        Args:
            player_id: Player identifier.
            start_date: Start date for stats range.
            end_date: End date for stats range.
            limit: Maximum number of records.

        Returns:
            DataFrame with player statistics.
        """
        conn = self.connect()
        if conn is None:
            return pd.DataFrame()

        try:
            query = """
                SELECT * FROM player_stats
                WHERE player_id = %s
            """
            params: list[Any] = [player_id]

            if start_date:
                query += " AND game_date >= %s"
                params.append(start_date)
            if end_date:
                query += " AND game_date <= %s"
                params.append(end_date)

            query += " ORDER BY game_date DESC LIMIT %s"
            params.append(limit)

            return pd.read_sql(query, conn, params=params)
        except (_psycopg2_Error or Exception, pd.errors.DatabaseError):
            return pd.DataFrame()

    def get_game_data(
        self,
        game_id: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100,
    ) -> pd.DataFrame:
        """Fetch game data from TimescaleDB.

        Args:
            game_id: Specific game ID to fetch.
            start_date: Start date for games range.
            end_date: End date for games range.
            limit: Maximum number of records.

        Returns:
            DataFrame with game data.
        """
        conn = self.connect()
        if conn is None:
            return pd.DataFrame()

        try:
            query = "SELECT * FROM games WHERE 1=1"
            params = []

            if game_id:
                query += " AND game_id = %s"
                params.append(game_id)
            if start_date:
                query += " AND game_date >= %s"
                params.append(start_date)
            if end_date:
                query += " AND game_date <= %s"
                params.append(end_date)

            query += " ORDER BY game_date DESC LIMIT %s"
            params.append(limit)

            return pd.read_sql(query, conn, params=params)
        except (_psycopg2_Error or Exception, pd.errors.DatabaseError):
            return pd.DataFrame()

    def get_team_ratings(self, team_abbr: str | None = None) -> pd.DataFrame:
        """Fetch team ratings from TimescaleDB.

        Args:
            team_abbr: Specific team to fetch ratings for.

        Returns:
            DataFrame with team ratings.
        """
        conn = self.connect()
        if conn is None:
            return pd.DataFrame()

        try:
            query = "SELECT * FROM team_ratings"
            params = []

            if team_abbr:
                query += " WHERE team_abbr = %s"
                params.append(team_abbr)

            return pd.read_sql(query, conn, params=params)
        except (_psycopg2_Error or Exception, pd.errors.DatabaseError):
            return pd.DataFrame()


class KafkaConsumer:
    """Kafka consumer for real-time player stats and schedules.

    Reads from:
    - sports-analytics-player-stats: Real-time player statistics
    - sports-schedules: Game schedules (compacted topic)
    """

    def __init__(self, config: DataAccessConfig | None = None) -> None:
        """Initialize Kafka consumer.

        Args:
            config: Data access configuration.
        """
        self.config = config or DataAccessConfig()
        self._consumer = None

    def _get_consumer(self) -> Any:
        """Get or create Kafka consumer."""
        if not KAFKA_AVAILABLE or Consumer is None:
            return None
        if self._consumer is None:
            self._consumer = Consumer(
                {
                    "bootstrap.servers": self.config.kafka_bootstrap_servers,
                    "group.id": "features-consumer",
                    "auto.offset.reset": "earliest",
                }
            )
        return self._consumer

    def consume_stats(self, timeout_seconds: float = 1.0) -> list[dict[str, Any]]:
        """Consume player stats from Kafka topic.

        Args:
            timeout_seconds: Consumer timeout.

        Returns:
            List of player stats dictionaries.
        """
        consumer = self._get_consumer()
        if consumer is None:
            return []

        consumer.subscribe([self.config.stats_topic])

        messages = []
        try:
            while len(messages) < 100:
                msg = consumer.consume(timeout=timeout_seconds)
                if not msg:
                    break
                for m in msg:
                    if m.value():
                        try:
                            stats = json.loads(m.value())
                            messages.append(stats)
                        except json.JSONDecodeError:
                            continue
        except Exception:  # pylint: disable=broad-exception-caught
            pass

        return messages

    def consume_schedules(self, timeout_seconds: float = 1.0) -> list[dict[str, Any]]:
        """Consume game schedules from Kafka topic.

        Args:
            timeout_seconds: Consumer timeout.

        Returns:
            List of schedule dictionaries.
        """
        consumer = self._get_consumer()
        if consumer is None:
            return []

        consumer.subscribe([self.config.schedule_topic])

        messages = []
        try:
            while len(messages) < 100:
                msg = consumer.consume(timeout=timeout_seconds)
                if not msg:
                    break
                for m in msg:
                    if m.value():
                        try:
                            schedule = json.loads(m.value())
                            messages.append(schedule)
                        except json.JSONDecodeError:
                            continue
        except Exception:  # pylint: disable=broad-exception-caught
            pass

        return messages

    def close(self) -> None:
        """Close Kafka consumer."""
        if self._consumer:
            self._consumer.close()
            self._consumer = None


class DataAccess:
    """Unified data access layer for feature engineering.

    Combines:
    - Apache Ignite for caching
    - TimescaleDB for historical data
    - Kafka for real-time data
    """

    def __init__(self, config: DataAccessConfig | None = None) -> None:
        """Initialize data access layer.

        Args:
            config: Data access configuration.
        """
        self.config = config or DataAccessConfig()
        self.ignite = IgniteCache(self.config)
        self.timescale = TimescaleDBClient(self.config)
        self.kafka = KafkaConsumer(self.config)

    def get_player_data(
        self,
        player_id: str,
        use_cache: bool = True,
        use_realtime: bool = False,
    ) -> dict[str, Any]:
        """Get complete player data from all sources.

        Args:
            player_id: Player identifier.
            use_cache: Whether to check cache first.
            use_realtime: Whether to fetch real-time data from Kafka.

        Returns:
            Combined player data dictionary.
        """
        result: dict[str, Any] = {}

        if use_cache:
            cached = self.ignite.get_player_index(player_id)
            if cached:
                result["cached"] = cached

        if use_realtime:
            stats = self.kafka.consume_stats()
            for stat in stats:
                if stat.get("player_id") == player_id:
                    result["realtime"] = stat
                    break

        historical = self.timescale.get_player_stats(player_id)
        if not historical.empty:
            result["historical"] = historical.to_dict(orient="records")

        return result

    def get_game_data(
        self,
        game_id: str | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Get complete game data from all sources.

        Args:
            game_id: Game identifier.
            use_cache: Whether to check cache first.

        Returns:
            Combined game data dictionary.
        """
        result: dict[str, Any] = {}

        if use_cache and game_id:
            cached = self.ignite.get(f"game:{game_id}")
            if cached:
                result["cached"] = cached

        historical = self.timescale.get_game_data(game_id=game_id)
        if not historical.empty:
            result["historical"] = historical.to_dict(orient="records")

        if game_id:
            schedules = self.kafka.consume_schedules()
            for schedule in schedules:
                if schedule.get("game_id") == game_id:
                    result["schedule"] = schedule
                    break

        return result

    def store_features(
        self,
        game_id: str,
        player_id: str,
        features: dict[str, Any],
    ) -> None:
        """Store computed features in cache.

        Args:
            game_id: Game identifier.
            player_id: Player identifier.
            features: Computed feature values.
        """
        self.ignite.put_features(game_id, player_id, features)

    def get_features(
        self,
        game_id: str,
        player_id: str,
    ) -> dict[str, Any] | None:
        """Retrieve stored features from cache.

        Args:
            game_id: Game identifier.
            player_id: Player identifier.

        Returns:
            Feature dictionary or None if not found.
        """
        return self.ignite.get_features(game_id, player_id)

    def close(self) -> None:
        """Close all connections."""
        self.ignite.close()
        self.timescale.close()
        self.kafka.close()
