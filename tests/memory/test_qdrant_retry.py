"""
Tests for Qdrant retry logic and fallback mechanism.

IMP-REL-003: Unhandled Network Failures in Qdrant Store

Tests cover:
- Retry mechanism for transient failures
- Exponential backoff behavior
- Fallback on persistent failure
- Connection recovery
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from autopack.memory.qdrant_store import QdrantStore


@pytest.fixture
def mock_qdrant_client():
    """Fixture providing a mocked QdrantClient."""
    with patch("autopack.memory.qdrant_store.QdrantClient") as mock_client:
        yield mock_client


class TestQdrantRetryLogic:
    """Test retry decorator on critical operations."""

    def test_connect_with_retry_success_on_first_attempt(self, mock_qdrant_client):
        """Test successful connection on first attempt."""
        # Setup mock client
        instance = MagicMock()
        instance.get_collections.return_value = Mock(collections=[])
        mock_qdrant_client.return_value = instance

        # Mock HTTP health check
        with patch("requests.get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "ok"}
            mock_get.return_value = mock_response

            # Create store
            store = QdrantStore(host="localhost", port=6333)

            # Test connect method succeeds
            assert store.connect() is True

    def test_connect_with_retry_recovers_after_transient_failure(self, mock_qdrant_client):
        """Test connection recovery after transient network error."""
        # Setup mock client that fails twice then succeeds
        instance = MagicMock()

        # Make get_collections fail twice, then succeed
        get_collections_mock = Mock()
        get_collections_mock.collections = []
        instance.get_collections.side_effect = [
            ConnectionError("Connection refused"),
            ConnectionError("Connection refused"),
            get_collections_mock,  # Success on third attempt
        ]

        mock_qdrant_client.return_value = instance

        # Create store with mocked health check
        with patch.object(QdrantStore, "_check_qdrant_health", return_value=(True, "")):
            store = QdrantStore(host="localhost", port=6333)

        # Reset the mock for testing connect
        instance.get_collections.side_effect = [
            ConnectionError("Connection refused"),
            get_collections_mock,  # Success on second attempt
        ]

        # Test that connect eventually succeeds despite transient failures
        assert store.connect() is True

    def test_connect_fails_after_max_retries(self, mock_qdrant_client):
        """Test connection fails gracefully after exhausting retries."""
        # Setup mock client that always fails
        instance = MagicMock()
        instance.get_collections.side_effect = ConnectionError("Connection refused")

        mock_qdrant_client.return_value = instance

        # Create store with mocked health check
        with patch.object(QdrantStore, "_check_qdrant_health", return_value=(True, "")):
            store = QdrantStore(host="localhost", port=6333)

        # Test that connect returns False after all retries exhausted
        assert store.connect() is False

    def test_health_check_with_exponential_backoff(self, mock_qdrant_client):
        """Test health check retries with exponential backoff."""
        # Setup mock client
        instance = MagicMock()

        # Fail twice with connection errors, then succeed
        get_collections_mock = Mock()
        get_collections_mock.collections = []
        instance.get_collections.side_effect = [
            ConnectionError("Not ready"),
            ConnectionError("Still not ready"),
            get_collections_mock,
        ]

        mock_qdrant_client.return_value = instance

        # Create store - should succeed on third attempt
        with patch("time.sleep") as mock_sleep:
            with patch("requests.get") as mock_get:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"status": "ok"}
                mock_get.return_value = mock_response

                _ = QdrantStore(host="localhost", port=6333)

                # Verify exponential backoff delays
                # Expected: 1s, 2s
                calls = mock_sleep.call_args_list
                assert len(calls) == 2
                assert calls[0][0][0] == 1.0  # First retry delay: 1s
                assert calls[1][0][0] == 2.0  # Second retry delay: 2s

    def test_upsert_with_retry(self, mock_qdrant_client):
        """Test upsert retries on transient failure."""
        # Setup mock client
        instance = MagicMock()
        instance.get_collections.return_value = Mock(collections=[])

        # Make upsert fail once, then succeed
        instance.upsert.side_effect = [
            ConnectionError("Connection lost"),
            None,  # Success
        ]

        mock_qdrant_client.return_value = instance

        # Create store
        with patch.object(QdrantStore, "_check_qdrant_health", return_value=(True, "")):
            store = QdrantStore(host="localhost", port=6333)

        # Test upsert with retry
        points = [
            {
                "id": "test_1",
                "vector": [0.1, 0.2, 0.3],
                "payload": {"text": "test"},
            }
        ]

        # Reset mock for test
        instance.upsert.side_effect = [
            ConnectionError("Connection lost"),
            None,  # Success on retry
        ]

        # This should succeed despite first failure
        result = store.upsert("test_collection", points)
        assert result == 1

    def test_search_returns_empty_on_persistent_failure(self, mock_qdrant_client):
        """Test search returns empty list on persistent failure."""
        # Setup mock client
        instance = MagicMock()
        instance.get_collections.return_value = Mock(collections=[])

        # Make search always fail
        instance.query_points.side_effect = ConnectionError("Connection lost")

        mock_qdrant_client.return_value = instance

        # Create store
        with patch.object(QdrantStore, "_check_qdrant_health", return_value=(True, "")):
            store = QdrantStore(host="localhost", port=6333)

        # Test search returns empty list on all retries failing
        result = store.search("test_collection", [0.1, 0.2])
        assert result == []

    def test_scroll_returns_empty_on_persistent_failure(self, mock_qdrant_client):
        """Test scroll returns empty list on persistent failure."""
        # Setup mock client
        instance = MagicMock()
        instance.get_collections.return_value = Mock(collections=[])

        # Make scroll always fail
        instance.scroll.side_effect = ConnectionError("Connection lost")

        mock_qdrant_client.return_value = instance

        # Create store
        with patch.object(QdrantStore, "_check_qdrant_health", return_value=(True, "")):
            store = QdrantStore(host="localhost", port=6333)

        # Test scroll returns empty list on all retries failing
        result = store.scroll("test_collection")
        assert result == []


class TestQdrantFallback:
    """Test fallback behavior on persistent Qdrant failure."""

    def test_initialization_fails_when_qdrant_unavailable(self, mock_qdrant_client):
        """Test initialization raises RuntimeError when Qdrant unavailable."""
        # Setup mock client that always fails health check
        instance = MagicMock()
        instance.get_collections.side_effect = ConnectionError("Connection refused")

        mock_qdrant_client.return_value = instance

        # Initialization should raise RuntimeError
        with pytest.raises(RuntimeError, match="Qdrant health check failed"):
            QdrantStore(host="localhost", port=6333)

    def test_connect_logs_fallback_message(self, mock_qdrant_client, caplog):
        """Test that connect logs fallback message on persistent failure."""
        # Setup mock client that always fails
        instance = MagicMock()
        instance.get_collections.side_effect = ConnectionError("Connection lost")

        mock_qdrant_client.return_value = instance

        # Create store with mocked health check
        with patch.object(QdrantStore, "_check_qdrant_health", return_value=(True, "")):
            store = QdrantStore(host="localhost", port=6333)

        # Attempt to connect and verify fallback message in logs
        import logging

        with caplog.at_level(logging.ERROR):
            result = store.connect()

        assert result is False
        assert "Falling back to FAISS store" in caplog.text


class TestQdrantHealthCheck:
    """Test health check functionality."""

    def test_health_check_validates_connectivity(self, mock_qdrant_client):
        """Test health check validates both basic connectivity and HTTP endpoint."""
        # Setup mock client
        instance = MagicMock()
        get_collections_mock = Mock()
        get_collections_mock.collections = []
        instance.get_collections.return_value = get_collections_mock

        mock_qdrant_client.return_value = instance

        # Mock HTTP request
        with patch("requests.get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "ok"}
            mock_get.return_value = mock_response

            # Initialize store
            _ = QdrantStore(host="localhost", port=6333)

            # Verify connectivity check was called
            assert instance.get_collections.called

    def test_health_check_retries_on_http_timeout(self, mock_qdrant_client):
        """Test health check retries when HTTP endpoint times out."""
        # Setup mock client
        instance = MagicMock()
        get_collections_mock = Mock()
        get_collections_mock.collections = []
        instance.get_collections.return_value = get_collections_mock

        mock_qdrant_client.return_value = instance

        # Mock HTTP request that times out then succeeds
        with patch("requests.get") as mock_get:
            import requests

            mock_get.side_effect = [
                requests.exceptions.Timeout("Timeout"),
                Mock(status_code=200, json=Mock(return_value={"status": "ok"})),
            ]

            with patch("time.sleep"):
                # Initialize store - should succeed on retry
                _ = QdrantStore(host="localhost", port=6333)


class TestQdrantErrorHandling:
    """Test error handling in operations."""

    def test_count_returns_zero_on_failure(self, mock_qdrant_client):
        """Test count returns 0 on connection failure."""
        # Setup mock client
        instance = MagicMock()
        instance.get_collections.return_value = Mock(collections=[])

        # Make count always fail
        instance.count.side_effect = ConnectionError("Connection lost")

        mock_qdrant_client.return_value = instance

        # Create store
        with patch.object(QdrantStore, "_check_qdrant_health", return_value=(True, "")):
            store = QdrantStore(host="localhost", port=6333)

        # Test count returns 0 on failure
        result = store.count("test_collection")
        assert result == 0

    def test_delete_returns_zero_on_failure(self, mock_qdrant_client):
        """Test delete returns 0 on connection failure."""
        # Setup mock client
        instance = MagicMock()
        instance.get_collections.return_value = Mock(collections=[])

        # Make delete always fail
        instance.delete.side_effect = ConnectionError("Connection lost")

        mock_qdrant_client.return_value = instance

        # Create store
        with patch.object(QdrantStore, "_check_qdrant_health", return_value=(True, "")):
            store = QdrantStore(host="localhost", port=6333)

        # Test delete returns 0 on failure
        result = store.delete("test_collection", ["id1", "id2"])
        assert result == 0

    def test_get_payload_returns_none_on_failure(self, mock_qdrant_client):
        """Test get_payload returns None on connection failure."""
        # Setup mock client
        instance = MagicMock()
        instance.get_collections.return_value = Mock(collections=[])

        # Make retrieve always fail
        instance.retrieve.side_effect = ConnectionError("Connection lost")

        mock_qdrant_client.return_value = instance

        # Create store
        with patch.object(QdrantStore, "_check_qdrant_health", return_value=(True, "")):
            store = QdrantStore(host="localhost", port=6333)

        # Test get_payload returns None on failure
        result = store.get_payload("test_collection", "point_id")
        assert result is None
