"""Credential health models.

Provides non-secret visibility into provider credential status for:
- YouTube API
- Etsy API
- Shopify API
- Trading APIs (Alpaca, etc.)
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class CredentialStatus(str, Enum):
    """Status of a provider credential."""

    PRESENT = "present"  # Credential configured and accessible
    MISSING = "missing"  # Credential not configured
    EXPIRED = "expired"  # Token expired and needs refresh
    INVALID = "invalid"  # Credential validation failed
    NEEDS_REAUTH = "needs_reauth"  # Refresh token expired/revoked, needs manual reauth
    UNKNOWN = "unknown"  # Unable to determine status


@dataclass
class ProviderCredential:
    """Non-secret view of a provider credential.

    Never contains actual secret values - only status metadata.
    """

    provider: str  # youtube, etsy, shopify, alpaca, etc.
    environment: str  # dev, staging, prod
    status: CredentialStatus

    # Timing (without revealing secrets)
    last_validated: Optional[datetime] = None  # When credential was last validated
    expires_at: Optional[datetime] = None  # Token expiry time (if applicable)
    last_used: Optional[datetime] = None  # Last successful use

    # Health metrics
    age_days: Optional[int] = None  # Days since credential was created/rotated
    validation_error: Optional[str] = None  # Non-secret error message if status is INVALID

    # Scopes (what the credential can do)
    scopes: Optional[list[str]] = None  # e.g., ["publish", "read"] for YouTube

    def is_healthy(self) -> bool:
        """Check if credential is in a healthy state."""
        return self.status == CredentialStatus.PRESENT

    def is_expired(self) -> bool:
        """Check if credential is expired."""
        return self.status in (CredentialStatus.EXPIRED, CredentialStatus.NEEDS_REAUTH)

    def needs_attention(self) -> bool:
        """Check if credential needs operator attention."""
        return self.status in (
            CredentialStatus.MISSING,
            CredentialStatus.EXPIRED,
            CredentialStatus.INVALID,
            CredentialStatus.NEEDS_REAUTH,
        )

    def to_dict(self) -> dict:
        """Convert to API-safe dictionary (no secrets)."""
        return {
            "provider": self.provider,
            "environment": self.environment,
            "status": self.status.value,
            "is_healthy": self.is_healthy(),
            "needs_attention": self.needs_attention(),
            "last_validated": self.last_validated.isoformat() if self.last_validated else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "age_days": self.age_days,
            "validation_error": self.validation_error,
            "scopes": self.scopes,
        }
