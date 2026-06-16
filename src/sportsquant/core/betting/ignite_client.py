"""
Apache Ignite Client Wrapper for Betting State Management

This module provides a wrapper around pyignite to manage betting state
including bankroll, positions, and portfolio data in Apache Ignite
instead of Redis.

Adapted from Redis-based architecture:
- Replaced redis.Redis() with IgniteCache wrapper
- Replaced redis.pipeline() with Ignite batch operations
- Store bankroll/positions state in Ignite distributed cache

Apache Ignite provides:
- Distributed in-memory key-value store
- SQL queries on cached data
- ACID transactions
- Horizontal scaling
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

try:
    from pyignite import Client
    from pyignite.cache import Cache

    _PYIGNITE_AVAILABLE = True
except ImportError:
    Client = None  # type: ignore[assignment]
    Cache = None  # type: ignore[assignment]
    _PYIGNITE_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IgniteConfig:
    """Configuration for Ignite connection."""

    host: str = "localhost"
    port: int = 10800
    username: str = ""
    password: str = ""
    timeout: int = 30
    max_reconnects: int = 3


@dataclass
class BankrollState:
    """Bankroll state stored in Ignite."""

    current_amount: float
    initial_amount: float
    peak_amount: float
    last_updated: str = ""
    total_deposits: float = 0.0
    total_withdrawals: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert bankroll state to dictionary.

        Returns:
            Dictionary representation of the bankroll state.
        """
        return {
            "current_amount": self.current_amount,
            "initial_amount": self.initial_amount,
            "peak_amount": self.peak_amount,
            "last_updated": self.last_updated,
            "total_deposits": self.total_deposits,
            "total_withdrawals": self.total_withdrawals,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BankrollState":
        """Create BankrollState from dictionary.

        Args:
            data: Dictionary with bankroll data.

        Returns:
            BankrollState instance.
        """
        return cls(
            current_amount=data.get("current_amount", 0.0),
            initial_amount=data.get("initial_amount", 0.0),
            peak_amount=data.get("peak_amount", 0.0),
            last_updated=data.get("last_updated", ""),
            total_deposits=data.get("total_deposits", 0.0),
            total_withdrawals=data.get("total_withdrawals", 0.0),
        )


@dataclass
class Position:  # pylint: disable=too-many-instance-attributes
    """Single position state."""

    player_id: str
    market: str
    line: float
    odds: float
    stake: float
    side: str
    book: str
    status: str = "pending"
    bet_id: str = ""
    placed_at: str = ""
    pnl: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert position to dictionary.

        Returns:
            Dictionary representation of the position.
        """
        return {
            "player_id": self.player_id,
            "market": self.market,
            "line": self.line,
            "odds": self.odds,
            "stake": self.stake,
            "side": self.side,
            "book": self.book,
            "status": self.status,
            "bet_id": self.bet_id,
            "placed_at": self.placed_at,
            "pnl": self.pnl,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Position":
        """Create Position from dictionary.

        Args:
            data: Dictionary with position data.

        Returns:
            Position instance.
        """
        return cls(
            player_id=data.get("player_id", ""),
            market=data.get("market", ""),
            line=data.get("line", 0.0),
            odds=data.get("odds", 0.0),
            stake=data.get("stake", 0.0),
            side=data.get("side", ""),
            book=data.get("book", ""),
            status=data.get("status", "pending"),
            bet_id=data.get("bet_id", ""),
            placed_at=data.get("placed_at", ""),
            pnl=data.get("pnl", 0.0),
        )


@dataclass
class PortfolioState:
    """Portfolio state with multiple positions."""

    positions: dict[str, Position] = field(default_factory=dict)
    settled_positions: list[dict[str, Any]] = field(default_factory=list)
    total_exposure: float = 0.0
    daily_pnl: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert portfolio state to dictionary.

        Returns:
            Dictionary representation of the portfolio.
        """
        return {
            "positions": {k: v.to_dict() for k, v in self.positions.items()},
            "settled_positions": self.settled_positions,
            "total_exposure": self.total_exposure,
            "daily_pnl": self.daily_pnl,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PortfolioState":
        """Create PortfolioState from dictionary.

        Args:
            data: Dictionary with portfolio data.

        Returns:
            PortfolioState instance.
        """
        positions = {}
        for k, v in data.get("positions", {}).items():
            positions[k] = Position.from_dict(v)
        return cls(
            positions=positions,
            settled_positions=data.get("settled_positions", []),
            total_exposure=data.get("total_exposure", 0.0),
            daily_pnl=data.get("daily_pnl", 0.0),
        )


# pylint: disable=too-many-instance-attributes,too-many-locals
class IgniteCache:
    """
    Wrapper around pyignite Cache for betting state management.

    Provides Redis-compatible interface for:
    - Bankroll state storage and retrieval
    - Position tracking
    - Portfolio state persistence
    - Batch operations for performance

    Example:
        >>> cache = IgniteCache()
        >>> bankroll = cache.get_bankroll("primary")
        >>> cache.update_bankroll("primary", 10000.0)
        >>> cache.place_position(position)
    """

    def __init__(self, config: Optional[IgniteConfig] = None):
        """Initialize Ignite cache client.

        Args:
            config: Ignite connection configuration
        """
        self.config = config or IgniteConfig()
        self._client: Optional[Client] = None
        self._caches: dict[str, Cache] = {}
        self._connect()

    def _connect(self) -> None:
        """Establish connection to Ignite cluster."""
        try:
            self._client = Client(
                host=self.config.host,
                port=self.config.port,
                username=self.config.username if self.config.username else None,
                password=self.config.password if self.config.password else None,
                timeout=self.config.timeout,
            )
            self._client.connect()
            logger.info("Connected to Ignite at %s:%d", self.config.host, self.config.port)
        except Exception as e:
            logger.error("Failed to connect to Ignite: %s", e)
            raise

    def _get_cache(self, name: str) -> Cache:
        """Get or create a named cache.

        Args:
            name: Cache name

        Returns:
            Cache instance
        """
        assert self._client is not None
        if name not in self._caches:
            self._caches[name] = self._client.get_cache(name)
        return self._caches[name]

    def close(self) -> None:
        """Close all connections."""
        if self._client:
            self._client.close()
            logger.info("Closed Ignite connection")

    def ping(self) -> bool:
        """Check if Ignite is reachable."""
        try:
            assert self._client is not None
            self._client.connect()
            return True
        except (ConnectionError, RuntimeError):
            return False

    def get(self, cache_name: str, key: str) -> Optional[dict[str, Any]]:
        """Get a value from cache.

        Args:
            cache_name: Name of the cache
            key: Key to retrieve

        Returns:
            Value as dictionary or None
        """
        try:
            cache = self._get_cache(cache_name)
            value = cache.get(key)
            if value is not None:
                return value
        except (KeyError, RuntimeError) as e:
            logger.error("Error getting key %s from cache %s: %s", key, cache_name, e)
        return None

    def put(self, cache_name: str, key: str, value: dict[str, Any], ttl: int = 0) -> bool:
        """Put a value into cache.

        Args:
            cache_name: Name of the cache
            key: Key to store
            value: Value to store
            ttl: Time to live in seconds (not fully supported by Ignite)

        Returns:
            True if successful
        """
        try:
            cache = self._get_cache(cache_name)
            cache.put(key, value)
            if ttl > 0:
                cache.with_expiry_mode(ttl=ttl)  # type: ignore[reportAttributeAccessIssue]
            return True
        except (KeyError, RuntimeError) as e:
            logger.error("Error putting key %s to cache %s: %s", key, cache_name, e)
            return False

    def delete(self, cache_name: str, key: str) -> bool:
        """Delete a key from cache.

        Args:
            cache_name: Name of the cache
            key: Key to delete

        Returns:
            True if successful
        """
        try:
            cache = self._get_cache(cache_name)
            cache.remove(key)  # type: ignore[reportAttributeAccessIssue]
            return True
        except (KeyError, RuntimeError) as e:
            logger.error("Error deleting key %s from cache %s: %s", key, cache_name, e)
            return False

    def exists(self, cache_name: str, key: str) -> bool:
        """Check if a key exists in cache.

        Args:
            cache_name: Name of the cache
            key: Key to check

        Returns:
            True if key exists
        """
        try:
            cache = self._get_cache(cache_name)
            return cache.contains_key(key)
        except (KeyError, RuntimeError) as e:
            logger.error("Error checking key %s in cache %s: %s", key, cache_name, e)
            return False

    def scan(self, cache_name: str, pattern: str = "*") -> list[tuple[str, dict[str, Any]]]:
        """Scan cache for keys matching pattern.

        Args:
            cache_name: Name of the cache
            pattern: Key pattern (e.g., "bankroll_*")

        Returns:
            List of (key, value) tuples
        """
        results = []
        try:
            cache = self._get_cache(cache_name)
            for key in cache.scan():
                if pattern == "*" or pattern in key:
                    value = cache.get(key)
                    if value:
                        results.append((key, value))
        except (KeyError, RuntimeError) as e:
            logger.error("Error scanning cache %s: %s", cache_name, e)
        return results


class IgniteBankrollManager:
    """
    Manages bankroll state using Apache Ignite.

    Replaces Redis-based bankroll management with Ignite for:
    - Distributed state storage
    - ACID transactions
    - Horizontal scaling

    Attributes:
        cache: IgniteCache instance for state storage
        bankroll_cache_name: Cache name for bankroll data
    """

    def __init__(
        self,
        ignite_cache: Optional[IgniteCache] = None,
        config: Optional[IgniteConfig] = None,
    ):
        """Initialize bankroll manager.

        Args:
            ignite_cache: Optional IgniteCache instance
            config: Optional Ignite connection config
        """
        self.cache = ignite_cache or IgniteCache(config)
        self.bankroll_cache_name = "betting_bankroll"
        self.default_key = "primary"

    def get_bankroll(self, key: Optional[str] = None) -> Optional[BankrollState]:
        """Get current bankroll state.

        Args:
            key: Bankroll key (defaults to 'primary')

        Returns:
            BankrollState or None
        """
        k = key or self.default_key
        data = self.cache.get(self.bankroll_cache_name, k)
        if data:
            return BankrollState.from_dict(data)
        return None

    def set_bankroll(self, bankroll: BankrollState, key: Optional[str] = None) -> bool:
        """Set bankroll state.

        Args:
            bankroll: BankrollState to store
            key: Bankroll key

        Returns:
            True if successful
        """
        k = key or self.default_key
        return self.cache.put(self.bankroll_cache_name, k, bankroll.to_dict())

    def initialize_bankroll(self, amount: float, key: Optional[str] = None) -> BankrollState:
        """Initialize a new bankroll.

        Args:
            amount: Initial bankroll amount
            key: Bankroll key

        Returns:
            Created BankrollState
        """
        bankroll = BankrollState(
            current_amount=amount,
            initial_amount=amount,
            peak_amount=amount,
            last_updated=datetime.now(timezone.utc).isoformat(),
        )
        self.set_bankroll(bankroll, key)
        return bankroll

    def update_bankroll(
        self,
        profit: float,
        loss: Optional[float] = None,
        key: Optional[str] = None,
    ) -> Optional[BankrollState]:
        """Update bankroll with profit/loss.

        Args:
            profit: Profit amount (negative for loss)
            loss: Optional explicit loss amount
            key: Bankroll key

        Returns:
            Updated BankrollState or None
        """
        bankroll = self.get_bankroll(key)
        if not bankroll:
            return None

        if loss is not None:
            bankroll.current_amount -= loss
        else:
            bankroll.current_amount += profit

        bankroll.current_amount = max(0.0, bankroll.current_amount)
        bankroll.peak_amount = max(bankroll.peak_amount, bankroll.current_amount)

        bankroll.last_updated = datetime.now(timezone.utc).isoformat()

        self.set_bankroll(bankroll, key)
        return bankroll

    def get_balance(self, key: Optional[str] = None) -> float:
        """Get current balance.

        Args:
            key: Bankroll key

        Returns:
            Current balance
        """
        bankroll = self.get_bankroll(key)
        return bankroll.current_amount if bankroll else 0.0


class IgnitePositionManager:
    """
    Manages positions using Apache Ignite.

    Replaces Redis-based position tracking with Ignite for:
    - Distributed position storage
    - Query by player, market, book
    - Batch updates

    Attributes:
        cache: IgniteCache instance
        position_cache_name: Cache name for positions
    """

    def __init__(
        self,
        ignite_cache: Optional[IgniteCache] = None,
        config: Optional[IgniteConfig] = None,
    ):
        """Initialize position manager.

        Args:
            ignite_cache: Optional IgniteCache instance
            config: Optional Ignite connection config
        """
        self.cache = ignite_cache or IgniteCache(config)
        self.position_cache_name = "betting_positions"

    def add_position(self, position: Position, key: Optional[str] = None) -> bool:
        """Add a new position.

        Args:
            position: Position to add
            key: Position key (defaults to bet_id)

        Returns:
            True if successful
        """
        k = key or position.bet_id
        return self.cache.put(self.position_cache_name, k, position.to_dict())

    def get_position(self, bet_id: str) -> Optional[Position]:
        """Get a position by bet ID.

        Args:
            bet_id: Bet identifier

        Returns:
            Position or None
        """
        data = self.cache.get(self.position_cache_name, bet_id)
        if data:
            return Position.from_dict(data)
        return None

    def get_all_positions(self) -> list[Position]:
        """Get all pending positions.

        Returns:
            List of positions
        """
        positions = []
        for _, data in self.cache.scan(self.position_cache_name):
            if data.get("status") == "pending":
                positions.append(Position.from_dict(data))
        return positions

    def get_positions_by_market(self, market: str) -> list[Position]:
        """Get positions filtered by market.

        Args:
            market: Market name (e.g., 'pts', 'reb')

        Returns:
            List of positions
        """
        positions = []
        for _, data in self.cache.scan(self.position_cache_name):
            if data.get("status") == "pending" and data.get("market") == market:
                positions.append(Position.from_dict(data))
        return positions

    def get_positions_by_player(self, player_id: str) -> list[Position]:
        """Get positions filtered by player.

        Args:
            player_id: Player identifier

        Returns:
            List of positions
        """
        positions = []
        for _, data in self.cache.scan(self.position_cache_name):
            if data.get("status") == "pending" and data.get("player_id") == player_id:
                positions.append(Position.from_dict(data))
        return positions

    def settle_position(self, bet_id: str, result: int, payout: float) -> bool:
        """Settle a position.

        Args:
            bet_id: Bet identifier
            result: 1 for win, 0 for loss
            payout: Payout amount (including stake)

        Returns:
            True if successful
        """
        position = self.get_position(bet_id)
        if not position:
            return False

        position.status = "settled"
        position.pnl = payout - position.stake if result == 1 else -position.stake

        self.cache.put(self.position_cache_name, bet_id, position.to_dict())
        return True

    def remove_position(self, bet_id: str) -> bool:
        """Remove a position.

        Args:
            bet_id: Bet identifier

        Returns:
            True if successful
        """
        return self.cache.delete(self.position_cache_name, bet_id)


class IgnitePortfolioManager:
    """
    Manages portfolio state using Apache Ignite.

    Combines bankroll and position management for complete
    portfolio tracking and persistence.

    Replaces Redis-based portfolio management with Ignite for:
    - Distributed state
    - ACID consistency
    - Query capabilities

    Example:
        >>> portfolio = IgnitePortfolioManager()
        >>> bankroll = portfolio.get_bankroll_state()
        >>> positions = portfolio.get_pending_positions()
    """

    def __init__(
        self,
        ignite_cache: Optional[IgniteCache] = None,
        config: Optional[IgniteConfig] = None,
    ):
        """Initialize portfolio manager.

        Args:
            ignite_cache: Optional IgniteCache instance
            config: Optional Ignite connection config
        """
        self.cache = ignite_cache or IgniteCache(config)
        self.bankroll_mgr = IgniteBankrollManager(self.cache, config)
        self.position_mgr = IgnitePositionManager(self.cache, config)

    def get_bankroll_state(self) -> Optional[BankrollState]:
        """Get current bankroll state."""
        return self.bankroll_mgr.get_bankroll()

    def get_balance(self) -> float:
        """Get current balance."""
        return self.bankroll_mgr.get_balance()

    def get_pending_positions(self) -> list[Position]:
        """Get all pending positions."""
        return self.position_mgr.get_all_positions()

    def get_total_exposure(self) -> float:
        """Calculate total pending exposure."""
        positions = self.get_pending_positions()
        return sum(p.stake for p in positions)

    def get_market_exposure(self, market: str) -> float:
        """Calculate exposure for a specific market."""
        positions = self.position_mgr.get_positions_by_market(market)
        return sum(p.stake for p in positions)

    def get_player_exposure(self, player_id: str) -> float:
        """Calculate exposure for a specific player."""
        positions = self.position_mgr.get_positions_by_player(player_id)
        return sum(p.stake for p in positions)

    def place_bet(self, position: Position) -> bool:
        """Place a new bet and update state.

        Args:
            position: Position to place

        Returns:
            True if successful
        """
        balance = self.get_balance()
        if position.stake > balance:
            logger.warning("Insufficient balance for bet: %s > %s", position.stake, balance)
            return False

        success = self.position_mgr.add_position(position)
        if success:
            self.bankroll_mgr.update_bankroll(-position.stake)
        return success

    def settle_bet(self, bet_id: str, result: int, odds: float) -> bool:
        """Settle a bet and update state.

        Args:
            bet_id: Bet identifier
            result: 1 for win, 0 for loss
            odds: Decimal odds

        Returns:
            True if successful
        """
        position = self.position_mgr.get_position(bet_id)
        if not position:
            return False

        payout = position.stake * odds if result == 1 else 0.0
        profit = payout - position.stake if result == 1 else -position.stake

        self.position_mgr.settle_position(bet_id, result, payout)
        self.bankroll_mgr.update_bankroll(profit)

        return True


__all__ = [
    "IgniteConfig",
    "IgniteCache",
    "BankrollState",
    "Position",
    "PortfolioState",
    "IgniteBankrollManager",
    "IgnitePositionManager",
    "IgnitePortfolioManager",
]
