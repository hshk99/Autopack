"""Persistent cache for bootstrap research sessions.

This module provides persistent caching capabilities for research results,
allowing bootstrap sessions to be cached and reused across application restarts.

Features:
- Disk-backed cache with automatic serialization
- Cache directory management and cleanup
- TTL enforcement across restarts
- Integration with OptimizedResearchCache
- Metrics and monitoring for disk operations
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from autopack.research.cache_optimizer import OptimizedResearchCache
from autopack.research.models.bootstrap_session import BootstrapSession

logger = logging.getLogger(__name__)

# Default cache directory
DEFAULT_CACHE_DIR = Path.home() / ".autopack" / "research_cache"

# Default TTL: 24 hours
DEFAULT_CACHE_TTL_HOURS = 24


class PersistentCacheMetadata:
    """Metadata for a cached session file."""

    def __init__(
        self,
        idea_hash: str,
        created_at: datetime,
        expires_at: datetime,
        session_id: str,
        file_path: Path,
    ):
        """Initialize cache metadata.

        Args:
            idea_hash: Hash of the idea that was cached
            created_at: When the cache entry was created
            expires_at: When the cache entry expires
            session_id: ID of the bootstrapsession
            file_path: Path to the cache file
        """
        self.idea_hash = idea_hash
        self.created_at = created_at
        self.expires_at = expires_at
        self.session_id = session_id
        self.file_path = file_path

    def is_expired(self) -> bool:
        """Check if cache entry has expired.

        Returns:
            True if cache entry has expired
        """
        return datetime.now() >= self.expires_at

    def to_dict(self) -> dict[str, Any]:
        """Convert metadata to dictionary.

        Returns:
            Dictionary representation of metadata
        """
        return {
            "idea_hash": self.idea_hash,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "session_id": self.session_id,
            "file_path": str(self.file_path),
            "is_expired": self.is_expired(),
        }

    @staticmethod
    def from_dict(data: dict[str, Any], file_path: Path) -> PersistentCacheMetadata:
        """Create metadata from dictionary.

        Args:
            data: Dictionary with metadata fields
            file_path: Path to the cache file

        Returns:
            PersistentCacheMetadata instance
        """
        return PersistentCacheMetadata(
            idea_hash=data["idea_hash"],
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
            session_id=data["session_id"],
            file_path=file_path,
        )


class PersistentCache:
    """Persistent cache for bootstrap research sessions.

    Provides disk-backed caching with automatic serialization and TTL enforcement.
    Integrates with OptimizedResearchCache for in-memory performance.
    """

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        ttl_hours: int = DEFAULT_CACHE_TTL_HOURS,
        auto_load: bool = True,
    ):
        """Initialize persistent cache.

        Args:
            cache_dir: Directory for cache files (default: ~/.autopack/research_cache)
            ttl_hours: Time-to-live in hours for cache entries
            auto_load: Whether to automatically load cache from disk on init
        """
        self.cache_dir = cache_dir or DEFAULT_CACHE_DIR
        self.ttl_hours = ttl_hours

        # Create cache directory if it doesn't exist
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # In-memory cache for session data
        self._sessions: dict[str, dict[str, Any]] = {}

        # In-memory cache for metadata
        self._metadata: dict[str, PersistentCacheMetadata] = {}

        # Metrics
        self._disk_reads = 0
        self._disk_writes = 0
        self._cache_hits = 0
        self._cache_misses = 0
        self._expired_cleanups = 0

        # Auto-load existing cache if requested
        if auto_load:
            self._load_cache_from_disk()

    def get(self, idea_hash: str) -> Optional[BootstrapSession]:
        """Get cached session if valid.

        Checks in-memory cache first, then loads from disk if needed.
        Returns None if not found or expired.

        Args:
            idea_hash: Hash of the parsed idea

        Returns:
            Cached BootstrapSession if valid, None otherwise
        """
        # Check metadata to see if it's expired
        metadata = self._metadata.get(idea_hash)
        if metadata and metadata.is_expired():
            logger.debug(f"Cache entry expired for idea hash: {idea_hash[:8]}...")
            self._delete_cache_entry(idea_hash)
            self._cache_misses += 1
            return None

        # Check in-memory cache
        if idea_hash in self._sessions:
            self._cache_hits += 1
            logger.debug(f"Cache hit (in-memory) for idea hash: {idea_hash[:8]}...")
            return self._deserialize_session(self._sessions[idea_hash])

        # Try loading from disk
        if metadata and metadata.file_path.exists():
            try:
                session_data = self._load_session_from_disk(metadata.file_path)
                if session_data:
                    # Store in memory for faster access
                    self._sessions[idea_hash] = session_data
                    self._cache_hits += 1
                    self._disk_reads += 1
                    logger.debug(f"Cache hit (from disk) for idea hash: {idea_hash[:8]}...")
                    return self._deserialize_session(session_data)
            except Exception as e:
                logger.warning(f"Failed to load cache from disk for {idea_hash[:8]}...: {e}")

        self._cache_misses += 1
        logger.debug(f"Cache miss for idea hash: {idea_hash[:8]}...")
        return None

    def set(self, idea_hash: str, session: BootstrapSession) -> None:
        """Store session in persistent cache.

        Saves to both in-memory cache and disk.

        Args:
            idea_hash: Hash of the parsed idea
            session: BootstrapSession to cache
        """
        # Serialize the session
        session_data = self._serialize_session(session)

        # Store in memory
        self._sessions[idea_hash] = session_data

        # Create metadata
        now = datetime.now()
        expires_at = now + timedelta(hours=self.ttl_hours)
        metadata = PersistentCacheMetadata(
            idea_hash=idea_hash,
            created_at=now,
            expires_at=expires_at,
            session_id=session.session_id,
            file_path=self._get_cache_file_path(idea_hash),
        )
        self._metadata[idea_hash] = metadata

        # Write to disk
        try:
            self._save_session_to_disk(idea_hash, session_data, metadata)
            self._disk_writes += 1
            logger.debug(
                f"Cached session for idea hash: {idea_hash[:8]}... "
                f"(expires: {metadata.expires_at})"
            )
        except Exception as e:
            logger.error(f"Failed to save cache to disk for {idea_hash[:8]}...: {e}")
            # Still have it in memory, so continue working

    def invalidate(self, idea_hash: str) -> bool:
        """Invalidate a cached entry.

        Removes from both in-memory and disk cache.

        Args:
            idea_hash: Hash of the parsed idea

        Returns:
            True if entry was removed, False if not found
        """
        result = self._delete_cache_entry(idea_hash)
        if result:
            logger.debug(f"Invalidated cache for idea hash: {idea_hash[:8]}...")
        return result

    def clear(self) -> None:
        """Clear all cached entries.

        Removes all in-memory and disk cache entries.
        """
        self._sessions.clear()
        self._metadata.clear()

        # Delete all cache files
        try:
            for cache_file in self.cache_dir.glob("*.json"):
                if cache_file.name != "metadata.json":
                    cache_file.unlink()
                    logger.debug(f"Deleted cache file: {cache_file.name}")

            # Delete metadata file
            metadata_file = self.cache_dir / "metadata.json"
            if metadata_file.exists():
                metadata_file.unlink()
        except Exception as e:
            logger.warning(f"Error clearing cache directory: {e}")

        logger.debug("Research cache cleared")

    def cleanup_expired(self) -> int:
        """Remove expired entries from cache.

        Scans both in-memory and disk caches for expired entries
        and removes them.

        Returns:
            Number of entries removed
        """
        expired_hashes = [
            idea_hash
            for idea_hash, metadata in self._metadata.items()
            if metadata.is_expired()
        ]

        for idea_hash in expired_hashes:
            self._delete_cache_entry(idea_hash)
            self._expired_cleanups += 1

        if expired_hashes:
            logger.debug(f"Cleaned up {len(expired_hashes)} expired cache entries")

        return len(expired_hashes)

    def get_size(self) -> int:
        """Get current number of cached entries.

        Returns:
            Number of valid cache entries
        """
        return len(self._sessions)

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache metrics and configuration
        """
        total_requests = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total_requests * 100) if total_requests > 0 else 0.0

        return {
            "cache_size": self.get_size(),
            "ttl_hours": self.ttl_hours,
            "cache_dir": str(self.cache_dir),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "total_requests": total_requests,
            "hit_rate_percent": hit_rate,
            "disk_reads": self._disk_reads,
            "disk_writes": self._disk_writes,
            "expired_cleanups": self._expired_cleanups,
        }

    def _serialize_session(self, session: BootstrapSession) -> dict[str, Any]:
        """Serialize a bootstrap session to dictionary.

        Args:
            session: BootstrapSession to serialize

        Returns:
            Dictionary representation suitable for JSON serialization
        """
        return session.model_dump(mode="json")

    def _deserialize_session(self, data: dict[str, Any]) -> BootstrapSession:
        """Deserialize a bootstrap session from dictionary.

        Args:
            data: Dictionary with session data

        Returns:
            BootstrapSession instance
        """
        return BootstrapSession.model_validate(data)

    def _get_cache_file_path(self, idea_hash: str) -> Path:
        """Get the file path for a cached session.

        Args:
            idea_hash: Hash of the parsed idea

        Returns:
            Path to the cache file
        """
        return self.cache_dir / f"{idea_hash}.json"

    def _save_session_to_disk(
        self,
        idea_hash: str,
        session_data: dict[str, Any],
        metadata: PersistentCacheMetadata,
    ) -> None:
        """Save session and metadata to disk.

        Args:
            idea_hash: Hash of the parsed idea
            session_data: Serialized session data
            metadata: Cache metadata

        Raises:
            IOError: If file write fails
        """
        cache_file = self._get_cache_file_path(idea_hash)

        # Write session file with metadata as header
        data_to_write = {
            "_metadata": {
                "idea_hash": metadata.idea_hash,
                "created_at": metadata.created_at.isoformat(),
                "expires_at": metadata.expires_at.isoformat(),
                "session_id": metadata.session_id,
            },
            "_session": session_data,
        }

        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data_to_write, f, indent=2, ensure_ascii=False, default=str)

        logger.debug(f"Saved cache to disk: {cache_file}")

    def _load_session_from_disk(self, file_path: Path) -> Optional[dict[str, Any]]:
        """Load session from disk.

        Args:
            file_path: Path to the cache file

        Returns:
            Session data dictionary or None if load fails

        Raises:
            IOError: If file read fails
        """
        if not file_path.exists():
            return None

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Extract session data (skip metadata)
        return data.get("_session")

    def _load_cache_from_disk(self) -> None:
        """Load all cached sessions from disk on startup.

        Automatically loads valid cache entries from disk and validates
        TTL before loading into memory.
        """
        if not self.cache_dir.exists():
            logger.debug(f"Cache directory doesn't exist: {self.cache_dir}")
            return

        loaded_count = 0
        expired_count = 0

        for cache_file in self.cache_dir.glob("*.json"):
            if cache_file.name == "metadata.json":
                continue

            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                metadata_dict = data.get("_metadata", {})
                session_data = data.get("_session", {})

                if not metadata_dict or not session_data:
                    logger.warning(f"Invalid cache file format: {cache_file}")
                    continue

                # Check if expired
                expires_at_str = metadata_dict.get("expires_at")
                if expires_at_str:
                    expires_at = datetime.fromisoformat(expires_at_str)
                    if datetime.now() >= expires_at:
                        # Delete expired entry
                        cache_file.unlink()
                        expired_count += 1
                        logger.debug(f"Skipped expired cache: {cache_file.name}")
                        continue

                # Load into memory
                idea_hash = metadata_dict.get("idea_hash")
                if idea_hash:
                    self._sessions[idea_hash] = session_data

                    # Recreate metadata
                    self._metadata[idea_hash] = PersistentCacheMetadata(
                        idea_hash=idea_hash,
                        created_at=datetime.fromisoformat(metadata_dict["created_at"]),
                        expires_at=datetime.fromisoformat(metadata_dict["expires_at"]),
                        session_id=metadata_dict.get("session_id", ""),
                        file_path=cache_file,
                    )

                    loaded_count += 1
                    logger.debug(f"Loaded cache from disk: {idea_hash[:8]}...")

            except Exception as e:
                logger.warning(f"Error loading cache file {cache_file}: {e}")

        if loaded_count > 0 or expired_count > 0:
            logger.info(
                f"Cache startup: loaded {loaded_count} entries, "
                f"skipped {expired_count} expired entries"
            )

    def _delete_cache_entry(self, idea_hash: str) -> bool:
        """Delete a cache entry from both memory and disk.

        Args:
            idea_hash: Hash of the parsed idea

        Returns:
            True if entry was deleted, False if not found
        """
        deleted = False

        # Remove from memory
        if idea_hash in self._sessions:
            del self._sessions[idea_hash]
            deleted = True

        # Remove from metadata and disk
        if idea_hash in self._metadata:
            metadata = self._metadata[idea_hash]
            del self._metadata[idea_hash]

            # Delete disk file
            if metadata.file_path.exists():
                try:
                    metadata.file_path.unlink()
                    logger.debug(f"Deleted cache file: {metadata.file_path.name}")
                except Exception as e:
                    logger.warning(f"Failed to delete cache file: {e}")

            deleted = True

        return deleted


class PersistentCacheManager:
    """Manager for integrating persistent cache with OptimizedResearchCache.

    Provides a unified interface for caching with automatic persistence.
    """

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        ttl_hours: int = DEFAULT_CACHE_TTL_HOURS,
        max_cache_size: int = 100,
        enable_compression: bool = True,
    ):
        """Initialize cache manager.

        Args:
            cache_dir: Directory for persistent cache files
            ttl_hours: Time-to-live in hours for cache entries
            max_cache_size: Maximum number of in-memory cache entries
            enable_compression: Whether to enable compression
        """
        self.persistent_cache = PersistentCache(
            cache_dir=cache_dir,
            ttl_hours=ttl_hours,
            auto_load=True,
        )

        self.optimized_cache = OptimizedResearchCache(
            ttl_hours=ttl_hours,
            max_size=max_cache_size,
            enable_compression=enable_compression,
        )

    def get(self, idea_hash: str) -> Optional[BootstrapSession]:
        """Get cached session with fallback to persistent cache.

        Args:
            idea_hash: Hash of the parsed idea

        Returns:
            Cached BootstrapSession if valid, None otherwise
        """
        # Try optimized (in-memory) cache first
        session = self.optimized_cache.get(idea_hash)
        if session:
            return session

        # Fall back to persistent cache
        session = self.persistent_cache.get(idea_hash)
        if session:
            # Store in optimized cache for future access
            self.optimized_cache.set(idea_hash, session)
            return session

        return None

    def set(self, idea_hash: str, session: BootstrapSession) -> None:
        """Store session in both caches.

        Args:
            idea_hash: Hash of the parsed idea
            session: BootstrapSession to cache
        """
        self.optimized_cache.set(idea_hash, session)
        self.persistent_cache.set(idea_hash, session)

    def invalidate(self, idea_hash: str) -> bool:
        """Invalidate cache entry in both caches.

        Args:
            idea_hash: Hash of the parsed idea

        Returns:
            True if entry was removed
        """
        result1 = self.optimized_cache.invalidate(idea_hash)
        result2 = self.persistent_cache.invalidate(idea_hash)
        return result1 or result2

    def clear(self) -> None:
        """Clear all cache entries in both caches."""
        self.optimized_cache.clear()
        self.persistent_cache.clear()

    def cleanup_expired(self) -> int:
        """Clean up expired entries in both caches.

        Returns:
            Total number of entries removed
        """
        count1 = self.optimized_cache.cleanup_expired()
        count2 = self.persistent_cache.cleanup_expired()
        return count1 + count2

    def get_stats(self) -> dict[str, Any]:
        """Get combined statistics from both caches.

        Returns:
            Dictionary with cache statistics
        """
        return {
            "optimized_cache": self.optimized_cache.get_stats(),
            "persistent_cache": self.persistent_cache.get_stats(),
        }
