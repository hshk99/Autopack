"""Publish packet models for content/IP/compliance preflight.

Implements gap analysis item 6.10:
- Publish packet artifact with title/description/tags + media hashes
- Heuristic IP/compliance flags
- Required disclosures (AI-generated, etc.)
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class PublishPacketStatus(str, Enum):
    """Status of a publish packet."""

    DRAFT = "draft"  # Being assembled
    PENDING_REVIEW = "pending_review"  # Awaiting operator review
    APPROVED = "approved"  # Approved for publishing
    REJECTED = "rejected"  # Rejected by operator
    PUBLISHED = "published"  # Successfully published


class ComplianceFlagSeverity(str, Enum):
    """Severity of a compliance flag."""

    INFO = "info"  # Informational only
    WARNING = "warning"  # Requires attention but not blocking
    BLOCKING = "blocking"  # Must be resolved before publishing


@dataclass
class ComplianceFlag:
    """A compliance or IP-related flag on publish content.

    Flags can indicate:
    - Trademark keywords detected
    - Banned category matches
    - Missing required disclosures
    - Policy violations
    """

    category: str  # trademark, banned_content, disclosure, policy, copyright
    severity: ComplianceFlagSeverity
    message: str
    details: Optional[str] = None
    detected_text: Optional[str] = None  # The text that triggered the flag
    remediation: Optional[str] = None  # Suggested fix

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "severity": self.severity.value,
            "message": self.message,
            "details": self.details,
            "detected_text": self.detected_text,
            "remediation": self.remediation,
        }


@dataclass
class MediaAsset:
    """Reference to a media asset with hash for verification."""

    filename: str
    content_hash: str  # SHA-256 of file content
    content_type: str  # MIME type
    size_bytes: int
    local_path: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "content_hash": self.content_hash,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
        }


@dataclass
class PublishPacket:
    """A publish packet for content approval before publishing.

    Contains all metadata and media references needed to publish,
    along with compliance flags and required disclosures.

    The packet is immutable once approved - the exact content hashes
    and text that were approved are what gets published.
    """

    # Identification
    packet_id: str  # Unique ID for this packet
    provider: str  # youtube, etsy, shopify
    action: str  # publish, list, update

    # Content
    title: str
    description: str
    tags: list[str] = field(default_factory=list)

    # Media references
    media_assets: list[MediaAsset] = field(default_factory=list)

    # Status and lifecycle
    status: PublishPacketStatus = PublishPacketStatus.DRAFT
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reviewed_at: Optional[datetime] = None
    published_at: Optional[datetime] = None

    # Compliance
    compliance_flags: list[ComplianceFlag] = field(default_factory=list)
    required_disclosures: list[str] = field(default_factory=list)
    policy_snapshot_refs: list[str] = field(default_factory=list)

    # Approval tracking
    approval_id: Optional[str] = None
    reviewer_notes: Optional[str] = None

    # Run context
    run_id: Optional[str] = None
    phase_number: Optional[int] = None

    def content_hash(self) -> str:
        """Compute hash of publishable content.

        This hash uniquely identifies the exact content that will be published.
        Changes to title, description, tags, or media will change this hash.
        """
        content = {
            "title": self.title,
            "description": self.description,
            "tags": sorted(self.tags),
            "media_hashes": sorted([m.content_hash for m in self.media_assets]),
        }
        canonical = json.dumps(content, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(canonical.encode()).hexdigest()

    def has_blocking_flags(self) -> bool:
        """Check if any blocking compliance flags exist."""
        return any(f.severity == ComplianceFlagSeverity.BLOCKING for f in self.compliance_flags)

    def can_be_approved(self) -> bool:
        """Check if packet can be approved (no blocking issues)."""
        return self.status == PublishPacketStatus.PENDING_REVIEW and not self.has_blocking_flags()

    def can_be_published(self) -> bool:
        """Check if packet can be published."""
        return self.status == PublishPacketStatus.APPROVED

    def to_dict(self) -> dict:
        """Convert to dictionary for storage/API."""
        return {
            "packet_id": self.packet_id,
            "provider": self.provider,
            "action": self.action,
            "title": self.title,
            "description": self.description,
            "tags": self.tags,
            "media_assets": [m.to_dict() for m in self.media_assets],
            "status": self.status.value,
            "content_hash": self.content_hash(),
            "created_at": self.created_at.isoformat(),
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "compliance_flags": [f.to_dict() for f in self.compliance_flags],
            "required_disclosures": self.required_disclosures,
            "policy_snapshot_refs": self.policy_snapshot_refs,
            "has_blocking_flags": self.has_blocking_flags(),
            "can_be_approved": self.can_be_approved(),
            "approval_id": self.approval_id,
            "reviewer_notes": self.reviewer_notes,
            "run_id": self.run_id,
            "phase_number": self.phase_number,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PublishPacket":
        """Create from dictionary."""
        return cls(
            packet_id=data["packet_id"],
            provider=data["provider"],
            action=data["action"],
            title=data["title"],
            description=data["description"],
            tags=data.get("tags", []),
            media_assets=[
                MediaAsset(
                    filename=m["filename"],
                    content_hash=m["content_hash"],
                    content_type=m["content_type"],
                    size_bytes=m["size_bytes"],
                )
                for m in data.get("media_assets", [])
            ],
            status=PublishPacketStatus(data["status"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            reviewed_at=(
                datetime.fromisoformat(data["reviewed_at"]) if data.get("reviewed_at") else None
            ),
            published_at=(
                datetime.fromisoformat(data["published_at"]) if data.get("published_at") else None
            ),
            compliance_flags=[
                ComplianceFlag(
                    category=f["category"],
                    severity=ComplianceFlagSeverity(f["severity"]),
                    message=f["message"],
                    details=f.get("details"),
                    detected_text=f.get("detected_text"),
                    remediation=f.get("remediation"),
                )
                for f in data.get("compliance_flags", [])
            ],
            required_disclosures=data.get("required_disclosures", []),
            policy_snapshot_refs=data.get("policy_snapshot_refs", []),
            approval_id=data.get("approval_id"),
            reviewer_notes=data.get("reviewer_notes"),
            run_id=data.get("run_id"),
            phase_number=data.get("phase_number"),
        )
