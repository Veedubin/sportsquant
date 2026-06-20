"""Asyncpg connection pool wrapper for Quant-Sports TimescaleDB integration.

Provides a lazy-initialised, thread-safe singleton pool plus a ``DBConfig``
dataclass sourced from environment variables or a DSN string.

Usage::

    from quantitative_sports.infra.db.connection import get_pool, health_check

    async def main():
        pool = await get_pool()
        rows = await pool.fetch("SELECT * FROM odds_ticks LIMIT 10")
        status = await health_check(pool)
        await pool.close()

The module imports cleanly even when ``asyncpg`` is not installed — the
import is deferred to first use so that the base package can be imported
in environments that only need the config layer.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

__all__ = [
    "DBConfig",
    "DatabasePool",
    "get_pool",
    "reset_pool",
    "health_check",
]


# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────


class DBConfig(BaseSettings):
    """TimescaleDB connection configuration.

    Values are sourced from environment variables with the ``QUANT_SPORTS_DB_``
    prefix, or from an explicit DSN string passed to :meth:`from_dsn`.

    Attributes:
        host: Database hostname.
        port: Database port.
        user: Database user.
        password: Database password.
        database: Database name.
    """

    host: str = "timescaledb"
    port: int = 5432
    user: str = "quantitative_sports"
    password: str = "quantitative_sports"
    database: str = "quantitative_sports"

    model_config = {"env_prefix": "QUANT_SPORTS_DB_"}  # type: ignore[typed-dict-unknown]

    @classmethod
    def from_env(cls) -> DBConfig:
        """Construct configuration from environment variables.

        Uses ``pydantic-settings`` env prefix ``QUANT_SPORTS_DB_`` so that
        ``QUANT_SPORTS_DB_HOST`` maps to :attr:`host`, etc.

        Returns:
            A fully populated :class:`DBConfig` instance.
        """
        return cls()

    @classmethod
    def from_dsn(cls, dsn: str) -> DBConfig:
        """Construct configuration from a PostgreSQL DSN string.

        The DSN format is::

            postgresql://user:password@host:port/database

        Args:
            dsn: A libpq-compatible connection string.

        Returns:
            A :class:`DBConfig` populated from the DSN components.
        """
        # Minimal DSN parsing — we avoid importing urllib at module level
        # so this stays lightweight. Handles standard postgresql:// DSNs.
        from urllib.parse import urlparse

        parsed = urlparse(dsn)
        return cls(
            host=parsed.hostname or "timescaledb",
            port=parsed.port or 5432,
            user=parsed.username or "quantitative_sports",
            password=parsed.password or "quantitative_sports",
            database=parsed.path.lstrip("/") or "quantitative_sports",
        )

    def to_dsn(self) -> str:
        """Render the configuration as a PostgreSQL DSN string.

        Returns:
            A ``postgresql://`` connection string suitable for asyncpg.
        """
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


# ──────────────────────────────────────────────
# Connection Pool
# ──────────────────────────────────────────────


class DatabasePool:
    """Async context manager wrapping an :mod:`asyncpg` connection pool.

    The pool is created lazily via :meth:`connect` and torn down via
    :meth:`close`.  Prefer the module-level :func:`get_pool` singleton
    over manual instantiation unless you need isolated pools (e.g. tests).

    Example::

        async with DatabasePool(config) as pool:
            await pool.execute("INSERT INTO odds_ticks ...")
            rows = await pool.fetch("SELECT 1")
    """

    def __init__(self, config: Optional[DBConfig] = None) -> None:
        self._config = config or DBConfig()
        self._pool: Any = None  # asyncpg.Pool, but lazy-imported

    @property
    def pool(self) -> Any:
        """Return the underlying asyncpg pool, or ``None`` if not connected."""
        return self._pool

    async def connect(self) -> None:
        """Create the asyncpg connection pool.

        Raises:
            ImportError: If ``asyncpg`` is not installed.
        """
        import asyncpg  # noqa: F811 — lazy import

        if self._pool is not None:
            logger.debug("Pool already connected — skipping")
            return

        logger.info(
            "Connecting to TimescaleDB at %s:%s/%s",
            self._config.host,
            self._config.port,
            self._config.database,
        )
        self._pool = await asyncpg.create_pool(
            dsn=self._config.to_dsn(),
            min_size=2,
            max_size=10,
            command_timeout=60,
        )
        logger.info("Connection pool established (min=2, max=10)")

    async def close(self) -> None:
        """Close the connection pool gracefully."""
        if self._pool is not None:
            logger.info("Closing connection pool")
            await self._pool.close()
            self._pool = None
            logger.info("Connection pool closed")

    async def __aenter__(self) -> DatabasePool:
        await self.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def execute(self, query: str, *args: Any) -> str:
        """Execute a single SQL command and return the status tag.

        Args:
            query: SQL statement.
            *args: Query parameters.

        Returns:
            The command status tag (e.g. ``"INSERT 3"``).
        """
        assert self._pool is not None, "Pool not connected — call connect() first"
        return await self._pool.execute(query, *args)

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        """Execute a SELECT query and return all matching rows.

        Args:
            query: SQL SELECT statement.
            *args: Query parameters.

        Returns:
            A list of :class:`asyncpg.Record` objects.
        """
        assert self._pool is not None, "Pool not connected — call connect() first"
        return await self._pool.fetch(query, *args)

    async def fetchrow(self, query: str, *args: Any) -> Optional[Any]:
        """Execute a SELECT query and return the first row.

        Args:
            query: SQL SELECT statement.
            *args: Query parameters.

        Returns:
            The first :class:`asyncpg.Record`, or ``None`` if no rows match.
        """
        assert self._pool is not None, "Pool not connected — call connect() first"
        return await self._pool.fetchrow(query, *args)

    async def fetchval(self, query: str, *args: Any) -> Any:
        """Execute a SELECT query and return a single scalar value.

        Args:
            query: SQL SELECT statement returning one value.
            *args: Query parameters.

        Returns:
            The first column of the first row.
        """
        assert self._pool is not None, "Pool not connected — call connect() first"
        return await self._pool.fetchval(query, *args)

    async def executemany(self, query: str, args: list[tuple[Any, ...]]) -> None:
        """Execute a command for every argument sequence in *args*.

        Useful for batch inserts or updates.

        Args:
            query: SQL statement with parameter placeholders.
            args: A list of parameter tuples.
        """
        assert self._pool is not None, "Pool not connected — call connect() first"
        await self._pool.executemany(query, args)

    async def copy_records_to_table(
        self,
        table_name: str,
        records: list[tuple[Any, ...]],
        columns: list[str],
    ) -> None:
        """Bulk-insert records using the PostgreSQL COPY protocol.

        This is the fastest way to load large batches of data (e.g. odds
        ticks, injury reports) into TimescaleDB.

        Args:
            table_name: Target table (e.g. ``"odds_ticks"``).
            records: Row data as a list of tuples.
            columns: Column names matching the tuple order.
        """
        assert self._pool is not None, "Pool not connected — call connect() first"
        async with self._pool.acquire() as conn:
            await conn.copy_records_to_table(table_name, records=records, columns=columns)


# ──────────────────────────────────────────────
# Module-level Singleton
# ──────────────────────────────────────────────

_pool_singleton: Optional[DatabasePool] = None
_pool_lock = asyncio.Lock()


async def get_pool(config: Optional[DBConfig] = None) -> DatabasePool:
    """Return the module-level :class:`DatabasePool` singleton.

    On the first call the pool is created and connected.  Subsequent
    calls return the same instance.  The function is safe to call from
    multiple coroutines — an :class:`asyncio.Lock` serialises the
    initial creation.

    Args:
        config: Optional configuration.  Used only on the first call
            to initialise the pool.  Ignored on subsequent calls.

    Returns:
        The shared :class:`DatabasePool` instance.
    """
    global _pool_singleton

    if _pool_singleton is not None:
        return _pool_singleton

    async with _pool_lock:
        # Re-check after acquiring the lock (double-checked locking)
        if _pool_singleton is not None:
            return _pool_singleton

        pool = DatabasePool(config=config)
        await pool.connect()
        _pool_singleton = pool
        logger.info("Created singleton DatabasePool")
        return _pool_singleton


async def reset_pool() -> None:
    """Close and clear the module-level pool singleton.

    Intended for use in test teardowns.
    """
    global _pool_singleton

    if _pool_singleton is not None:
        await _pool_singleton.close()
        _pool_singleton = None
        logger.info("Reset singleton DatabasePool")


# ──────────────────────────────────────────────
# Health Check
# ──────────────────────────────────────────────


async def health_check(pool: DatabasePool) -> dict[str, Any]:
    """Verify database connectivity and return server metadata.

    Runs a lightweight ``SELECT 1`` and queries PostgreSQL/TimescaleDB
    version strings.

    Args:
        pool: A connected :class:`DatabasePool`.

    Returns:
        A dict with keys ``status``, ``latency_ms``, ``version``, and
        ``timescaledb`` (the extension version, or ``None``).
    """
    start = time.monotonic()
    await pool.fetchval("SELECT 1")
    latency_ms = round((time.monotonic() - start) * 1000, 2)

    pg_version: Optional[str] = await pool.fetchval("SELECT version()")

    ts_row = await pool.fetchrow(
        "SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'"
    )
    timescaledb_version: Optional[str] = ts_row["extversion"] if ts_row else None

    return {
        "status": "healthy",
        "latency_ms": latency_ms,
        "version": pg_version,
        "timescaledb": timescaledb_version,
    }
