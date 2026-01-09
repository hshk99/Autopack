"""Artifact retention policy management.

Implements artifact lifecycle management with:
- Classification by type (logs, media, browser artifacts, etc.)
- Retention windows per artifact class
- Automatic cleanup of expired artifacts
- Audit trail for deletions
"""

import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ArtifactClass(str, Enum):
    """Classification of artifacts for retention purposes."""

    # Logs and text artifacts
    RUN_LOG = "run_log"  # Phase and run logs
    DEBUG_LOG = "debug_log"  # Debug/trace logs
    ERROR_LOG = "error_log"  # Error and exception logs

    # Media artifacts
    SCREENSHOT = "screenshot"  # Browser screenshots
    VIDEO = "video"  # Screen recordings
    AUDIO = "audio"  # Audio recordings
    IMAGE = "image"  # Generated images

    # Browser artifacts (higher sensitivity)
    HAR_LOG = "har_log"  # HTTP Archive logs
    BROWSER_STATE = "browser_state"  # Cookies, session data
    NETWORK_TRACE = "network_trace"  # Network captures

    # Data artifacts
    STRUCTURED_DATA = "structured_data"  # JSON/CSV outputs
    DATABASE_SNAPSHOT = "database_snapshot"  # DB exports
    API_RESPONSE = "api_response"  # API response captures

    # Sensitive artifacts
    CREDENTIAL_ARTIFACT = "credential_artifact"  # Anything with credentials
    PII_ARTIFACT = "pii_artifact"  # Artifacts with PII

    # Audit and compliance
    AUDIT_LOG = "audit_log"  # Compliance/audit records
    APPROVAL_RECORD = "approval_record"  # Approval artifacts


@dataclass
class RetentionPolicy:
    """Retention policy for an artifact class."""

    artifact_class: ArtifactClass
    retention_days: int  # How long to keep
    require_redaction: bool = False  # Must redact before storage
    require_encryption: bool = False  # Must encrypt
    auto_delete: bool = True  # Automatically delete after expiry
    notify_before_delete_days: int = 0  # Notify N days before deletion
    archive_before_delete: bool = False  # Archive before deletion

    def to_dict(self) -> dict:
        return {
            "artifact_class": self.artifact_class.value,
            "retention_days": self.retention_days,
            "require_redaction": self.require_redaction,
            "require_encryption": self.require_encryption,
            "auto_delete": self.auto_delete,
            "notify_before_delete_days": self.notify_before_delete_days,
            "archive_before_delete": self.archive_before_delete,
        }


# Default retention policies - conservative by default
DEFAULT_RETENTION_POLICIES = {
    ArtifactClass.RUN_LOG: RetentionPolicy(
        artifact_class=ArtifactClass.RUN_LOG,
        retention_days=90,
        require_redaction=False,
    ),
    ArtifactClass.DEBUG_LOG: RetentionPolicy(
        artifact_class=ArtifactClass.DEBUG_LOG,
        retention_days=30,
        require_redaction=False,
        auto_delete=True,
    ),
    ArtifactClass.ERROR_LOG: RetentionPolicy(
        artifact_class=ArtifactClass.ERROR_LOG,
        retention_days=90,
        require_redaction=True,  # May contain sensitive data
    ),
    ArtifactClass.SCREENSHOT: RetentionPolicy(
        artifact_class=ArtifactClass.SCREENSHOT,
        retention_days=30,
        require_redaction=True,  # May contain sensitive info
    ),
    ArtifactClass.VIDEO: RetentionPolicy(
        artifact_class=ArtifactClass.VIDEO,
        retention_days=14,  # Large files, shorter retention
        require_redaction=True,
    ),
    ArtifactClass.HAR_LOG: RetentionPolicy(
        artifact_class=ArtifactClass.HAR_LOG,
        retention_days=7,  # Contains sensitive headers/cookies
        require_redaction=True,
        require_encryption=True,
    ),
    ArtifactClass.BROWSER_STATE: RetentionPolicy(
        artifact_class=ArtifactClass.BROWSER_STATE,
        retention_days=1,  # Very sensitive, delete quickly
        require_redaction=True,
        require_encryption=True,
        auto_delete=True,
    ),
    ArtifactClass.NETWORK_TRACE: RetentionPolicy(
        artifact_class=ArtifactClass.NETWORK_TRACE,
        retention_days=7,
        require_redaction=True,
        require_encryption=True,
    ),
    ArtifactClass.STRUCTURED_DATA: RetentionPolicy(
        artifact_class=ArtifactClass.STRUCTURED_DATA,
        retention_days=90,
        require_redaction=False,
    ),
    ArtifactClass.API_RESPONSE: RetentionPolicy(
        artifact_class=ArtifactClass.API_RESPONSE,
        retention_days=30,
        require_redaction=True,
    ),
    ArtifactClass.CREDENTIAL_ARTIFACT: RetentionPolicy(
        artifact_class=ArtifactClass.CREDENTIAL_ARTIFACT,
        retention_days=0,  # Never store credentials
        require_redaction=True,
        require_encryption=True,
        auto_delete=True,
    ),
    ArtifactClass.PII_ARTIFACT: RetentionPolicy(
        artifact_class=ArtifactClass.PII_ARTIFACT,
        retention_days=30,
        require_redaction=True,
        require_encryption=True,
    ),
    ArtifactClass.AUDIT_LOG: RetentionPolicy(
        artifact_class=ArtifactClass.AUDIT_LOG,
        retention_days=365,  # Long retention for compliance
        require_redaction=False,
        auto_delete=False,  # Require manual deletion
        archive_before_delete=True,
    ),
    ArtifactClass.APPROVAL_RECORD: RetentionPolicy(
        artifact_class=ArtifactClass.APPROVAL_RECORD,
        retention_days=365,
        require_redaction=False,
        auto_delete=False,
        archive_before_delete=True,
    ),
}


@dataclass
class ArtifactMetadata:
    """Metadata for a tracked artifact."""

    artifact_id: str
    artifact_class: ArtifactClass
    path: str
    created_at: datetime
    size_bytes: int
    content_hash: Optional[str] = None
    is_redacted: bool = False
    is_encrypted: bool = False
    expires_at: Optional[datetime] = None
    run_id: Optional[str] = None
    phase_number: Optional[int] = None
    tags: list[str] = field(default_factory=list)

    def is_expired(self, as_of: Optional[datetime] = None) -> bool:
        """Check if artifact has expired."""
        if self.expires_at is None:
            return False
        now = as_of or datetime.now(timezone.utc)
        return now > self.expires_at

    def days_until_expiry(self, as_of: Optional[datetime] = None) -> Optional[int]:
        """Calculate days until expiry."""
        if self.expires_at is None:
            return None
        now = as_of or datetime.now(timezone.utc)
        delta = self.expires_at - now
        return max(0, delta.days)

    def to_dict(self) -> dict:
        return {
            "artifact_id": self.artifact_id,
            "artifact_class": self.artifact_class.value,
            "path": self.path,
            "created_at": self.created_at.isoformat(),
            "size_bytes": self.size_bytes,
            "content_hash": self.content_hash,
            "is_redacted": self.is_redacted,
            "is_encrypted": self.is_encrypted,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "run_id": self.run_id,
            "phase_number": self.phase_number,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ArtifactMetadata":
        return cls(
            artifact_id=data["artifact_id"],
            artifact_class=ArtifactClass(data["artifact_class"]),
            path=data["path"],
            created_at=datetime.fromisoformat(data["created_at"]),
            size_bytes=data.get("size_bytes", 0),
            content_hash=data.get("content_hash"),
            is_redacted=data.get("is_redacted", False),
            is_encrypted=data.get("is_encrypted", False),
            expires_at=(
                datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None
            ),
            run_id=data.get("run_id"),
            phase_number=data.get("phase_number"),
            tags=data.get("tags", []),
        )


@dataclass
class DeletionRecord:
    """Record of an artifact deletion."""

    artifact_id: str
    artifact_class: str
    path: str
    deleted_at: datetime
    reason: str
    deleted_by: str  # "auto" or operator name
    archived_to: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "artifact_id": self.artifact_id,
            "artifact_class": self.artifact_class,
            "path": self.path,
            "deleted_at": self.deleted_at.isoformat(),
            "reason": self.reason,
            "deleted_by": self.deleted_by,
            "archived_to": self.archived_to,
        }


class ArtifactRetentionManager:
    """Manages artifact retention lifecycle.

    Usage:
        manager = ArtifactRetentionManager(
            artifacts_dir=Path(".autonomous_runs/artifacts"),
            storage_dir=Path(".artifact_retention"),
        )

        # Register an artifact
        metadata = manager.register_artifact(
            path=Path("screenshots/page.png"),
            artifact_class=ArtifactClass.SCREENSHOT,
            run_id="run-001",
        )

        # Run cleanup
        deleted = manager.cleanup_expired()
    """

    def __init__(
        self,
        artifacts_dir: Optional[Path] = None,
        storage_dir: Optional[Path] = None,
        archive_dir: Optional[Path] = None,
    ):
        """Initialize the manager.

        Args:
            artifacts_dir: Root directory for artifacts
            storage_dir: Directory for metadata storage
            archive_dir: Directory for archived artifacts
        """
        self.artifacts_dir = artifacts_dir or Path(".autonomous_runs/artifacts")
        self.storage_dir = storage_dir or Path(".artifact_retention")
        self.archive_dir = archive_dir or Path("archive/artifacts")
        self._artifacts: dict[str, ArtifactMetadata] = {}
        self._policies: dict[ArtifactClass, RetentionPolicy] = DEFAULT_RETENTION_POLICIES.copy()
        self._deletion_log: list[DeletionRecord] = []
        self._load()

    def _load(self) -> None:
        """Load state from storage."""
        artifacts_file = self.storage_dir / "artifacts.json"
        if artifacts_file.exists():
            try:
                data = json.loads(artifacts_file.read_text(encoding="utf-8"))
                for art_id, art_data in data.get("artifacts", {}).items():
                    self._artifacts[art_id] = ArtifactMetadata.from_dict(art_data)
                self._deletion_log = [
                    DeletionRecord(
                        artifact_id=d["artifact_id"],
                        artifact_class=d["artifact_class"],
                        path=d["path"],
                        deleted_at=datetime.fromisoformat(d["deleted_at"]),
                        reason=d["reason"],
                        deleted_by=d["deleted_by"],
                        archived_to=d.get("archived_to"),
                    )
                    for d in data.get("deletion_log", [])
                ]
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load artifact metadata: {e}")

    def _save(self) -> None:
        """Save state to storage."""
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        artifacts_file = self.storage_dir / "artifacts.json"
        data = {
            "artifacts": {aid: a.to_dict() for aid, a in self._artifacts.items()},
            "deletion_log": [d.to_dict() for d in self._deletion_log[-1000:]],  # Keep last 1000
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        artifacts_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get_policy(self, artifact_class: ArtifactClass) -> RetentionPolicy:
        """Get retention policy for an artifact class."""
        return self._policies.get(
            artifact_class,
            RetentionPolicy(artifact_class=artifact_class, retention_days=30),
        )

    def set_policy(self, policy: RetentionPolicy) -> None:
        """Set a custom retention policy."""
        self._policies[policy.artifact_class] = policy

    def register_artifact(
        self,
        path: Path,
        artifact_class: ArtifactClass,
        run_id: Optional[str] = None,
        phase_number: Optional[int] = None,
        is_redacted: bool = False,
        is_encrypted: bool = False,
        content_hash: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> ArtifactMetadata:
        """Register an artifact for retention tracking.

        Args:
            path: Path to the artifact
            artifact_class: Classification of the artifact
            run_id: Associated run ID
            phase_number: Associated phase number
            is_redacted: Whether artifact has been redacted
            is_encrypted: Whether artifact is encrypted
            content_hash: Hash of content
            tags: Optional tags

        Returns:
            ArtifactMetadata for the registered artifact
        """
        import uuid

        now = datetime.now(timezone.utc)
        policy = self.get_policy(artifact_class)

        # Validate redaction/encryption requirements
        if policy.require_redaction and not is_redacted:
            logger.warning(f"Artifact {path} requires redaction (class={artifact_class.value})")

        if policy.require_encryption and not is_encrypted:
            logger.warning(f"Artifact {path} requires encryption (class={artifact_class.value})")

        # Calculate expiry
        expires_at = now + timedelta(days=policy.retention_days)

        # Get file size
        full_path = self.artifacts_dir / path if not path.is_absolute() else path
        size_bytes = full_path.stat().st_size if full_path.exists() else 0

        artifact_id = f"art-{uuid.uuid4().hex[:12]}"
        metadata = ArtifactMetadata(
            artifact_id=artifact_id,
            artifact_class=artifact_class,
            path=str(path),
            created_at=now,
            size_bytes=size_bytes,
            content_hash=content_hash,
            is_redacted=is_redacted,
            is_encrypted=is_encrypted,
            expires_at=expires_at,
            run_id=run_id,
            phase_number=phase_number,
            tags=tags or [],
        )

        self._artifacts[artifact_id] = metadata
        self._save()

        logger.info(
            f"Registered artifact: {artifact_id} ({artifact_class.value}) "
            f"expires in {policy.retention_days} days"
        )

        return metadata

    def get_artifact(self, artifact_id: str) -> Optional[ArtifactMetadata]:
        """Get artifact metadata by ID."""
        return self._artifacts.get(artifact_id)

    def get_artifacts_by_run(self, run_id: str) -> list[ArtifactMetadata]:
        """Get all artifacts for a run."""
        return [a for a in self._artifacts.values() if a.run_id == run_id]

    def get_artifacts_by_class(self, artifact_class: ArtifactClass) -> list[ArtifactMetadata]:
        """Get all artifacts of a class."""
        return [a for a in self._artifacts.values() if a.artifact_class == artifact_class]

    def get_expired_artifacts(self, as_of: Optional[datetime] = None) -> list[ArtifactMetadata]:
        """Get all expired artifacts."""
        return [a for a in self._artifacts.values() if a.is_expired(as_of)]

    def get_expiring_soon(
        self, days: int = 7, as_of: Optional[datetime] = None
    ) -> list[ArtifactMetadata]:
        """Get artifacts expiring within N days."""
        result = []
        for artifact in self._artifacts.values():
            days_left = artifact.days_until_expiry(as_of)
            if days_left is not None and days_left <= days:
                result.append(artifact)
        return result

    def delete_artifact(
        self,
        artifact_id: str,
        reason: str,
        deleted_by: str = "auto",
        archive: bool = False,
    ) -> bool:
        """Delete an artifact.

        Args:
            artifact_id: ID of artifact to delete
            reason: Reason for deletion
            deleted_by: Who is deleting
            archive: Whether to archive before deletion

        Returns:
            True if deleted successfully
        """
        metadata = self._artifacts.get(artifact_id)
        if not metadata:
            return False

        full_path = Path(metadata.path)
        if not full_path.is_absolute():
            full_path = self.artifacts_dir / metadata.path

        archived_to = None
        if archive and full_path.exists():
            # Archive the file
            archive_path = self.archive_dir / f"{metadata.artifact_class.value}" / full_path.name
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(full_path, archive_path)
            archived_to = str(archive_path)
            logger.info(f"Archived artifact to: {archive_path}")

        # Delete the file
        if full_path.exists():
            full_path.unlink()

        # Record deletion
        deletion = DeletionRecord(
            artifact_id=artifact_id,
            artifact_class=metadata.artifact_class.value,
            path=metadata.path,
            deleted_at=datetime.now(timezone.utc),
            reason=reason,
            deleted_by=deleted_by,
            archived_to=archived_to,
        )
        self._deletion_log.append(deletion)

        # Remove from tracking
        del self._artifacts[artifact_id]
        self._save()

        logger.info(
            f"Deleted artifact: {artifact_id} ({metadata.artifact_class.value}) "
            f"reason: {reason}"
        )

        return True

    def cleanup_expired(self, deleted_by: str = "auto") -> list[str]:
        """Delete all expired artifacts with auto_delete enabled.

        Args:
            deleted_by: Who is performing the cleanup

        Returns:
            List of deleted artifact IDs
        """
        deleted = []
        expired = self.get_expired_artifacts()

        for artifact in expired:
            policy = self.get_policy(artifact.artifact_class)
            if not policy.auto_delete:
                continue

            success = self.delete_artifact(
                artifact.artifact_id,
                reason="Retention period expired",
                deleted_by=deleted_by,
                archive=policy.archive_before_delete,
            )
            if success:
                deleted.append(artifact.artifact_id)

        if deleted:
            logger.info(f"Cleanup deleted {len(deleted)} expired artifacts")

        return deleted

    def get_retention_report(self) -> dict:
        """Generate retention report.

        Returns:
            Report dictionary safe for API/dashboard
        """
        now = datetime.now(timezone.utc)
        total_size = sum(a.size_bytes for a in self._artifacts.values())
        expired = self.get_expired_artifacts()
        expiring_soon = self.get_expiring_soon(days=7)

        by_class = {}
        for artifact_class in ArtifactClass:
            artifacts = self.get_artifacts_by_class(artifact_class)
            if artifacts:
                by_class[artifact_class.value] = {
                    "count": len(artifacts),
                    "total_bytes": sum(a.size_bytes for a in artifacts),
                    "policy": self.get_policy(artifact_class).to_dict(),
                }

        return {
            "generated_at": now.isoformat(),
            "total_artifacts": len(self._artifacts),
            "total_size_bytes": total_size,
            "expired_count": len(expired),
            "expiring_soon_count": len(expiring_soon),
            "by_class": by_class,
            "recent_deletions": [d.to_dict() for d in self._deletion_log[-10:]],
        }
