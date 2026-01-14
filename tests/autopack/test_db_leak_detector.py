"""Unit tests for connection pool leak detector."""

from unittest.mock import Mock

from autopack.db_leak_detector import ConnectionLeakDetector


def test_leak_detector_warns_at_threshold():
    """Verify leak detector warns when utilization exceeds threshold."""
    mock_pool = Mock()
    mock_pool.size.return_value = 10
    mock_pool.checkedout.return_value = 9  # 90% utilization
    mock_pool.overflow.return_value = 0

    detector = ConnectionLeakDetector(mock_pool, threshold=0.8)
    health = detector.check_pool_health()

    assert health["utilization"] == 0.9
    assert health["is_healthy"] is False
    assert health["pool_size"] == 10
    assert health["checked_out"] == 9
    assert health["overflow"] == 0


def test_leak_detector_healthy_below_threshold():
    """Verify leak detector reports healthy when below threshold."""
    mock_pool = Mock()
    mock_pool.size.return_value = 10
    mock_pool.checkedout.return_value = 5  # 50% utilization
    mock_pool.overflow.return_value = 0

    detector = ConnectionLeakDetector(mock_pool, threshold=0.8)
    health = detector.check_pool_health()

    assert health["utilization"] == 0.5
    assert health["is_healthy"] is True
    assert health["pool_size"] == 10
    assert health["checked_out"] == 5


def test_leak_detector_at_exact_threshold():
    """Verify leak detector behavior when utilization equals threshold."""
    mock_pool = Mock()
    mock_pool.size.return_value = 10
    mock_pool.checkedout.return_value = 8  # Exactly 80%
    mock_pool.overflow.return_value = 0

    detector = ConnectionLeakDetector(mock_pool, threshold=0.8)
    health = detector.check_pool_health()

    assert health["utilization"] == 0.8
    assert health["is_healthy"] is False  # >= threshold means unhealthy


def test_leak_detector_with_overflow():
    """Verify leak detector handles overflow connections."""
    mock_pool = Mock()
    mock_pool.size.return_value = 10
    mock_pool.checkedout.return_value = 12  # 120% - overflow in use
    mock_pool.overflow.return_value = 2

    detector = ConnectionLeakDetector(mock_pool, threshold=0.8)
    health = detector.check_pool_health()

    assert health["pool_size"] == 10
    assert health["checked_out"] == 12
    assert health["overflow"] == 2
    assert health["utilization"] == 1.2
    assert health["is_healthy"] is False


def test_leak_detector_empty_pool():
    """Verify leak detector handles zero pool size."""
    mock_pool = Mock()
    mock_pool.size.return_value = 0
    mock_pool.checkedout.return_value = 0
    mock_pool.overflow.return_value = 0

    detector = ConnectionLeakDetector(mock_pool, threshold=0.8)
    health = detector.check_pool_health()

    assert health["pool_size"] == 0
    assert health["checked_out"] == 0
    assert health["utilization"] == 0  # 0/0 case handled
    assert health["is_healthy"] is True


def test_leak_detector_custom_threshold():
    """Verify leak detector respects custom threshold."""
    mock_pool = Mock()
    mock_pool.size.return_value = 10
    mock_pool.checkedout.return_value = 6  # 60% utilization

    # 60% threshold: 60% usage is at threshold
    detector = ConnectionLeakDetector(mock_pool, threshold=0.6)
    health = detector.check_pool_health()

    assert health["utilization"] == 0.6
    assert health["is_healthy"] is False  # >= threshold

    # 70% threshold: 60% usage is below threshold
    detector = ConnectionLeakDetector(mock_pool, threshold=0.7)
    health = detector.check_pool_health()

    assert health["utilization"] == 0.6
    assert health["is_healthy"] is True  # < threshold


def test_leak_detector_all_connections_in_use():
    """Verify leak detector when all connections are checked out."""
    mock_pool = Mock()
    mock_pool.size.return_value = 20
    mock_pool.checkedout.return_value = 20  # 100% utilization
    mock_pool.overflow.return_value = 0

    detector = ConnectionLeakDetector(mock_pool, threshold=0.8)
    health = detector.check_pool_health()

    assert health["pool_size"] == 20
    assert health["checked_out"] == 20
    assert health["utilization"] == 1.0
    assert health["is_healthy"] is False
