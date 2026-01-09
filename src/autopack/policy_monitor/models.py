"""Policy monitor models.

Defines data structures for policy snapshots, diffs, and status tracking.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class PolicyStatus(str, Enum):
    """Status of a policy snapshot."""

    FRESH = "fresh"  # Within freshness threshold
    STALE = "stale"  # Past freshness threshold
    CHANGED = "changed"  # Content changed, needs acknowledgment
    ACKNOWLEDGED = "acknowledged"  # Change was acknowledged by operator
    UNKNOWN = "unknown"  # No snapshot available


class PolicyCategory(str, Enum):
    """Categories of provider policies."""

    TERMS_OF_SERVICE = "terms_of_service"
    CONTENT_POLICY = "content_policy"
    MONETIZATION = "monetization"
    AI_DISCLOSURE = "ai_disclosure"
    PROHIBITED_ITEMS = "prohibited_items"
    INTELLECTUAL_PROPERTY = "intellectual_property"
    SPAM_POLICY = "spam_policy"


@dataclass
class PolicySnapshot:
    """A point-in-time snapshot of a provider policy page."""

    snapshot_id: str
    provider: str
    policy_url: str
    policy_category: PolicyCategory
    content_hash: str
    fetched_at: datetime
    content_summary: str = ""
    raw_content: str = ""
    status: PolicyStatus = PolicyStatus.FRESH
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    freshness_days: int = 7  # Default freshness threshold

    def is_fresh(self, as_of: Optional[datetime] = None) -> bool:
        """Check if snapshot is within freshness threshold."""
        now = as_of or datetime.now(timezone.utc)
        age = now - self.fetched_at
        return age.days < self.freshness_days

    def content_matches(self, other_hash: str) -> bool:
        """Check if content hash matches another hash."""
        return self.content_hash == other_hash

    @staticmethod
    def compute_hash(content: str) -> str:
        """Compute SHA-256 hash of content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "snapshot_id": self.snapshot_id,
            "provider": self.provider,
            "policy_url": self.policy_url,
            "policy_category": self.policy_category.value,
            "content_hash": self.content_hash,
            "fetched_at": self.fetched_at.isoformat(),
            "content_summary": self.content_summary,
            "status": self.status.value,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "acknowledged_by": self.acknowledged_by,
            "freshness_days": self.freshness_days,
        }


@dataclass
class PolicyDiff:
    """Represents a detected change between policy snapshots."""

    diff_id: str
    provider: str
    policy_category: PolicyCategory
    old_snapshot_id: str
    new_snapshot_id: str
    old_hash: str
    new_hash: str
    detected_at: datetime
    summary: str = ""
    is_acknowledged: bool = False
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    acknowledgment_notes: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "diff_id": self.diff_id,
            "provider": self.provider,
            "policy_category": self.policy_category.value,
            "old_snapshot_id": self.old_snapshot_id,
            "new_snapshot_id": self.new_snapshot_id,
            "old_hash": self.old_hash[:16] + "...",
            "new_hash": self.new_hash[:16] + "...",
            "detected_at": self.detected_at.isoformat(),
            "summary": self.summary,
            "is_acknowledged": self.is_acknowledged,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "acknowledged_by": self.acknowledged_by,
        }


@dataclass
class ProviderPolicyConfig:
    """Configuration for monitoring a provider's policies."""

    provider: str
    policies: list[dict] = field(default_factory=list)
    freshness_days: int = 7
    enabled: bool = True

    @classmethod
    def youtube(cls) -> "ProviderPolicyConfig":
        """Default YouTube policy monitoring config."""
        return cls(
            provider="youtube",
            policies=[
                {
                    "url": "https://support.google.com/youtube/answer/6162278",
                    "category": PolicyCategory.CONTENT_POLICY,
                    "name": "Community Guidelines",
                },
                {
                    "url": "https://support.google.com/youtube/answer/13572837",
                    "category": PolicyCategory.AI_DISCLOSURE,
                    "name": "AI-generated content disclosure",
                },
                {
                    "url": "https://support.google.com/youtube/answer/2801973",
                    "category": PolicyCategory.SPAM_POLICY,
                    "name": "Spam, deceptive practices, & scams",
                },
                {
                    "url": "https://support.google.com/youtube/answer/72851",
                    "category": PolicyCategory.MONETIZATION,
                    "name": "YouTube Partner Program policies",
                },
            ],
            freshness_days=7,
        )

    @classmethod
    def etsy(cls) -> "ProviderPolicyConfig":
        """Default Etsy policy monitoring config."""
        return cls(
            provider="etsy",
            policies=[
                {
                    "url": "https://www.etsy.com/legal/prohibited/",
                    "category": PolicyCategory.PROHIBITED_ITEMS,
                    "name": "Prohibited Items Policy",
                },
                {
                    "url": "https://www.etsy.com/legal/ip/",
                    "category": PolicyCategory.INTELLECTUAL_PROPERTY,
                    "name": "Intellectual Property Policy",
                },
                {
                    "url": "https://www.etsy.com/legal/handmade/",
                    "category": PolicyCategory.CONTENT_POLICY,
                    "name": "Handmade Policy",
                },
            ],
            freshness_days=7,
        )

    @classmethod
    def shopify(cls) -> "ProviderPolicyConfig":
        """Default Shopify policy monitoring config."""
        return cls(
            provider="shopify",
            policies=[
                {
                    "url": "https://www.shopify.com/legal/aup",
                    "category": PolicyCategory.TERMS_OF_SERVICE,
                    "name": "Acceptable Use Policy",
                },
                {
                    "url": "https://help.shopify.com/en/manual/products/digital-service-product/prohibited-content",
                    "category": PolicyCategory.PROHIBITED_ITEMS,
                    "name": "Prohibited Content",
                },
            ],
            freshness_days=7,
        )


@dataclass
class PolicyGateResult:
    """Result of checking policy gate before an action."""

    can_proceed: bool
    provider: str
    action: str
    stale_policies: list[str] = field(default_factory=list)
    unacknowledged_changes: list[str] = field(default_factory=list)
    missing_snapshots: list[str] = field(default_factory=list)
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "can_proceed": self.can_proceed,
            "provider": self.provider,
            "action": self.action,
            "stale_policies": self.stale_policies,
            "unacknowledged_changes": self.unacknowledged_changes,
            "missing_snapshots": self.missing_snapshots,
            "error_message": self.error_message,
        }
