"""Credential rotation tracking and management.

Implements gap analysis item 6.4:
- Rotation tracking and age monitoring
- Scoped credentials (least privilege)
- Health warnings for stale credentials
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class CredentialScope(str, Enum):
    """Standard credential scopes across providers."""

    READ = "read"  # Read-only access
    WRITE = "write"  # Create/update access
    DELETE = "delete"  # Delete access
    PUBLISH = "publish"  # Publishing (YouTube, etc.)
    TRADE = "trade"  # Trading operations
    ADMIN = "admin"  # Administrative access


class CredentialEnvironment(str, Enum):
    """Credential environment types."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    PAPER = "paper"  # Paper trading / sandbox


@dataclass
class RotationPolicy:
    """Policy for credential rotation."""

    provider: str
    max_age_days: int = 90  # Max age before warning
    critical_age_days: int = 180  # Age that requires immediate rotation
    auto_refresh_enabled: bool = False  # Whether to auto-refresh OAuth tokens
    refresh_retry_limit: int = 3  # Max retries for refresh
    notify_at_days: list[int] = field(default_factory=lambda: [30, 14, 7, 1])  # Warning thresholds

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "max_age_days": self.max_age_days,
            "critical_age_days": self.critical_age_days,
            "auto_refresh_enabled": self.auto_refresh_enabled,
            "refresh_retry_limit": self.refresh_retry_limit,
            "notify_at_days": self.notify_at_days,
        }


@dataclass
class CredentialRecord:
    """Record of a credential's lifecycle.

    Never stores actual secret values - only metadata for rotation tracking.
    """

    provider: str
    credential_id: str  # Opaque identifier (not the actual key)
    environment: CredentialEnvironment
    scopes: list[CredentialScope]

    # Lifecycle timestamps
    created_at: datetime
    rotated_at: Optional[datetime] = None  # Last rotation
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    # Rotation tracking
    rotation_count: int = 0
    refresh_failures: int = 0
    last_refresh_error: Optional[str] = None

    # Least privilege metadata
    is_scoped: bool = True  # False if this is a full-access key
    allowed_actions: list[str] = field(default_factory=list)

    def age_days(self) -> int:
        """Calculate credential age in days."""
        reference = self.rotated_at or self.created_at
        return (datetime.now(timezone.utc) - reference).days

    def is_stale(self, policy: RotationPolicy) -> bool:
        """Check if credential exceeds max age."""
        return self.age_days() > policy.max_age_days

    def is_critical(self, policy: RotationPolicy) -> bool:
        """Check if credential requires immediate rotation."""
        return self.age_days() > policy.critical_age_days

    def days_until_warning(self, policy: RotationPolicy) -> Optional[int]:
        """Days until next rotation warning, or None if past warning."""
        age = self.age_days()
        for threshold in sorted(policy.notify_at_days, reverse=True):
            days_until = policy.max_age_days - threshold - age
            if days_until > 0:
                return days_until
        return None

    def has_scope(self, scope: CredentialScope) -> bool:
        """Check if credential has a specific scope."""
        return scope in self.scopes

    def can_perform(self, action: str) -> bool:
        """Check if credential can perform a specific action."""
        if not self.allowed_actions:
            return True  # No restrictions
        return action in self.allowed_actions

    def to_dict(self) -> dict:
        """Convert to dictionary (no secrets)."""
        return {
            "provider": self.provider,
            "credential_id": self.credential_id,
            "environment": self.environment.value,
            "scopes": [s.value for s in self.scopes],
            "created_at": self.created_at.isoformat(),
            "rotated_at": self.rotated_at.isoformat() if self.rotated_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "rotation_count": self.rotation_count,
            "age_days": self.age_days(),
            "refresh_failures": self.refresh_failures,
            "last_refresh_error": self.last_refresh_error,
            "is_scoped": self.is_scoped,
            "allowed_actions": self.allowed_actions,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CredentialRecord":
        """Create from dictionary."""
        return cls(
            provider=data["provider"],
            credential_id=data["credential_id"],
            environment=CredentialEnvironment(data["environment"]),
            scopes=[CredentialScope(s) for s in data.get("scopes", [])],
            created_at=datetime.fromisoformat(data["created_at"]),
            rotated_at=(
                datetime.fromisoformat(data["rotated_at"]) if data.get("rotated_at") else None
            ),
            last_used_at=(
                datetime.fromisoformat(data["last_used_at"]) if data.get("last_used_at") else None
            ),
            expires_at=(
                datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None
            ),
            rotation_count=data.get("rotation_count", 0),
            refresh_failures=data.get("refresh_failures", 0),
            last_refresh_error=data.get("last_refresh_error"),
            is_scoped=data.get("is_scoped", True),
            allowed_actions=data.get("allowed_actions", []),
        )


# Default rotation policies per provider
DEFAULT_ROTATION_POLICIES = {
    "youtube": RotationPolicy(
        provider="youtube",
        max_age_days=90,
        critical_age_days=180,
        auto_refresh_enabled=True,  # OAuth tokens can auto-refresh
    ),
    "etsy": RotationPolicy(
        provider="etsy",
        max_age_days=60,
        critical_age_days=90,
        auto_refresh_enabled=True,
    ),
    "shopify": RotationPolicy(
        provider="shopify",
        max_age_days=365,  # Shopify tokens are long-lived
        critical_age_days=400,
        auto_refresh_enabled=False,
    ),
    "alpaca": RotationPolicy(
        provider="alpaca",
        max_age_days=90,
        critical_age_days=180,
        auto_refresh_enabled=False,  # API keys require manual rotation
    ),
    "anthropic": RotationPolicy(
        provider="anthropic",
        max_age_days=180,
        critical_age_days=365,
        auto_refresh_enabled=False,
    ),
    "openai": RotationPolicy(
        provider="openai",
        max_age_days=180,
        critical_age_days=365,
        auto_refresh_enabled=False,
    ),
}


class CredentialRotationTracker:
    """Service for tracking credential rotation and age.

    Manages credential lifecycle without storing actual secrets.
    Stores only metadata (creation dates, rotation counts, scopes).
    """

    def __init__(self, storage_path: Optional[Path] = None):
        """Initialize tracker.

        Args:
            storage_path: Path to store credential metadata
        """
        self.storage_path = storage_path or Path(".credentials/metadata.json")
        self._records: dict[str, CredentialRecord] = {}
        self._policies: dict[str, RotationPolicy] = DEFAULT_ROTATION_POLICIES.copy()
        self._load()

    def _load(self) -> None:
        """Load existing records from storage."""
        if not self.storage_path.exists():
            return

        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
            for key, record_data in data.get("records", {}).items():
                self._records[key] = CredentialRecord.from_dict(record_data)
            for provider, policy_data in data.get("policies", {}).items():
                self._policies[provider] = RotationPolicy(**policy_data)
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to load credential metadata: {e}")

    def _save(self) -> None:
        """Save records to storage."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "records": {key: r.to_dict() for key, r in self._records.items()},
            "policies": {p: pol.to_dict() for p, pol in self._policies.items()},
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        self.storage_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _make_key(self, provider: str, environment: CredentialEnvironment) -> str:
        """Create unique key for credential record."""
        return f"{provider}:{environment.value}"

    def register_credential(
        self,
        provider: str,
        credential_id: str,
        environment: CredentialEnvironment,
        scopes: list[CredentialScope],
        allowed_actions: Optional[list[str]] = None,
        expires_at: Optional[datetime] = None,
    ) -> CredentialRecord:
        """Register a new credential for tracking.

        Args:
            provider: Provider name
            credential_id: Opaque identifier (NOT the actual secret)
            environment: Environment type
            scopes: Granted scopes
            allowed_actions: Specific allowed actions (if restricted)
            expires_at: Token expiry time

        Returns:
            CredentialRecord for the registered credential
        """
        key = self._make_key(provider, environment)
        now = datetime.now(timezone.utc)

        record = CredentialRecord(
            provider=provider,
            credential_id=credential_id,
            environment=environment,
            scopes=scopes,
            created_at=now,
            expires_at=expires_at,
            is_scoped=bool(allowed_actions),
            allowed_actions=allowed_actions or [],
        )

        self._records[key] = record
        self._save()

        logger.info(
            f"Registered credential: {provider}/{environment.value} "
            f"(scopes={[s.value for s in scopes]})"
        )

        return record

    def record_rotation(
        self,
        provider: str,
        environment: CredentialEnvironment,
        new_credential_id: str,
        expires_at: Optional[datetime] = None,
    ) -> Optional[CredentialRecord]:
        """Record a credential rotation.

        Args:
            provider: Provider name
            environment: Environment type
            new_credential_id: New opaque identifier
            expires_at: New expiry time

        Returns:
            Updated CredentialRecord, or None if not found
        """
        key = self._make_key(provider, environment)
        record = self._records.get(key)

        if not record:
            logger.warning(f"No credential record found for {key}")
            return None

        now = datetime.now(timezone.utc)
        record.credential_id = new_credential_id
        record.rotated_at = now
        record.rotation_count += 1
        record.refresh_failures = 0
        record.last_refresh_error = None

        if expires_at:
            record.expires_at = expires_at

        self._save()

        logger.info(
            f"Rotated credential: {provider}/{environment.value} "
            f"(rotation #{record.rotation_count})"
        )

        return record

    def record_usage(
        self,
        provider: str,
        environment: CredentialEnvironment,
    ) -> Optional[CredentialRecord]:
        """Record credential usage.

        Args:
            provider: Provider name
            environment: Environment type

        Returns:
            Updated CredentialRecord, or None if not found
        """
        key = self._make_key(provider, environment)
        record = self._records.get(key)

        if record:
            record.last_used_at = datetime.now(timezone.utc)
            self._save()

        return record

    def record_refresh_failure(
        self,
        provider: str,
        environment: CredentialEnvironment,
        error: str,
    ) -> Optional[CredentialRecord]:
        """Record a refresh failure.

        Args:
            provider: Provider name
            environment: Environment type
            error: Error message

        Returns:
            Updated CredentialRecord, or None if not found
        """
        key = self._make_key(provider, environment)
        record = self._records.get(key)

        if record:
            record.refresh_failures += 1
            record.last_refresh_error = error
            self._save()
            logger.warning(
                f"Refresh failure for {provider}/{environment.value}: {error} "
                f"(failures: {record.refresh_failures})"
            )

        return record

    def get_record(
        self,
        provider: str,
        environment: CredentialEnvironment,
    ) -> Optional[CredentialRecord]:
        """Get credential record."""
        key = self._make_key(provider, environment)
        return self._records.get(key)

    def get_policy(self, provider: str) -> RotationPolicy:
        """Get rotation policy for provider."""
        return self._policies.get(
            provider,
            RotationPolicy(provider=provider),  # Default policy
        )

    def check_rotation_needed(
        self,
        provider: str,
        environment: CredentialEnvironment,
    ) -> tuple[bool, str]:
        """Check if credential rotation is needed.

        Args:
            provider: Provider name
            environment: Environment type

        Returns:
            Tuple of (needs_rotation: bool, reason: str)
        """
        record = self.get_record(provider, environment)
        if not record:
            return False, "No credential record found"

        policy = self.get_policy(provider)

        if record.is_critical(policy):
            return (
                True,
                f"Credential age ({record.age_days()} days) exceeds critical threshold ({policy.critical_age_days} days)",
            )

        if record.is_stale(policy):
            return (
                True,
                f"Credential age ({record.age_days()} days) exceeds max age ({policy.max_age_days} days)",
            )

        if record.refresh_failures >= policy.refresh_retry_limit:
            return True, f"Too many refresh failures ({record.refresh_failures})"

        return False, "Credential is healthy"

    def can_perform_action(
        self,
        provider: str,
        environment: CredentialEnvironment,
        action: str,
        required_scope: Optional[CredentialScope] = None,
    ) -> tuple[bool, Optional[str]]:
        """Check if credential can perform an action.

        Args:
            provider: Provider name
            environment: Environment type
            action: Action to perform
            required_scope: Required scope for the action

        Returns:
            Tuple of (can_perform: bool, error: Optional[str])
        """
        record = self.get_record(provider, environment)
        if not record:
            return False, f"No credential registered for {provider}/{environment.value}"

        if required_scope and not record.has_scope(required_scope):
            return False, (
                f"Credential lacks required scope: {required_scope.value}. "
                f"Available scopes: {[s.value for s in record.scopes]}"
            )

        if not record.can_perform(action):
            return False, (
                f"Action '{action}' not in allowed actions for this credential. "
                f"Allowed: {record.allowed_actions}"
            )

        # Check if credential is usable
        needs_rotation, reason = self.check_rotation_needed(provider, environment)
        policy = self.get_policy(provider)
        if record.is_critical(policy):
            return False, f"Credential requires immediate rotation: {reason}"

        return True, None

    def get_health_report(self) -> dict:
        """Generate health report for all credentials.

        Returns:
            Health report dictionary (no secrets)
        """
        now = datetime.now(timezone.utc)
        healthy = []
        warnings = []
        critical = []

        for key, record in self._records.items():
            policy = self.get_policy(record.provider)

            if record.is_critical(policy):
                critical.append(
                    {
                        "key": key,
                        "record": record.to_dict(),
                        "policy": policy.to_dict(),
                        "reason": f"Age ({record.age_days()} days) exceeds critical threshold",
                    }
                )
            elif record.is_stale(policy):
                warnings.append(
                    {
                        "key": key,
                        "record": record.to_dict(),
                        "policy": policy.to_dict(),
                        "reason": f"Age ({record.age_days()} days) exceeds max age",
                    }
                )
            elif record.refresh_failures > 0:
                warnings.append(
                    {
                        "key": key,
                        "record": record.to_dict(),
                        "policy": policy.to_dict(),
                        "reason": f"Refresh failures: {record.refresh_failures}",
                    }
                )
            else:
                healthy.append(
                    {
                        "key": key,
                        "record": record.to_dict(),
                        "days_until_warning": record.days_until_warning(policy),
                    }
                )

        return {
            "checked_at": now.isoformat(),
            "total_credentials": len(self._records),
            "healthy_count": len(healthy),
            "warning_count": len(warnings),
            "critical_count": len(critical),
            "overall_status": ("critical" if critical else "warning" if warnings else "healthy"),
            "healthy": healthy,
            "warnings": warnings,
            "critical": critical,
        }
