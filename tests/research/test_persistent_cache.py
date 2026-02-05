"""Tests for persistent cache for bootstrap research.

Tests the PersistentCache, PersistentCacheMetadata, and PersistentCacheManager classes
for disk-backed caching of bootstrap sessions.
"""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from autopack.research.idea_parser import ParsedIdea, ProjectType, RiskProfile
from autopack.research.models.bootstrap_session import (
    BootstrapPhase,
    BootstrapSession,
    generate_idea_hash,
)
from autopack.research.persistent_cache import (
    PersistentCache,
    PersistentCacheManager,
    PersistentCacheMetadata,
)


class TestPersistentCacheMetadata:
    """Test suite for PersistentCacheMetadata."""

    def test_create_metadata(self):
        """Test creating metadata."""
        now = datetime.now()
        expires = now + timedelta(hours=24)
        path = Path("/tmp/cache.json")

        metadata = PersistentCacheMetadata(
            idea_hash="abc123",
            created_at=now,
            expires_at=expires,
            session_id="session-1",
            file_path=path,
        )

        assert metadata.idea_hash == "abc123"
        assert metadata.session_id == "session-1"
        assert metadata.is_expired() is False

    def test_metadata_expired_check(self):
        """Test metadata expiration."""
        now = datetime.now()
        past = now - timedelta(hours=1)
        path = Path("/tmp/cache.json")

        metadata = PersistentCacheMetadata(
            idea_hash="abc123",
            created_at=past,
            expires_at=past,
            session_id="session-1",
            file_path=path,
        )

        assert metadata.is_expired() is True

    def test_metadata_to_dict(self):
        """Test metadata serialization."""
        now = datetime.now()
        expires = now + timedelta(hours=24)
        path = Path("/tmp/cache.json")

        metadata = PersistentCacheMetadata(
            idea_hash="abc123",
            created_at=now,
            expires_at=expires,
            session_id="session-1",
            file_path=path,
        )

        data = metadata.to_dict()
        assert data["idea_hash"] == "abc123"
        assert data["session_id"] == "session-1"
        assert "created_at" in data
        assert "expires_at" in data
        assert "is_expired" in data

    def test_metadata_from_dict(self):
        """Test metadata deserialization."""
        now = datetime.now()
        expires = now + timedelta(hours=24)
        path = Path("/tmp/cache.json")

        original = PersistentCacheMetadata(
            idea_hash="abc123",
            created_at=now,
            expires_at=expires,
            session_id="session-1",
            file_path=path,
        )

        data = original.to_dict()
        restored = PersistentCacheMetadata.from_dict(data, path)

        assert restored.idea_hash == original.idea_hash
        assert restored.session_id == original.session_id
        assert restored.file_path == original.file_path


class TestPersistentCache:
    """Test suite for PersistentCache."""

    @pytest.fixture
    def temp_cache_dir(self):
        """Create a temporary cache directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_initialize_cache(self, temp_cache_dir):
        """Test cache initialization."""
        cache = PersistentCache(cache_dir=temp_cache_dir, auto_load=False)
        assert cache.cache_dir == temp_cache_dir
        assert cache.ttl_hours == 24
        assert cache.get_size() == 0

    def test_set_and_get_session(self, temp_cache_dir):
        """Test setting and getting a session."""
        cache = PersistentCache(cache_dir=temp_cache_dir, auto_load=False)

        session = BootstrapSession(
            session_id="test-session",
            idea_hash="test-hash",
            parsed_idea_title="Test Project",
            parsed_idea_type="ecommerce",
        )

        cache.set("test-hash", session)
        retrieved = cache.get("test-hash")

        assert retrieved is not None
        assert retrieved.session_id == "test-session"
        assert retrieved.parsed_idea_title == "Test Project"

    def test_cache_persists_to_disk(self, temp_cache_dir):
        """Test that cache is saved to disk."""
        cache = PersistentCache(cache_dir=temp_cache_dir, auto_load=False)

        session = BootstrapSession(
            session_id="test-session",
            idea_hash="test-hash",
            parsed_idea_title="Test Project",
            parsed_idea_type="ecommerce",
        )

        cache.set("test-hash", session)

        # Check that file was created
        cache_file = temp_cache_dir / "test-hash.json"
        assert cache_file.exists()

        # Verify file contents
        with open(cache_file, "r") as f:
            data = json.load(f)
            assert "_metadata" in data
            assert "_session" in data
            assert data["_session"]["parsed_idea_title"] == "Test Project"

    def test_cache_load_from_disk(self, temp_cache_dir):
        """Test loading cache from disk on startup."""
        # Create and populate cache
        cache1 = PersistentCache(cache_dir=temp_cache_dir, auto_load=False)
        session = BootstrapSession(
            session_id="test-session",
            idea_hash="test-hash",
            parsed_idea_title="Test Project",
            parsed_idea_type="ecommerce",
        )
        cache1.set("test-hash", session)

        # Create new cache instance with auto_load=True
        cache2 = PersistentCache(cache_dir=temp_cache_dir, auto_load=True)

        # Should load from disk
        retrieved = cache2.get("test-hash")
        assert retrieved is not None
        assert retrieved.session_id == "test-session"
        assert retrieved.parsed_idea_title == "Test Project"

    def test_cache_expiry_on_startup(self, temp_cache_dir):
        """Test that expired entries are skipped on startup."""
        # Create cache with expired entry
        cache1 = PersistentCache(cache_dir=temp_cache_dir, auto_load=False)

        session = BootstrapSession(
            session_id="test-session",
            idea_hash="test-hash",
            parsed_idea_title="Test Project",
            parsed_idea_type="ecommerce",
        )
        cache1.set("test-hash", session)

        # Manually expire the entry
        cache_file = temp_cache_dir / "test-hash.json"
        with open(cache_file, "r") as f:
            data = json.load(f)

        # Set expiry to past
        data["_metadata"]["expires_at"] = (datetime.now() - timedelta(hours=1)).isoformat()

        with open(cache_file, "w") as f:
            json.dump(data, f)

        # Create new cache with auto_load=True
        cache2 = PersistentCache(cache_dir=temp_cache_dir, auto_load=True)

        # Should skip expired entry
        retrieved = cache2.get("test-hash")
        assert retrieved is None

        # File should be deleted
        assert not cache_file.exists()

    def test_cache_invalidate(self, temp_cache_dir):
        """Test cache invalidation."""
        cache = PersistentCache(cache_dir=temp_cache_dir, auto_load=False)

        session = BootstrapSession(
            session_id="test-session",
            idea_hash="test-hash",
            parsed_idea_title="Test Project",
            parsed_idea_type="ecommerce",
        )

        cache.set("test-hash", session)
        assert cache.get("test-hash") is not None

        result = cache.invalidate("test-hash")
        assert result is True
        assert cache.get("test-hash") is None

        # File should be deleted
        cache_file = temp_cache_dir / "test-hash.json"
        assert not cache_file.exists()

    def test_cache_clear(self, temp_cache_dir):
        """Test clearing cache."""
        cache = PersistentCache(cache_dir=temp_cache_dir, auto_load=False)

        for i in range(3):
            session = BootstrapSession(
                session_id=f"session-{i}",
                idea_hash=f"hash-{i}",
                parsed_idea_title=f"Project {i}",
                parsed_idea_type="ecommerce",
            )
            cache.set(f"hash-{i}", session)

        cache.clear()

        assert cache.get_size() == 0

        # All files should be deleted
        for i in range(3):
            cache_file = temp_cache_dir / f"hash-{i}.json"
            assert not cache_file.exists()

    def test_cache_cleanup_expired(self, temp_cache_dir):
        """Test cleanup of expired entries."""
        cache = PersistentCache(cache_dir=temp_cache_dir, auto_load=False, ttl_hours=24)

        # Add sessions
        for i in range(3):
            session = BootstrapSession(
                session_id=f"session-{i}",
                idea_hash=f"hash-{i}",
                parsed_idea_title=f"Project {i}",
                parsed_idea_type="ecommerce",
            )
            cache.set(f"hash-{i}", session)

        # Expire first two entries
        cache._metadata["hash-0"].expires_at = datetime.now() - timedelta(hours=1)
        cache._metadata["hash-1"].expires_at = datetime.now() - timedelta(hours=1)

        removed = cache.cleanup_expired()
        assert removed == 2

        assert cache.get("hash-0") is None
        assert cache.get("hash-1") is None
        assert cache.get("hash-2") is not None

    def test_cache_stats(self, temp_cache_dir):
        """Test cache statistics."""
        cache = PersistentCache(cache_dir=temp_cache_dir, auto_load=False)

        session = BootstrapSession(
            session_id="test-session",
            idea_hash="test-hash",
            parsed_idea_title="Test Project",
            parsed_idea_type="ecommerce",
        )

        cache.set("test-hash", session)
        _ = cache.get("test-hash")  # Cache hit
        _ = cache.get("nonexistent")  # Cache miss

        stats = cache.get_stats()
        assert stats["cache_size"] == 1
        assert stats["cache_hits"] == 1
        assert stats["cache_misses"] == 1
        assert stats["disk_writes"] == 1
        assert stats["hit_rate_percent"] == 50.0


class TestPersistentCacheManager:
    """Test suite for PersistentCacheManager."""

    @pytest.fixture
    def temp_cache_dir(self):
        """Create a temporary cache directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_manager_initialization(self, temp_cache_dir):
        """Test manager initialization."""
        manager = PersistentCacheManager(cache_dir=temp_cache_dir)
        assert manager.persistent_cache is not None
        assert manager.optimized_cache is not None

    def test_manager_set_and_get(self, temp_cache_dir):
        """Test manager set and get operations."""
        manager = PersistentCacheManager(cache_dir=temp_cache_dir)

        session = BootstrapSession(
            session_id="test-session",
            idea_hash="test-hash",
            parsed_idea_title="Test Project",
            parsed_idea_type="ecommerce",
        )

        manager.set("test-hash", session)
        retrieved = manager.get("test-hash")

        assert retrieved is not None
        assert retrieved.session_id == "test-session"

    def test_manager_fallback_to_persistent(self, temp_cache_dir):
        """Test manager falls back to persistent cache."""
        manager = PersistentCacheManager(cache_dir=temp_cache_dir)

        session = BootstrapSession(
            session_id="test-session",
            idea_hash="test-hash",
            parsed_idea_title="Test Project",
            parsed_idea_type="ecommerce",
        )

        # Add to persistent cache only
        manager.persistent_cache.set("test-hash", session)
        manager.optimized_cache.clear()

        # Should retrieve from persistent cache
        retrieved = manager.get("test-hash")
        assert retrieved is not None
        assert retrieved.session_id == "test-session"

        # Should now be in optimized cache too
        assert manager.optimized_cache.get("test-hash") is not None

    def test_manager_invalidate(self, temp_cache_dir):
        """Test manager invalidation."""
        manager = PersistentCacheManager(cache_dir=temp_cache_dir)

        session = BootstrapSession(
            session_id="test-session",
            idea_hash="test-hash",
            parsed_idea_title="Test Project",
            parsed_idea_type="ecommerce",
        )

        manager.set("test-hash", session)
        assert manager.get("test-hash") is not None

        result = manager.invalidate("test-hash")
        assert result is True
        assert manager.get("test-hash") is None

    def test_manager_clear(self, temp_cache_dir):
        """Test manager clearing both caches."""
        manager = PersistentCacheManager(cache_dir=temp_cache_dir)

        for i in range(2):
            session = BootstrapSession(
                session_id=f"session-{i}",
                idea_hash=f"hash-{i}",
                parsed_idea_title=f"Project {i}",
                parsed_idea_type="ecommerce",
            )
            manager.set(f"hash-{i}", session)

        manager.clear()

        assert manager.get("hash-0") is None
        assert manager.get("hash-1") is None

    def test_manager_cleanup_expired(self, temp_cache_dir):
        """Test manager cleanup of both caches."""
        manager = PersistentCacheManager(cache_dir=temp_cache_dir)

        session = BootstrapSession(
            session_id="test-session",
            idea_hash="test-hash",
            parsed_idea_title="Test Project",
            parsed_idea_type="ecommerce",
        )

        manager.set("test-hash", session)

        # Expire entry in both caches
        manager.persistent_cache._metadata["test-hash"].expires_at = (
            datetime.now() - timedelta(hours=1)
        )
        manager.optimized_cache._cache["test-hash"].expires_at = (
            datetime.now() - timedelta(hours=1)
        )

        removed = manager.cleanup_expired()
        assert removed > 0
        assert manager.get("test-hash") is None

    def test_manager_stats(self, temp_cache_dir):
        """Test manager statistics."""
        manager = PersistentCacheManager(cache_dir=temp_cache_dir)

        session = BootstrapSession(
            session_id="test-session",
            idea_hash="test-hash",
            parsed_idea_title="Test Project",
            parsed_idea_type="ecommerce",
        )

        manager.set("test-hash", session)
        _ = manager.get("test-hash")

        stats = manager.get_stats()
        assert "optimized_cache" in stats
        assert "persistent_cache" in stats
        assert stats["persistent_cache"]["cache_size"] == 1
