"""Unit tests for connection pool leak detector cleanup functionality."""

import time
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine

from autopack.db_leak_detector import (ConnectionLeakDetector,
                                       _connection_checkout_times)


@pytest.fixture
def mock_pool():
    """Create a mock pool for testing."""
    pool = Mock()
    pool.size.return_value = 20
    pool.checkedout.return_value = 5
    pool.overflow.return_value = 0
    return pool


@pytest.fixture
def detector(mock_pool):
    """Create a ConnectionLeakDetector with mocked pool."""
    return ConnectionLeakDetector(mock_pool, threshold=0.8)


@pytest.fixture(autouse=True)
def clear_checkout_times():
    """Clear checkout times before and after each test."""
    _connection_checkout_times.clear()
    yield
    _connection_checkout_times.clear()


def test_force_cleanup_closes_stale_connections(detector):
    """Verify force_cleanup_stale_connections removes connections older than max_age."""
    now = time.time()

    # Simulate 3 connections: 2 stale (>30 min), 1 fresh
    _connection_checkout_times[1001] = now - (35 * 60)  # 35 minutes old - stale
    _connection_checkout_times[1002] = now - (45 * 60)  # 45 minutes old - stale
    _connection_checkout_times[1003] = now - (10 * 60)  # 10 minutes old - fresh

    cleaned = detector.force_cleanup_stale_connections(max_age_minutes=30)

    assert cleaned == 2
    # Stale connections should be removed from tracking
    assert 1001 not in _connection_checkout_times
    assert 1002 not in _connection_checkout_times
    # Fresh connection should remain
    assert 1003 in _connection_checkout_times


def test_cleanup_skips_active_transactions(detector):
    """Verify cleanup respects connections with recent activity (not truly stale)."""
    now = time.time()

    # Only add a fresh connection - simulates active transaction
    _connection_checkout_times[2001] = now - (5 * 60)  # 5 minutes old - active
    _connection_checkout_times[2002] = now - (15 * 60)  # 15 minutes old - still active

    cleaned = detector.force_cleanup_stale_connections(max_age_minutes=30)

    # No connections should be cleaned - all are within the 30 minute window
    assert cleaned == 0
    assert 2001 in _connection_checkout_times
    assert 2002 in _connection_checkout_times


def test_pool_config_explicit():
    """Verify engine pool configuration with explicit limits using QueuePool."""
    from sqlalchemy.pool import QueuePool

    # Create an in-memory SQLite engine with explicit QueuePool configuration
    # SQLite doesn't support pool settings directly, so we explicitly use QueuePool
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=QueuePool,
        pool_size=20,
        max_overflow=10,
        pool_timeout=30,
        pool_pre_ping=True,
    )

    pool = engine.pool

    # Verify pool configuration
    assert pool.size() == 20
    assert pool.timeout() == 30
    # max_overflow is accessible via the pool's _max_overflow attribute
    assert hasattr(pool, "_max_overflow")
    assert pool._max_overflow == 10

    engine.dispose()


def test_cleanup_triggered_when_threshold_exceeded(mock_pool):
    """Verify check_pool_health triggers cleanup when checked_out > CLEANUP_THRESHOLD."""
    mock_pool.checkedout.return_value = 18  # Above CLEANUP_THRESHOLD of 15

    detector = ConnectionLeakDetector(mock_pool, threshold=0.8)

    now = time.time()
    # Add a stale connection
    _connection_checkout_times[3001] = now - (40 * 60)  # 40 minutes old

    health = detector.check_pool_health()

    # Cleanup should have been triggered and reported
    assert "stale_cleaned" in health
    assert health["stale_cleaned"] == 1


def test_cleanup_not_triggered_below_threshold(mock_pool):
    """Verify check_pool_health does not cleanup when checked_out <= CLEANUP_THRESHOLD."""
    mock_pool.checkedout.return_value = 10  # Below CLEANUP_THRESHOLD of 15

    detector = ConnectionLeakDetector(mock_pool, threshold=0.8)

    now = time.time()
    # Add a stale connection (would be cleaned if threshold was exceeded)
    _connection_checkout_times[4001] = now - (40 * 60)

    health = detector.check_pool_health()

    # Cleanup should NOT have been triggered
    assert "stale_cleaned" not in health
    # Stale connection tracking should still be present
    assert 4001 in _connection_checkout_times


def test_force_cleanup_with_no_stale_connections(detector):
    """Verify cleanup returns 0 when no connections are stale."""
    now = time.time()

    # All connections are fresh
    _connection_checkout_times[5001] = now - (5 * 60)
    _connection_checkout_times[5002] = now - (10 * 60)

    cleaned = detector.force_cleanup_stale_connections(max_age_minutes=30)

    assert cleaned == 0


def test_force_cleanup_with_empty_tracking(detector):
    """Verify cleanup handles empty tracking dictionary gracefully."""
    cleaned = detector.force_cleanup_stale_connections(max_age_minutes=30)

    assert cleaned == 0


def test_force_cleanup_custom_max_age(detector):
    """Verify cleanup respects custom max_age_minutes parameter."""
    now = time.time()

    # Connection is 20 minutes old
    _connection_checkout_times[6001] = now - (20 * 60)

    # With default 30 min threshold, should NOT be cleaned
    cleaned = detector.force_cleanup_stale_connections(max_age_minutes=30)
    assert cleaned == 0
    assert 6001 in _connection_checkout_times

    # With 15 min threshold, should be cleaned
    cleaned = detector.force_cleanup_stale_connections(max_age_minutes=15)
    assert cleaned == 1
    assert 6001 not in _connection_checkout_times
