"""
Simple in-memory caching service
"""
from typing import Any, Optional
from datetime import datetime, timedelta
import json


class CacheService:
    """In-memory cache with TTL"""

    def __init__(self):
        self._cache = {}

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if key in self._cache:
            entry = self._cache[key]
            if datetime.now() < entry['expires_at']:
                return entry['value']
            else:
                # Expired, remove
                del self._cache[key]
        return None

    def set(self, key: str, value: Any, ttl_seconds: int = 300):
        """Set value in cache with TTL"""
        self._cache[key] = {
            'value': value,
            'expires_at': datetime.now() + timedelta(seconds=ttl_seconds)
        }

    def delete(self, key: str):
        """Delete value from cache"""
        if key in self._cache:
            del self._cache[key]

    def clear(self):
        """Clear entire cache"""
        self._cache.clear()

    def get_stats(self):
        """Get cache statistics"""
        total_entries = len(self._cache)
        expired = sum(
            1 for entry in self._cache.values()
            if datetime.now() >= entry['expires_at']
        )
        return {
            'total_entries': total_entries,
            'expired_entries': expired,
            'active_entries': total_entries - expired
        }


# Global cache instance
cache = CacheService()
