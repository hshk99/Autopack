"""Research cache optimization with LRU eviction and compression.

This module provides enhanced caching capabilities for research results with:
- LRU (Least Recently Used) eviction policy for memory management
- Optional compression for large results to reduce memory footprint
- Comprehensive metrics and monitoring
- Cache hit rate optimization
"""

from __future__ import annotations

import gzip
import logging
import pickle
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Any, Optional

from autopack.research.models.bootstrap_session import BootstrapSession

logger = logging.getLogger(__name__)

# Default cache configuration
DEFAULT_MAX_CACHE_SIZE = 100  # Maximum number of cache entries
DEFAULT_COMPRESSION_THRESHOLD = 1024 * 100  # 100KB - compress if larger
DEFAULT_CACHE_TTL_HOURS = 24


class CacheMetrics:
    """Tracks cache performance metrics."""

    def __init__(self):
        """Initialize cache metrics."""
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.compressions = 0
        self.decompressions = 0
        self.total_bytes_saved_by_compression = 0
        self.created_at = datetime.now()

    def record_hit(self) -> None:
        """Record a cache hit."""
        self.hits += 1

    def record_miss(self) -> None:
        """Record a cache miss."""
        self.misses += 1

    def record_eviction(self) -> None:
        """Record an LRU eviction."""
        self.evictions += 1

    def record_compression(self, original_size: int, compressed_size: int) -> None:
        """Record compression and track bytes saved."""
        self.compressions += 1
        bytes_saved = original_size - compressed_size
        self.total_bytes_saved_by_compression += bytes_saved
        logger.debug(
            f"Compression: {original_size} → {compressed_size} bytes (saved {bytes_saved} bytes)"
        )

    def record_decompression(self) -> None:
        """Record a decompression operation."""
        self.decompressions += 1

    def get_hit_rate(self) -> float:
        """Get cache hit rate as percentage.

        Returns:
            Hit rate from 0.0 to 100.0, or 0.0 if no requests yet
        """
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return (self.hits / total) * 100.0

    def get_stats(self) -> dict[str, Any]:
        """Get cache metrics as dictionary.

        Returns:
            Dictionary with comprehensive cache statistics
        """
        return {
            "hits": self.hits,
            "misses": self.misses,
            "total_requests": self.hits + self.misses,
            "hit_rate_percent": self.get_hit_rate(),
            "evictions": self.evictions,
            "compressions": self.compressions,
            "decompressions": self.decompressions,
            "total_bytes_saved_by_compression": self.total_bytes_saved_by_compression,
            "uptime_seconds": (datetime.now() - self.created_at).total_seconds(),
        }


class OptimizedResearchCache:
    """Enhanced research cache with LRU eviction and compression.

    Features:
    - LRU eviction policy for bounded memory usage
    - Optional compression for large bootstrap sessions
    - Comprehensive metrics and monitoring
    - Automatic expired entry cleanup
    - Cache hit rate tracking
    """

    def __init__(
        self,
        ttl_hours: int = DEFAULT_CACHE_TTL_HOURS,
        max_size: int = DEFAULT_MAX_CACHE_SIZE,
        compression_threshold: int = DEFAULT_COMPRESSION_THRESHOLD,
        enable_compression: bool = True,
    ):
        """Initialize the optimized research cache.

        Args:
            ttl_hours: Time-to-live in hours for cached entries
            max_size: Maximum number of cache entries before LRU eviction
            compression_threshold: Size threshold for compression (bytes)
            enable_compression: Whether to enable compression for large results
        """
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.ttl_hours = ttl_hours
        self.max_size = max_size
        self.compression_threshold = compression_threshold
        self.enable_compression = enable_compression
        self._metrics = CacheMetrics()

    def get(self, idea_hash: str) -> Optional[BootstrapSession]:
        """Get cached session if valid and update LRU order.

        Args:
            idea_hash: Hash of the parsed idea

        Returns:
            Cached BootstrapSession if valid, None otherwise
        """
        entry = self._cache.get(idea_hash)

        if not entry:
            self._metrics.record_miss()
            logger.debug(f"Cache miss for idea hash: {idea_hash[:8]}...")
            return None

        # Check if entry has expired
        if entry.is_expired():
            logger.debug(f"Cache expired for idea hash: {idea_hash[:8]}...")
            del self._cache[idea_hash]
            self._metrics.record_miss()
            return None

        # Move to end to mark as recently used (LRU)
        self._cache.move_to_end(idea_hash)

        # Decompress if needed
        session = entry.get_session()
        if session:
            self._metrics.record_hit()
            logger.debug(f"Cache hit for idea hash: {idea_hash[:8]}...")
            return session

        self._metrics.record_miss()
        return None

    def set(self, idea_hash: str, session: BootstrapSession) -> None:
        """Store session in cache with optional compression and LRU management.

        Args:
            idea_hash: Hash of the parsed idea
            session: BootstrapSession to cache
        """
        # Remove if already exists to update
        if idea_hash in self._cache:
            del self._cache[idea_hash]

        # Create cache entry with optional compression
        entry = CacheEntry(
            session=session,
            ttl_hours=self.ttl_hours,
            compression_threshold=self.compression_threshold,
            enable_compression=self.enable_compression,
            metrics=self._metrics,
        )

        self._cache[idea_hash] = entry

        # Move to end (most recently added)
        self._cache.move_to_end(idea_hash)

        # Check if we need LRU eviction
        while len(self._cache) > self.max_size:
            # Remove least recently used (first item in OrderedDict)
            lru_key = next(iter(self._cache))
            del self._cache[lru_key]
            self._metrics.record_eviction()
            logger.debug(
                f"LRU eviction: removed {lru_key[:8]}... "
                f"(cache size: {len(self._cache)}/{self.max_size})"
            )

        logger.debug(
            f"Cached session for idea hash: {idea_hash[:8]}... "
            f"(cache size: {len(self._cache)}/{self.max_size})"
        )

    def invalidate(self, idea_hash: str) -> bool:
        """Invalidate a cached entry.

        Args:
            idea_hash: Hash of the parsed idea

        Returns:
            True if entry was removed, False if not found
        """
        if idea_hash in self._cache:
            del self._cache[idea_hash]
            logger.debug(f"Invalidated cache for idea hash: {idea_hash[:8]}...")
            return True
        return False

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
        logger.debug("Research cache cleared")

    def cleanup_expired(self) -> int:
        """Remove expired entries from cache.

        Returns:
            Number of entries removed
        """
        expired_keys = [key for key, entry in self._cache.items() if entry.is_expired()]
        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")

        return len(expired_keys)

    def get_size(self) -> int:
        """Get current number of cached entries.

        Returns:
            Number of valid cache entries
        """
        return len(self._cache)

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache metrics and configuration
        """
        stats = self._metrics.get_stats()
        stats.update(
            {
                "cache_size": self.get_size(),
                "max_cache_size": self.max_size,
                "ttl_hours": self.ttl_hours,
                "compression_enabled": self.enable_compression,
                "compression_threshold_bytes": self.compression_threshold,
            }
        )
        return stats

    def get_metrics(self) -> CacheMetrics:
        """Get the metrics object for direct access.

        Returns:
            CacheMetrics instance
        """
        return self._metrics


class CacheEntry:
    """A single cache entry with optional compression."""

    def __init__(
        self,
        session: BootstrapSession,
        ttl_hours: int,
        compression_threshold: int,
        enable_compression: bool,
        metrics: CacheMetrics,
    ):
        """Initialize a cache entry.

        Args:
            session: The BootstrapSession to cache
            ttl_hours: Time-to-live in hours
            compression_threshold: Size threshold for compression
            enable_compression: Whether compression is enabled
            metrics: Metrics tracker for compression stats
        """
        self.created_at = datetime.now()
        self.expires_at = self.created_at + timedelta(hours=ttl_hours)
        self.ttl_hours = ttl_hours
        self.compression_threshold = compression_threshold
        self.enable_compression = enable_compression
        self.metrics = metrics
        self.is_compressed = False

        # Serialize and optionally compress the session
        self._store_session(session)

    def _store_session(self, session: BootstrapSession) -> None:
        """Store the session, optionally compressed.

        Args:
            session: BootstrapSession to store
        """
        # Serialize to bytes
        serialized = pickle.dumps(session)
        original_size = len(serialized)

        # Check if compression is beneficial
        if self.enable_compression and original_size > self.compression_threshold:
            compressed = gzip.compress(serialized, compresslevel=6)
            compressed_size = len(compressed)

            # Only use compression if it saves space
            if compressed_size < original_size:
                self._data = compressed
                self.is_compressed = True
                self.metrics.record_compression(original_size, compressed_size)
                logger.debug(
                    f"Stored session with compression: {original_size} → {compressed_size} bytes"
                )
            else:
                self._data = serialized
                self.is_compressed = False
        else:
            self._data = serialized
            self.is_compressed = False

    def get_session(self) -> Optional[BootstrapSession]:
        """Get the deserialized session.

        Returns:
            BootstrapSession if valid and not expired, None otherwise
        """
        if self.is_expired():
            return None

        try:
            # Decompress if needed
            if self.is_compressed:
                data = gzip.decompress(self._data)
                self.metrics.record_decompression()
            else:
                data = self._data

            # Deserialize
            session = pickle.loads(data)
            return session
        except Exception as e:
            logger.error(f"Error deserializing cache entry: {e}")
            return None

    def is_expired(self) -> bool:
        """Check if this cache entry has expired.

        Returns:
            True if expired, False otherwise
        """
        return datetime.now() >= self.expires_at

    def get_size(self) -> int:
        """Get the size of stored data in bytes.

        Returns:
            Size of compressed or uncompressed data
        """
        return len(self._data)

    def get_info(self) -> dict[str, Any]:
        """Get information about this cache entry.

        Returns:
            Dictionary with entry metadata
        """
        return {
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "ttl_hours": self.ttl_hours,
            "is_compressed": self.is_compressed,
            "size_bytes": self.get_size(),
            "is_expired": self.is_expired(),
        }


class CacheOptimizer:
    """Optimizer for cache performance monitoring and tuning.

    Provides methods to analyze cache performance and provide
    optimization recommendations.
    """

    @staticmethod
    def analyze_cache(cache: OptimizedResearchCache) -> dict[str, Any]:
        """Analyze cache performance.

        Args:
            cache: OptimizedResearchCache instance to analyze

        Returns:
            Dictionary with analysis results and recommendations
        """
        stats = cache.get_stats()
        metrics = cache.get_metrics()

        recommendations = []

        # Hit rate analysis
        hit_rate = stats.get("hit_rate_percent", 0.0)
        if hit_rate < 20:
            recommendations.append(
                "Low cache hit rate (<20%). Consider increasing TTL or improving idea similarity detection."
            )

        # Cache utilization analysis
        cache_utilization = stats["cache_size"] / stats["max_cache_size"]
        if cache_utilization > 0.9:
            recommendations.append(
                "Cache is near capacity (>90%). Consider increasing max_cache_size."
            )
        elif cache_utilization < 0.3 and stats["cache_size"] > 0:
            recommendations.append(
                "Cache underutilized (<30%). Consider reducing max_cache_size to free memory."
            )

        # Compression analysis
        if stats["compressions"] > 0:
            avg_bytes_saved = stats["total_bytes_saved_by_compression"] / stats["compressions"]
            recommendations.append(
                f"Compression is effective: saving avg {avg_bytes_saved:.0f} bytes per session."
            )

        # Eviction analysis
        if metrics.evictions > metrics.hits:
            recommendations.append(
                "High eviction rate relative to hits. "
                "Cache is evicting entries faster than they're being reused."
            )

        return {
            "stats": stats,
            "recommendations": recommendations,
            "timestamp": datetime.now().isoformat(),
        }

    @staticmethod
    def suggest_tuning(cache: OptimizedResearchCache) -> dict[str, Any]:
        """Suggest cache tuning parameters.

        Args:
            cache: OptimizedResearchCache instance to tune

        Returns:
            Dictionary with tuning suggestions
        """
        stats = cache.get_stats()
        metrics = cache.get_metrics()

        current_config = {
            "ttl_hours": cache.ttl_hours,
            "max_size": cache.max_size,
            "compression_enabled": cache.enable_compression,
            "compression_threshold": cache.compression_threshold,
        }

        suggested_config = current_config.copy()

        # Adjust max_size based on evictions
        eviction_rate = metrics.evictions / max(metrics.hits + metrics.misses, 1)
        if eviction_rate > 0.1:  # More than 10% of requests cause eviction
            suggested_config["max_size"] = int(cache.max_size * 1.5)

        # Adjust compression threshold based on savings
        if metrics.compressions > 0:
            avg_compression_ratio = stats["total_bytes_saved_by_compression"] / metrics.compressions
            # If we're saving less than 10%, reduce threshold to compress more aggressively
            if avg_compression_ratio < 10000:  # Less than 10KB
                suggested_config["compression_threshold"] = int(cache.compression_threshold * 0.7)

        return {
            "current_config": current_config,
            "suggested_config": suggested_config,
            "rationale": {
                "max_size": (
                    f"Current eviction rate: {eviction_rate * 100:.1f}%. "
                    f"Consider increasing max_size to reduce evictions."
                    if suggested_config["max_size"] != current_config["max_size"]
                    else "Max size is optimal."
                ),
                "compression_threshold": (
                    f"Average compression savings: {avg_compression_ratio / 1024:.1f}KB. "
                    f"Lower threshold to compress more aggressively."
                    if suggested_config["compression_threshold"]
                    != current_config["compression_threshold"]
                    else "Compression threshold is optimal."
                ),
            },
        }
