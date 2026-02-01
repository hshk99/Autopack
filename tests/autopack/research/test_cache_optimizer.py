"""Tests for research cache optimization module.

Tests LRU eviction, compression, and cache metrics functionality.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from autopack.research.cache_optimizer import (
    CacheEntry,
    CacheMetrics,
    CacheOptimizer,
    OptimizedResearchCache,
)
from autopack.research.models.bootstrap_session import BootstrapSession


class TestCacheMetrics:
    """Tests for cache metrics tracking."""

    def test_initial_metrics_zero(self):
        """Test that initial metrics are zero."""
        metrics = CacheMetrics()
        assert metrics.hits == 0
        assert metrics.misses == 0
        assert metrics.evictions == 0
        assert metrics.compressions == 0
        assert metrics.decompressions == 0

    def test_record_hit(self):
        """Test recording a cache hit."""
        metrics = CacheMetrics()
        metrics.record_hit()
        assert metrics.hits == 1

    def test_record_miss(self):
        """Test recording a cache miss."""
        metrics = CacheMetrics()
        metrics.record_miss()
        assert metrics.misses == 1

    def test_record_eviction(self):
        """Test recording an LRU eviction."""
        metrics = CacheMetrics()
        metrics.record_eviction()
        assert metrics.evictions == 1

    def test_record_compression(self):
        """Test recording compression."""
        metrics = CacheMetrics()
        metrics.record_compression(1000, 500)
        assert metrics.compressions == 1
        assert metrics.total_bytes_saved_by_compression == 500

    def test_get_hit_rate(self):
        """Test hit rate calculation."""
        metrics = CacheMetrics()

        # No requests
        assert metrics.get_hit_rate() == 0.0

        # 50% hit rate
        metrics.record_hit()
        metrics.record_miss()
        assert metrics.get_hit_rate() == 50.0

        # 100% hit rate
        metrics.record_hit()
        assert metrics.get_hit_rate() == 66.67

    def test_get_stats(self):
        """Test getting metrics stats."""
        metrics = CacheMetrics()
        metrics.record_hit()
        metrics.record_miss()
        metrics.record_compression(1000, 800)

        stats = metrics.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["total_requests"] == 2
        assert stats["hit_rate_percent"] == 50.0
        assert stats["compressions"] == 1
        assert stats["total_bytes_saved_by_compression"] == 200


class TestOptimizedResearchCache:
    """Tests for optimized research cache."""

    def create_test_session(self, session_id: str = "test") -> BootstrapSession:
        """Create a test bootstrap session."""
        session = MagicMock(spec=BootstrapSession)
        session.id = session_id
        session.expires_at = datetime.now() + timedelta(hours=24)
        session.is_cached_valid = MagicMock(return_value=True)
        return session

    def test_cache_initialization(self):
        """Test cache initializes with correct defaults."""
        cache = OptimizedResearchCache()
        assert cache.ttl_hours == 24
        assert cache.max_size == 100
        assert cache.enable_compression is True
        assert cache.get_size() == 0

    def test_cache_get_and_set(self):
        """Test basic get and set operations."""
        cache = OptimizedResearchCache()
        session = self.create_test_session()

        # Should be empty initially
        assert cache.get("test_hash") is None

        # Set and retrieve
        cache.set("test_hash", session)
        assert cache.get_size() == 1

        # Should get the session back
        retrieved = cache.get("test_hash")
        assert retrieved is not None

    def test_cache_hit_miss_tracking(self):
        """Test cache hit and miss tracking."""
        cache = OptimizedResearchCache()
        session = self.create_test_session()

        # Miss
        cache.get("nonexistent")
        stats = cache.get_stats()
        assert stats["misses"] == 1
        assert stats["hits"] == 0

        # Set and hit
        cache.set("test_hash", session)
        cache.get("test_hash")
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    def test_lru_eviction(self):
        """Test LRU eviction policy."""
        cache = OptimizedResearchCache(max_size=3)

        # Add 3 entries
        for i in range(3):
            session = self.create_test_session(f"session_{i}")
            cache.set(f"hash_{i}", session)

        assert cache.get_size() == 3

        # Add 4th entry - should evict least recently used (hash_0)
        session = self.create_test_session("session_3")
        cache.set("hash_3", session)

        assert cache.get_size() == 3
        assert cache.get("hash_0") is None  # LRU evicted
        assert cache.get("hash_1") is not None
        assert cache.get("hash_2") is not None
        assert cache.get("hash_3") is not None

        # Verify eviction was tracked
        stats = cache.get_stats()
        assert stats["evictions"] == 1

    def test_lru_order_update_on_access(self):
        """Test that accessing an entry updates its position in LRU order."""
        cache = OptimizedResearchCache(max_size=2)

        session_0 = self.create_test_session("session_0")
        session_1 = self.create_test_session("session_1")
        session_2 = self.create_test_session("session_2")

        cache.set("hash_0", session_0)
        cache.set("hash_1", session_1)

        # Access hash_0 to mark it as recently used
        cache.get("hash_0")

        # Add new entry - should evict hash_1 (least recently used after access)
        cache.set("hash_2", session_2)

        assert cache.get("hash_0") is not None  # hash_0 should still exist
        assert cache.get("hash_1") is None  # hash_1 should be evicted
        assert cache.get("hash_2") is not None

    def test_cache_invalidation(self):
        """Test cache entry invalidation."""
        cache = OptimizedResearchCache()
        session = self.create_test_session()

        cache.set("test_hash", session)
        assert cache.get_size() == 1

        # Invalidate
        result = cache.invalidate("test_hash")
        assert result is True
        assert cache.get_size() == 0

        # Invalidate non-existent entry
        result = cache.invalidate("nonexistent")
        assert result is False

    def test_cache_clear(self):
        """Test clearing entire cache."""
        cache = OptimizedResearchCache()

        for i in range(5):
            session = self.create_test_session(f"session_{i}")
            cache.set(f"hash_{i}", session)

        assert cache.get_size() == 5

        cache.clear()
        assert cache.get_size() == 0

    def test_cache_cleanup_expired(self):
        """Test cleanup of expired entries."""
        cache = OptimizedResearchCache(ttl_hours=1)
        session = self.create_test_session()

        cache.set("test_hash", session)
        assert cache.get_size() == 1

        # Manually set expiration to past
        entry = cache._cache["test_hash"]
        entry.expires_at = datetime.now() - timedelta(hours=1)

        # Cleanup
        removed = cache.cleanup_expired()
        assert removed == 1
        assert cache.get_size() == 0

    def test_cache_get_stats(self):
        """Test cache statistics."""
        cache = OptimizedResearchCache()
        session = self.create_test_session()

        cache.set("test_hash", session)
        cache.get("test_hash")  # Hit
        cache.get("nonexistent")  # Miss

        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["cache_size"] == 1
        assert stats["max_cache_size"] == 100
        assert stats["ttl_hours"] == 24


class TestCacheEntry:
    """Tests for individual cache entries."""

    def create_test_session(self) -> BootstrapSession:
        """Create a test bootstrap session."""
        session = MagicMock(spec=BootstrapSession)
        session.id = "test"
        return session

    def test_cache_entry_creation(self):
        """Test cache entry creation."""
        metrics = CacheMetrics()
        session = self.create_test_session()

        entry = CacheEntry(
            session=session,
            ttl_hours=24,
            compression_threshold=100000,
            enable_compression=False,
            metrics=metrics,
        )

        assert entry.created_at is not None
        assert entry.expires_at is not None
        assert not entry.is_compressed
        assert not entry.is_expired()

    def test_cache_entry_expiration(self):
        """Test cache entry expiration check."""
        metrics = CacheMetrics()
        session = self.create_test_session()

        entry = CacheEntry(
            session=session,
            ttl_hours=24,
            compression_threshold=100000,
            enable_compression=False,
            metrics=metrics,
        )

        assert not entry.is_expired()

        # Manually set to expired
        entry.expires_at = datetime.now() - timedelta(hours=1)
        assert entry.is_expired()

    def test_cache_entry_get_session(self):
        """Test retrieving session from cache entry."""
        metrics = CacheMetrics()
        session = self.create_test_session()

        entry = CacheEntry(
            session=session,
            ttl_hours=24,
            compression_threshold=100000,
            enable_compression=False,
            metrics=metrics,
        )

        retrieved = entry.get_session()
        assert retrieved is not None

    def test_cache_entry_expired_returns_none(self):
        """Test that expired entries return None."""
        metrics = CacheMetrics()
        session = self.create_test_session()

        entry = CacheEntry(
            session=session,
            ttl_hours=24,
            compression_threshold=100000,
            enable_compression=False,
            metrics=metrics,
        )

        # Expire the entry
        entry.expires_at = datetime.now() - timedelta(hours=1)

        # Should return None for expired entry
        retrieved = entry.get_session()
        assert retrieved is None

    def test_cache_entry_info(self):
        """Test cache entry info dictionary."""
        metrics = CacheMetrics()
        session = self.create_test_session()

        entry = CacheEntry(
            session=session,
            ttl_hours=24,
            compression_threshold=100000,
            enable_compression=False,
            metrics=metrics,
        )

        info = entry.get_info()
        assert "created_at" in info
        assert "expires_at" in info
        assert "ttl_hours" in info
        assert "is_compressed" in info
        assert "size_bytes" in info
        assert "is_expired" in info


class TestCacheOptimizer:
    """Tests for cache optimization analysis."""

    def create_test_cache_with_data(self) -> OptimizedResearchCache:
        """Create a test cache with sample data."""
        cache = OptimizedResearchCache()
        session = MagicMock(spec=BootstrapSession)

        for i in range(5):
            cache.set(f"hash_{i}", session)

        # Add some hits and misses
        for i in range(3):
            cache.get(f"hash_{i}")

        for _ in range(2):
            cache.get("nonexistent")

        return cache

    def test_analyze_cache(self):
        """Test cache performance analysis."""
        cache = self.create_test_cache_with_data()

        analysis = CacheOptimizer.analyze_cache(cache)

        assert "stats" in analysis
        assert "recommendations" in analysis
        assert "timestamp" in analysis
        assert isinstance(analysis["recommendations"], list)

    def test_suggest_tuning(self):
        """Test cache tuning suggestions."""
        cache = self.create_test_cache_with_data()

        suggestions = CacheOptimizer.suggest_tuning(cache)

        assert "current_config" in suggestions
        assert "suggested_config" in suggestions
        assert "rationale" in suggestions
        assert "max_size" in suggestions["current_config"]
        assert "compression_enabled" in suggestions["current_config"]


class TestCacheCompressionPerformance:
    """Tests for compression performance."""

    def test_compression_disabled(self):
        """Test cache with compression disabled."""
        cache = OptimizedResearchCache(
            enable_compression=False,
        )
        session = MagicMock(spec=BootstrapSession)

        cache.set("test_hash", session)

        entry = cache._cache["test_hash"]
        assert not entry.is_compressed

        stats = cache.get_stats()
        assert stats["compressions"] == 0

    def test_compression_enabled(self):
        """Test cache with compression enabled."""
        cache = OptimizedResearchCache(
            enable_compression=True,
            compression_threshold=100,  # Low threshold for testing
        )
        session = MagicMock(spec=BootstrapSession)

        cache.set("test_hash", session)

        # Check that compression was attempted (may not be used if not beneficial)
        stats = cache.get_stats()
        assert stats["compression_enabled"] is True

    def test_compression_threshold(self):
        """Test compression only triggers above threshold."""
        cache = OptimizedResearchCache(
            enable_compression=True,
            compression_threshold=10 * 1024 * 1024,  # 10MB threshold
        )
        session = MagicMock(spec=BootstrapSession)

        cache.set("test_hash", session)

        # Small object shouldn't be compressed with high threshold
        entry = cache._cache["test_hash"]
        assert not entry.is_compressed


class TestCacheIntegration:
    """Integration tests for cache functionality."""

    def test_multiple_operations_sequence(self):
        """Test a sequence of cache operations."""
        cache = OptimizedResearchCache(max_size=5)
        session_template = MagicMock(spec=BootstrapSession)

        # Set 5 entries
        for i in range(5):
            cache.set(f"hash_{i}", session_template)

        # Verify all exist
        assert cache.get_size() == 5

        # Access some (updates LRU)
        cache.get("hash_1")
        cache.get("hash_3")

        # Add one more (should evict LRU)
        cache.set("hash_5", session_template)

        # hash_0 should be evicted (wasn't accessed)
        assert cache.get("hash_0") is None
        assert cache.get("hash_1") is not None
        assert cache.get("hash_3") is not None

        # Verify stats
        stats = cache.get_stats()
        assert stats["cache_size"] == 5
        assert stats["evictions"] >= 1

    def test_cache_with_varying_ttl(self):
        """Test cache with different TTL values."""
        cache = OptimizedResearchCache(ttl_hours=1)
        session = MagicMock(spec=BootstrapSession)

        cache.set("test_hash", session)

        # Verify TTL is set
        entry = cache._cache["test_hash"]
        assert entry.ttl_hours == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
