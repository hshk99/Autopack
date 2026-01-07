"""
Secret Store - Environment-based secret retrieval with optional backends.

BUILD-189 Phase 5 Skeleton - Minimal implementation for bootstrap.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class SecretDescriptor:
    """Describes a secret and its metadata."""

    name: str
    env_var: str
    description: str
    required: bool = True
    redact_pattern: Optional[str] = None  # Regex to redact in logs


# Registry of known secrets (extend as integrations are added)
KNOWN_SECRETS: dict[str, SecretDescriptor] = {
    "etsy_api_key": SecretDescriptor(
        name="etsy_api_key",
        env_var="ETSY_API_KEY",
        description="Etsy API key for shop management",
    ),
    "shopify_access_token": SecretDescriptor(
        name="shopify_access_token",
        env_var="SHOPIFY_ACCESS_TOKEN",
        description="Shopify access token for store API",
    ),
    "youtube_api_key": SecretDescriptor(
        name="youtube_api_key",
        env_var="YOUTUBE_API_KEY",
        description="YouTube Data API key",
    ),
}


class SecretStore:
    """
    Simple secret store backed by environment variables.

    Future extensions:
    - Encrypted file backend
    - OS keychain (keyring library)
    - HashiCorp Vault
    """

    def __init__(self):
        self._cache: dict[str, str] = {}

    def get(self, secret_name: str, default: Optional[str] = None) -> Optional[str]:
        """Retrieve a secret by name."""
        if secret_name in self._cache:
            return self._cache[secret_name]

        descriptor = KNOWN_SECRETS.get(secret_name)
        if descriptor:
            value = os.environ.get(descriptor.env_var, default)
        else:
            # Allow arbitrary env var lookups
            value = os.environ.get(secret_name.upper(), default)

        if value:
            self._cache[secret_name] = value

        return value

    def has(self, secret_name: str) -> bool:
        """Check if a secret is available."""
        return self.get(secret_name) is not None

    def clear_cache(self) -> None:
        """Clear the in-memory cache (for testing)."""
        self._cache.clear()


# Module-level singleton
_store = SecretStore()


def get_secret(name: str, default: Optional[str] = None) -> Optional[str]:
    """Convenience function to get a secret."""
    return _store.get(name, default)
