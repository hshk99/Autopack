"""Tests for IMP-REL-002: Memory Service Retry with Backoff.

Tests cover:
- Retry behavior with exponential backoff for Qdrant connections
- Successful connection after transient failures
- Fallback to FAISS after retry exhaustion
"""

from unittest.mock import MagicMock, Mock

import pytest

from autopack.memory import memory_service as ms


class TestQdrantRetryWithBackoff:
    """Tests for IMP-REL-002: Memory Service Retry with Backoff."""

    def test_create_qdrant_store_with_retry_succeeds_first_attempt(self, monkeypatch):
        """Test that retry wrapper succeeds on first attempt."""
        monkeypatch.setattr(ms, "QDRANT_AVAILABLE", True, raising=False)

        mock_store = MagicMock()
        mock_qdrant_class = Mock(return_value=mock_store)
        monkeypatch.setattr(ms, "QdrantStore", mock_qdrant_class, raising=True)

        result = ms._create_qdrant_store_with_retry(
            host="localhost",
            port=6333,
            api_key=None,
            prefer_grpc=False,
            timeout=60,
        )

        assert result == mock_store
        assert mock_qdrant_class.call_count == 1

    def test_create_qdrant_store_with_retry_succeeds_after_transient_failure(self, monkeypatch):
        """Test that retry wrapper succeeds after transient connection failures."""
        monkeypatch.setattr(ms, "QDRANT_AVAILABLE", True, raising=False)

        call_count = {"n": 0}
        mock_store = MagicMock()

        def flaky_qdrant(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise ConnectionError("transient connection failure")
            return mock_store

        monkeypatch.setattr(ms, "QdrantStore", flaky_qdrant, raising=True)

        result = ms._create_qdrant_store_with_retry(
            host="localhost",
            port=6333,
            api_key=None,
            prefer_grpc=False,
            timeout=60,
            max_attempts=3,
        )

        assert result == mock_store
        assert call_count["n"] == 3  # Failed twice, succeeded on third

    def test_create_qdrant_store_with_retry_raises_after_max_attempts(self, monkeypatch):
        """Test that retry wrapper raises exception after max attempts exhausted."""
        monkeypatch.setattr(ms, "QDRANT_AVAILABLE", True, raising=False)

        call_count = {"n": 0}

        def always_fail(*args, **kwargs):
            call_count["n"] += 1
            raise ConnectionError("persistent connection failure")

        monkeypatch.setattr(ms, "QdrantStore", always_fail, raising=True)

        with pytest.raises(ConnectionError) as exc_info:
            ms._create_qdrant_store_with_retry(
                host="localhost",
                port=6333,
                api_key=None,
                prefer_grpc=False,
                timeout=60,
                max_attempts=3,
            )

        assert "persistent connection failure" in str(exc_info.value)
        assert call_count["n"] == 3  # All 3 attempts made

    def test_memory_service_uses_retry_wrapper_for_qdrant(self, monkeypatch):
        """Test that MemoryService uses retry wrapper when connecting to Qdrant."""
        monkeypatch.setattr(ms, "QDRANT_AVAILABLE", True, raising=False)
        monkeypatch.delenv("AUTOPACK_ENABLE_MEMORY", raising=False)
        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        call_count = {"n": 0}
        mock_store = MagicMock()
        mock_store.ensure_collection = Mock()

        def flaky_qdrant(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise ConnectionError("transient failure")
            return mock_store

        monkeypatch.setattr(ms, "QdrantStore", flaky_qdrant, raising=True)

        service = ms.MemoryService(use_qdrant=True)

        assert service.backend == "qdrant"
        assert call_count["n"] == 2  # Failed once, succeeded on second

    def test_memory_service_falls_back_to_faiss_after_retry_exhaustion(self, monkeypatch):
        """Test that MemoryService falls back to FAISS after retries are exhausted."""
        monkeypatch.setattr(ms, "QDRANT_AVAILABLE", True, raising=False)
        monkeypatch.delenv("AUTOPACK_ENABLE_MEMORY", raising=False)
        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        call_count = {"n": 0}

        def always_fail(*args, **kwargs):
            call_count["n"] += 1
            raise ConnectionError("persistent connection failure")

        monkeypatch.setattr(ms, "QdrantStore", always_fail, raising=True)

        # Disable autostart so we only get the initial 3 retry attempts
        monkeypatch.setattr(ms, "_autostart_qdrant_if_needed", lambda **kwargs: False, raising=True)

        # Ensure fallback is enabled (default behavior)
        service = ms.MemoryService(use_qdrant=True)

        assert service.backend == "faiss"
        assert service.enabled is True
        # Should have made 3 retry attempts (no autostart = no second round)
        assert call_count["n"] == 3

    def test_memory_service_retry_with_autostart(self, monkeypatch):
        """Test retry behavior when Qdrant autostart is triggered."""
        monkeypatch.setattr(ms, "QDRANT_AVAILABLE", True, raising=False)
        monkeypatch.setenv("AUTOPACK_QDRANT_AUTOSTART", "1")
        monkeypatch.setenv("AUTOPACK_QDRANT_HOST", "localhost")
        monkeypatch.setenv("AUTOPACK_QDRANT_PORT", "6333")
        monkeypatch.delenv("AUTOPACK_ENABLE_MEMORY", raising=False)

        call_count = {"n": 0}
        mock_store = MagicMock()
        mock_store.ensure_collection = Mock()

        def flaky_qdrant(*args, **kwargs):
            call_count["n"] += 1
            # First 3 attempts fail (initial retry exhausted)
            # Then autostart triggers, next attempt fails, then succeeds
            if call_count["n"] <= 3:
                raise ConnectionError("initial connection failure")
            if call_count["n"] == 4:
                raise ConnectionError("post-autostart transient failure")
            return mock_store

        monkeypatch.setattr(ms, "QdrantStore", flaky_qdrant, raising=True)

        # Pretend autostart succeeded
        monkeypatch.setattr(ms, "_autostart_qdrant_if_needed", lambda **kwargs: True, raising=True)

        service = ms.MemoryService(use_qdrant=True)

        assert service.backend == "qdrant"
        # 3 initial retries + 2 post-autostart retries (fail once, succeed once)
        # But with max_attempts=3 for post-autostart, it should succeed on attempt 5 or 6
        assert call_count["n"] >= 4

    def test_create_qdrant_store_with_custom_max_attempts(self, monkeypatch):
        """Test that custom max_attempts parameter is respected."""
        monkeypatch.setattr(ms, "QDRANT_AVAILABLE", True, raising=False)

        call_count = {"n": 0}

        def always_fail(*args, **kwargs):
            call_count["n"] += 1
            raise ConnectionError("connection failure")

        monkeypatch.setattr(ms, "QdrantStore", always_fail, raising=True)

        with pytest.raises(ConnectionError):
            ms._create_qdrant_store_with_retry(
                host="localhost",
                port=6333,
                api_key=None,
                prefer_grpc=False,
                timeout=60,
                max_attempts=5,  # Custom max attempts
            )

        assert call_count["n"] == 5  # All 5 attempts made

    def test_retry_handles_different_exception_types(self, monkeypatch):
        """Test that retry handles various connection-related exceptions."""
        monkeypatch.setattr(ms, "QDRANT_AVAILABLE", True, raising=False)

        call_count = {"n": 0}
        mock_store = MagicMock()

        exceptions = [
            TimeoutError("connection timeout"),
            OSError("network unreachable"),
        ]

        def varying_failures(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] <= len(exceptions):
                raise exceptions[call_count["n"] - 1]
            return mock_store

        monkeypatch.setattr(ms, "QdrantStore", varying_failures, raising=True)

        result = ms._create_qdrant_store_with_retry(
            host="localhost",
            port=6333,
            api_key=None,
            prefer_grpc=False,
            timeout=60,
            max_attempts=3,
        )

        assert result == mock_store
        assert call_count["n"] == 3  # Two failures, then success
