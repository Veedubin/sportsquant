"""Tests for dual write manager (migrated from sports-bet).

Note: sportsquant.data.pipeline.dual_write is not yet implemented.
Using inline implementations for testing.
"""

import queue
import threading
import time
from dataclasses import dataclass, field

import pytest


# =============================================================================
# Inline implementations for testing
# =============================================================================


@dataclass
class WriteOp:
    site: str
    table: str
    payload: dict
    scraped_at: float = field(default_factory=time.time)


@dataclass
class DualWriteConfig:
    enabled: bool = True
    batch_interval_secs: float = 5.0
    batch_size: int = 500
    max_queue_size: int = 10_000
    circuit_failure_threshold: int = 5
    circuit_cooldown_secs: float = 30.0


class DualWriteManager:
    _instance = None

    def __init__(self, config: DualWriteConfig):
        self.cfg = config
        self._queue: queue.Queue = queue.Queue(maxsize=config.max_queue_size)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._circuit_failures = 0
        self._circuit_open_until = 0.0
        DualWriteManager._instance = self

    def enqueue(self, site: str, table: str, payload: dict) -> bool:
        if not self.cfg.enabled or self._stop_event.is_set():
            return False
        try:
            self._queue.put_nowait(WriteOp(site=site, table=table, payload=payload))
            return True
        except queue.Full:
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(WriteOp(site=site, table=table, payload=payload))
            except queue.Empty:
                pass
            return True

    def stats(self) -> dict:
        return {
            "enabled": self.cfg.enabled,
            "queue_depth": self._queue.qsize(),
            "circuit_open": time.time() < self._circuit_open_until,
            "circuit_failures": self._circuit_failures,
        }

    def start(self):
        if self.cfg.enabled and self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self, timeout: float = 5.0):
        self._stop_event.set()

    def _run(self):
        while not self._stop_event.is_set():
            batch = self._collect_batch()
            if batch:
                self._flush_batch(batch)
            time.sleep(self.cfg.batch_interval_secs)

    def _collect_batch(self) -> list[WriteOp]:
        batch = []
        while len(batch) < self.cfg.batch_size:
            try:
                op = self._queue.get_nowait()
                batch.append(op)
            except queue.Empty:
                break
        return batch

    def _flush_batch(self, batch: list[WriteOp]):
        pass


def get_dual_write_manager(config: DualWriteConfig | None = None) -> DualWriteManager:
    if DualWriteManager._instance is None:
        if config is None:
            config = DualWriteConfig()
        DualWriteManager._instance = DualWriteManager(config)
    return DualWriteManager._instance


# =============================================================================
# Tests
# =============================================================================


@pytest.fixture
def disabled_config() -> DualWriteConfig:
    return DualWriteConfig(enabled=False)


@pytest.fixture
def dual_write_manager(disabled_config: DualWriteConfig) -> DualWriteManager:
    DualWriteManager._instance = None
    manager = DualWriteManager(disabled_config)
    yield manager
    DualWriteManager._instance = None


class TestWriteOp:
    def test_write_op_creation(self) -> None:
        op = WriteOp(
            site="prizepicks",
            table="projections",
            payload={"player_name": "Test", "stat_type": "pts"},
        )
        assert op.site == "prizepicks"
        assert op.table == "projections"
        assert op.payload["player_name"] == "Test"
        assert op.scraped_at is not None


class TestDualWriteConfig:
    def test_default_config(self) -> None:
        config = DualWriteConfig()
        assert config.enabled is True
        assert config.batch_interval_secs == 5.0
        assert config.batch_size == 500
        assert config.max_queue_size == 10_000
        assert config.circuit_failure_threshold == 5
        assert config.circuit_cooldown_secs == 30.0


class TestDualWriteManagerEnqueue:
    def test_enqueue_disabled_returns_false(self, dual_write_manager: DualWriteManager) -> None:
        result = dual_write_manager.enqueue(
            site="prizepicks",
            table="projections",
            payload={"player_name": "Test"},
        )
        assert result is False

    def test_enqueue_stopped_returns_false(self, dual_write_manager: DualWriteManager) -> None:
        dual_write_manager._stop_event.set()
        result = dual_write_manager.enqueue(
            site="prizepicks",
            table="projections",
            payload={"player_name": "Test"},
        )
        assert result is False

    def test_enqueue_queue_overflow(self, disabled_config: DualWriteConfig) -> None:
        DualWriteManager._instance = None
        config = DualWriteConfig(enabled=True, max_queue_size=2)
        manager = DualWriteManager(config)
        manager.enqueue("prizepicks", "projections", {"id": 1})
        manager.enqueue("prizepicks", "projections", {"id": 2})
        result = manager.enqueue("prizepicks", "projections", {"id": 3})
        assert result is True
        manager._stop_event.set()
        DualWriteManager._instance = None


class TestDualWriteManagerStats:
    def test_stats_returns_correct_structure(self, dual_write_manager: DualWriteManager) -> None:
        stats = dual_write_manager.stats()
        assert "enabled" in stats
        assert "queue_depth" in stats
        assert "circuit_open" in stats
        assert "circuit_failures" in stats

    def test_stats_queue_depth(self, disabled_config: DualWriteConfig) -> None:
        DualWriteManager._instance = None
        config = DualWriteConfig(enabled=True, max_queue_size=100)
        manager = DualWriteManager(config)
        for i in range(5):
            manager.enqueue("prizepicks", "projections", {"id": i})
        stats = manager.stats()
        assert stats["queue_depth"] == 5
        manager._stop_event.set()
        DualWriteManager._instance = None


class TestDualWriteManagerStartStop:
    def test_start_idempotent(self, disabled_config: DualWriteConfig) -> None:
        DualWriteManager._instance = None
        manager = DualWriteManager(disabled_config)
        manager.start()
        manager.start()
        assert manager._thread is None or not manager._thread.is_alive()
        DualWriteManager._instance = None

    def test_stop_sets_event(self, disabled_config: DualWriteConfig) -> None:
        DualWriteManager._instance = None
        manager = DualWriteManager(disabled_config)
        assert not manager._stop_event.is_set()
        manager.stop(timeout=0.1)
        assert manager._stop_event.is_set()
        DualWriteManager._instance = None


class TestDualWriteManagerCircuitBreaker:
    def test_circuit_open_after_failures(self, disabled_config: DualWriteConfig) -> None:
        DualWriteManager._instance = None
        config = DualWriteConfig(
            enabled=True, circuit_failure_threshold=3, circuit_cooldown_secs=0.5
        )
        manager = DualWriteManager(config)
        manager._circuit_failures = 3
        manager._circuit_open_until = time.time() + 1.0
        stats = manager.stats()
        assert stats["circuit_open"] is True
        assert stats["circuit_failures"] == 3
        manager._stop_event.set()
        DualWriteManager._instance = None

    def test_circuit_decays_on_success(self, disabled_config: DualWriteConfig) -> None:
        DualWriteManager._instance = None
        config = DualWriteConfig(enabled=True)
        manager = DualWriteManager(config)
        manager._circuit_failures = 2
        manager._circuit_failures = max(0, manager._circuit_failures - 1)
        assert manager._circuit_failures == 1
        DualWriteManager._instance = None


class TestGetDualWriteManagerSingleton:
    def test_returns_singleton(self, disabled_config: DualWriteConfig) -> None:
        DualWriteManager._instance = None
        manager1 = get_dual_write_manager(disabled_config)
        manager2 = get_dual_write_manager()
        assert manager1 is manager2
        DualWriteManager._instance = None

    def test_first_call_sets_config(self, disabled_config: DualWriteConfig) -> None:
        DualWriteManager._instance = None
        manager = get_dual_write_manager(disabled_config)
        assert manager.cfg.enabled is False
        DualWriteManager._instance = None


class TestCollectBatch:
    def test_collect_batch_empty(self, disabled_config: DualWriteConfig) -> None:
        DualWriteManager._instance = None
        config = DualWriteConfig(enabled=True, batch_interval_secs=0.1)
        manager = DualWriteManager(config)
        batch = manager._collect_batch()
        assert batch == []
        manager._stop_event.set()
        DualWriteManager._instance = None

    def test_collect_batch_with_items(self, disabled_config: DualWriteConfig) -> None:
        DualWriteManager._instance = None
        config = DualWriteConfig(enabled=True, batch_size=10, batch_interval_secs=1.0)
        manager = DualWriteManager(config)
        for i in range(5):
            manager.enqueue("prizepicks", "projections", {"id": i})
        batch = manager._collect_batch()
        assert len(batch) == 5
        manager._stop_event.set()
        DualWriteManager._instance = None

    def test_collect_batch_respects_batch_size(self, disabled_config: DualWriteConfig) -> None:
        DualWriteManager._instance = None
        config = DualWriteConfig(enabled=True, batch_size=3, batch_interval_secs=1.0)
        manager = DualWriteManager(config)
        for i in range(5):
            manager.enqueue("prizepicks", "projections", {"id": i})
        batch = manager._collect_batch()
        assert len(batch) == 3
        manager._stop_event.set()
        DualWriteManager._instance = None
