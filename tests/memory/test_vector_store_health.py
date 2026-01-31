"""
Tests for vector store health monitoring.

IMP-REL-012: Missing Health Check for Vector Store Operations

Tests cover:
- Health monitor initialization
- Consecutive failure tracking
- Consecutive success tracking
- Health status transitions
- Alert triggering on threshold exceeded
- Health status reporting
- Recovery from degraded state
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from autopack.memory.qdrant_store import QdrantStore, VectorStoreHealthMonitor


class TestVectorStoreHealthMonitor:
    """Test VectorStoreHealthMonitor class."""

    def test_health_monitor_initialization(self):
        """Test health monitor initializes with correct defaults."""
        monitor = VectorStoreHealthMonitor(consecutive_failure_threshold=5)

        assert monitor.consecutive_failure_threshold == 5
        assert monitor.consecutive_failures == 0
        assert monitor.consecutive_successes == 0
        assert monitor.is_healthy is True
        assert monitor.total_failures == 0
        assert monitor.total_successes == 0

    def test_record_success_increments_counter(self):
        """Test that recording success increments success counter."""
        monitor = VectorStoreHealthMonitor()

        monitor.record_success()

        assert monitor.consecutive_successes == 1
        assert monitor.consecutive_failures == 0
        assert monitor.total_successes == 1

    def test_record_success_resets_failure_counter(self):
        """Test that success resets consecutive failure counter."""
        monitor = VectorStoreHealthMonitor()

        monitor.consecutive_failures = 3
        monitor.record_success()

        assert monitor.consecutive_failures == 0
        assert monitor.consecutive_successes == 1

    def test_record_failure_increments_counter(self):
        """Test that recording failure increments failure counter."""
        monitor = VectorStoreHealthMonitor()
        error = Exception("Test error")

        monitor.record_failure(error)

        assert monitor.consecutive_failures == 1
        assert monitor.total_failures == 1
        assert monitor.last_failure_time is not None

    def test_record_failure_resets_success_counter(self):
        """Test that failure resets consecutive success counter."""
        monitor = VectorStoreHealthMonitor()
        error = Exception("Test error")

        monitor.consecutive_successes = 5
        monitor.record_failure(error)

        assert monitor.consecutive_successes == 0
        assert monitor.consecutive_failures == 1

    def test_health_alert_triggered_at_threshold(self, caplog):
        """Test that alert is logged when failure threshold is reached."""
        monitor = VectorStoreHealthMonitor(consecutive_failure_threshold=3)
        error = Exception("Connection error")

        # Record failures up to threshold
        monitor.record_failure(error)
        monitor.record_failure(error)
        monitor.record_failure(error)  # This should trigger alert

        assert monitor.is_healthy is False
        assert "Vector store health degraded" in caplog.text
        assert "3 consecutive failures" in caplog.text

    def test_health_recovery_after_success(self):
        """Test that health recovers when success is recorded after failures."""
        monitor = VectorStoreHealthMonitor(consecutive_failure_threshold=3)
        error = Exception("Connection error")

        # Trigger unhealthy state
        for _ in range(3):
            monitor.record_failure(error)

        assert monitor.is_healthy is False

        # Record success - should recover
        monitor.record_success()

        assert monitor.is_healthy is True
        assert monitor.consecutive_successes == 1

    def test_get_health_status_includes_all_metrics(self):
        """Test that health status includes all required metrics."""
        monitor = VectorStoreHealthMonitor()
        error = Exception("Test error")

        monitor.record_success()
        monitor.record_failure(error)
        monitor.record_success()

        status = monitor.get_health_status()

        assert "is_healthy" in status
        assert "consecutive_failures" in status
        assert "consecutive_successes" in status
        assert "total_failures" in status
        assert "total_successes" in status
        assert "uptime_percent" in status
        assert "last_failure_time" in status
        assert "last_success_time" in status

    def test_uptime_percent_calculation(self):
        """Test that uptime percentage is calculated correctly."""
        monitor = VectorStoreHealthMonitor()

        # Record 8 successes and 2 failures
        for _ in range(8):
            monitor.record_success()
        error = Exception("Test error")
        monitor.record_failure(error)
        monitor.record_failure(error)

        status = monitor.get_health_status()

        # Uptime should be 80%
        assert status["uptime_percent"] == 80.0
        assert status["total_successes"] == 8
        assert status["total_failures"] == 2

    def test_reset_clears_all_metrics(self):
        """Test that reset clears all tracking metrics."""
        monitor = VectorStoreHealthMonitor()
        error = Exception("Test error")

        # Build up some state
        for _ in range(5):
            monitor.record_success()
        monitor.record_failure(error)

        assert monitor.total_successes > 0
        assert monitor.total_failures > 0

        # Reset
        monitor.reset()

        assert monitor.consecutive_failures == 0
        assert monitor.consecutive_successes == 0
        assert monitor.is_healthy is True
        assert monitor.last_failure_time is None
        assert monitor.last_success_time is None


class TestQdrantStoreHealthIntegration:
    """Test health monitoring integration in QdrantStore."""

    @pytest.fixture
    def mock_qdrant_client(self):
        """Fixture providing a mocked QdrantClient."""
        with patch("autopack.memory.qdrant_store.QdrantClient") as mock_client:
            instance = MagicMock()
            instance.get_collections.return_value = Mock(collections=[])
            mock_client.return_value = instance
            yield mock_client, instance

    def test_qdrant_store_initializes_health_monitor(self, mock_qdrant_client):
        """Test that QdrantStore initializes health monitor."""
        _, instance = mock_qdrant_client

        with patch.object(QdrantStore, "_check_qdrant_health", return_value=(True, "")):
            store = QdrantStore(host="localhost", port=6333)

        assert store._health_monitor is not None
        assert isinstance(store._health_monitor, VectorStoreHealthMonitor)

    def test_get_health_status_returns_monitor_status(self, mock_qdrant_client):
        """Test that get_health_status returns health monitor status."""
        _, instance = mock_qdrant_client

        with patch.object(QdrantStore, "_check_qdrant_health", return_value=(True, "")):
            store = QdrantStore(host="localhost", port=6333)

        status = store.get_health_status()

        assert isinstance(status, dict)
        assert "is_healthy" in status
        assert "uptime_percent" in status

    def test_check_vector_store_health_success(self, mock_qdrant_client):
        """Test health check returns True on successful health check."""
        _, instance = mock_qdrant_client

        with patch.object(QdrantStore, "_check_qdrant_health", return_value=(True, "")):
            store = QdrantStore(host="localhost", port=6333)

        # Reset health monitor to test the check
        store._health_monitor.reset()

        result = store.check_vector_store_health()

        assert result is True
        status = store.get_health_status()
        assert status["total_successes"] > 0

    def test_check_vector_store_health_failure(self, mock_qdrant_client):
        """Test health check records failure on exception."""
        _, instance = mock_qdrant_client

        with patch.object(QdrantStore, "_check_qdrant_health", return_value=(True, "")):
            store = QdrantStore(host="localhost", port=6333)

        # Make health check fail
        with patch.object(store, "_health_check", side_effect=Exception("Connection error")):
            result = store.check_vector_store_health()

        assert result is False
        status = store.get_health_status()
        assert status["total_failures"] > 0

    def test_upsert_records_success(self, mock_qdrant_client):
        """Test that upsert operation records success."""
        _, instance = mock_qdrant_client
        instance.upsert.return_value = None

        with patch.object(QdrantStore, "_check_qdrant_health", return_value=(True, "")):
            store = QdrantStore(host="localhost", port=6333)

        # Reset health monitor
        store._health_monitor.reset()

        points = [{"id": "test-1", "vector": [0.1] * 1536, "payload": {"text": "test"}}]
        store.upsert("test_collection", points)

        status = store.get_health_status()
        assert status["total_successes"] > 0

    def test_search_records_success(self, mock_qdrant_client):
        """Test that search operation records success."""
        _, instance = mock_qdrant_client

        # Mock successful search
        mock_hit = Mock()
        mock_hit.id = "test-id"
        mock_hit.score = 0.95
        mock_hit.payload = {"_original_id": "test-id", "text": "test"}

        mock_query_result = Mock()
        mock_query_result.points = [mock_hit]
        instance.query_points.return_value = mock_query_result

        with patch.object(QdrantStore, "_check_qdrant_health", return_value=(True, "")):
            store = QdrantStore(host="localhost", port=6333)

        # Reset health monitor
        store._health_monitor.reset()

        results = store.search("test_collection", [0.1] * 1536)

        status = store.get_health_status()
        assert status["total_successes"] > 0
        assert len(results) > 0
