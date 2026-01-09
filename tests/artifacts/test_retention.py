"""Tests for artifact retention management."""

import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile

from autopack.artifacts import (
    ArtifactClass,
    ArtifactMetadata,
    ArtifactRetentionManager,
    DEFAULT_RETENTION_POLICIES,
)


class TestArtifactClass:
    """Tests for ArtifactClass enum."""

    def test_all_classes_exist(self):
        """All expected artifact classes exist."""
        assert ArtifactClass.RUN_LOG
        assert ArtifactClass.SCREENSHOT
        assert ArtifactClass.HAR_LOG
        assert ArtifactClass.CREDENTIAL_ARTIFACT
        assert ArtifactClass.AUDIT_LOG


class TestRetentionPolicy:
    """Tests for RetentionPolicy."""

    def test_default_policies_exist(self):
        """Default policies exist for key classes."""
        assert ArtifactClass.RUN_LOG in DEFAULT_RETENTION_POLICIES
        assert ArtifactClass.HAR_LOG in DEFAULT_RETENTION_POLICIES
        assert ArtifactClass.CREDENTIAL_ARTIFACT in DEFAULT_RETENTION_POLICIES

    def test_har_log_requires_redaction(self):
        """HAR logs require redaction."""
        policy = DEFAULT_RETENTION_POLICIES[ArtifactClass.HAR_LOG]
        assert policy.require_redaction is True
        assert policy.require_encryption is True

    def test_credential_artifact_zero_retention(self):
        """Credential artifacts have zero retention."""
        policy = DEFAULT_RETENTION_POLICIES[ArtifactClass.CREDENTIAL_ARTIFACT]
        assert policy.retention_days == 0

    def test_audit_log_long_retention(self):
        """Audit logs have long retention."""
        policy = DEFAULT_RETENTION_POLICIES[ArtifactClass.AUDIT_LOG]
        assert policy.retention_days >= 365
        assert policy.auto_delete is False


class TestArtifactMetadata:
    """Tests for ArtifactMetadata."""

    def test_is_expired_false(self):
        """Non-expired artifact returns False."""
        metadata = ArtifactMetadata(
            artifact_id="art-123",
            artifact_class=ArtifactClass.RUN_LOG,
            path="logs/run.log",
            created_at=datetime.now(timezone.utc),
            size_bytes=1000,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        assert metadata.is_expired() is False

    def test_is_expired_true(self):
        """Expired artifact returns True."""
        metadata = ArtifactMetadata(
            artifact_id="art-456",
            artifact_class=ArtifactClass.DEBUG_LOG,
            path="logs/debug.log",
            created_at=datetime.now(timezone.utc) - timedelta(days=60),
            size_bytes=500,
            expires_at=datetime.now(timezone.utc) - timedelta(days=30),
        )
        assert metadata.is_expired() is True

    def test_is_expired_no_expiry(self):
        """Artifact without expiry never expires."""
        metadata = ArtifactMetadata(
            artifact_id="art-789",
            artifact_class=ArtifactClass.AUDIT_LOG,
            path="audit/record.json",
            created_at=datetime.now(timezone.utc),
            size_bytes=200,
            expires_at=None,
        )
        assert metadata.is_expired() is False

    def test_days_until_expiry(self):
        """days_until_expiry calculates correctly."""
        metadata = ArtifactMetadata(
            artifact_id="art-abc",
            artifact_class=ArtifactClass.RUN_LOG,
            path="logs/run.log",
            created_at=datetime.now(timezone.utc),
            size_bytes=100,
            expires_at=datetime.now(timezone.utc) + timedelta(days=10),
        )
        days = metadata.days_until_expiry()
        assert days is not None
        assert 9 <= days <= 10

    def test_to_dict_and_from_dict(self):
        """Round-trip serialization works."""
        original = ArtifactMetadata(
            artifact_id="art-xyz",
            artifact_class=ArtifactClass.SCREENSHOT,
            path="screenshots/page.png",
            created_at=datetime.now(timezone.utc),
            size_bytes=50000,
            content_hash="abc123",
            is_redacted=True,
            is_encrypted=False,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            run_id="run-001",
            phase_number=2,
            tags=["browser", "test"],
        )

        data = original.to_dict()
        restored = ArtifactMetadata.from_dict(data)

        assert restored.artifact_id == original.artifact_id
        assert restored.artifact_class == original.artifact_class
        assert restored.is_redacted == original.is_redacted
        assert restored.run_id == original.run_id


class TestArtifactRetentionManager:
    """Tests for ArtifactRetentionManager."""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_dir = Path(tmpdir) / "artifacts"
            storage_dir = Path(tmpdir) / "retention"
            archive_dir = Path(tmpdir) / "archive"
            artifacts_dir.mkdir()
            storage_dir.mkdir()
            yield {
                "artifacts_dir": artifacts_dir,
                "storage_dir": storage_dir,
                "archive_dir": archive_dir,
            }

    @pytest.fixture
    def manager(self, temp_dirs):
        """Create manager with temp dirs."""
        return ArtifactRetentionManager(
            artifacts_dir=temp_dirs["artifacts_dir"],
            storage_dir=temp_dirs["storage_dir"],
            archive_dir=temp_dirs["archive_dir"],
        )

    @pytest.fixture
    def sample_artifact(self, temp_dirs):
        """Create a sample artifact file."""
        path = temp_dirs["artifacts_dir"] / "test.log"
        path.write_text("Sample log content")
        return path

    def test_register_artifact(self, manager, sample_artifact):
        """register_artifact creates metadata."""
        metadata = manager.register_artifact(
            path=sample_artifact,
            artifact_class=ArtifactClass.RUN_LOG,
            run_id="run-001",
        )

        assert metadata.artifact_id.startswith("art-")
        assert metadata.artifact_class == ArtifactClass.RUN_LOG
        assert metadata.run_id == "run-001"
        assert metadata.expires_at is not None

    def test_get_artifact(self, manager, sample_artifact):
        """get_artifact retrieves by ID."""
        registered = manager.register_artifact(
            path=sample_artifact,
            artifact_class=ArtifactClass.DEBUG_LOG,
        )

        retrieved = manager.get_artifact(registered.artifact_id)
        assert retrieved is not None
        assert retrieved.artifact_id == registered.artifact_id

    def test_get_artifacts_by_run(self, manager, temp_dirs):
        """get_artifacts_by_run filters correctly."""
        # Create multiple artifacts
        for i in range(3):
            path = temp_dirs["artifacts_dir"] / f"log{i}.log"
            path.write_text(f"Log {i}")
            manager.register_artifact(
                path=path,
                artifact_class=ArtifactClass.RUN_LOG,
                run_id=f"run-{i % 2}",  # run-0 or run-1
            )

        run0_artifacts = manager.get_artifacts_by_run("run-0")
        assert len(run0_artifacts) == 2

    def test_get_artifacts_by_class(self, manager, temp_dirs):
        """get_artifacts_by_class filters correctly."""
        # Create different artifact types
        log_path = temp_dirs["artifacts_dir"] / "log.log"
        log_path.write_text("Log")
        screenshot_path = temp_dirs["artifacts_dir"] / "page.png"
        screenshot_path.write_text("PNG data")

        manager.register_artifact(path=log_path, artifact_class=ArtifactClass.RUN_LOG)
        manager.register_artifact(path=screenshot_path, artifact_class=ArtifactClass.SCREENSHOT)

        logs = manager.get_artifacts_by_class(ArtifactClass.RUN_LOG)
        screenshots = manager.get_artifacts_by_class(ArtifactClass.SCREENSHOT)

        assert len(logs) == 1
        assert len(screenshots) == 1

    def test_get_expired_artifacts(self, manager, sample_artifact):
        """get_expired_artifacts returns expired items."""
        metadata = manager.register_artifact(
            path=sample_artifact,
            artifact_class=ArtifactClass.DEBUG_LOG,
        )

        # Manually expire it
        metadata.expires_at = datetime.now(timezone.utc) - timedelta(days=1)

        expired = manager.get_expired_artifacts()
        assert len(expired) == 1
        assert expired[0].artifact_id == metadata.artifact_id

    def test_delete_artifact(self, manager, sample_artifact):
        """delete_artifact removes file and metadata."""
        metadata = manager.register_artifact(
            path=sample_artifact,
            artifact_class=ArtifactClass.DEBUG_LOG,
        )

        assert sample_artifact.exists()

        success = manager.delete_artifact(
            metadata.artifact_id,
            reason="Test deletion",
            deleted_by="test",
        )

        assert success is True
        assert not sample_artifact.exists()
        assert manager.get_artifact(metadata.artifact_id) is None

    def test_delete_artifact_with_archive(self, manager, sample_artifact, temp_dirs):
        """delete_artifact can archive before deletion."""
        metadata = manager.register_artifact(
            path=sample_artifact,
            artifact_class=ArtifactClass.RUN_LOG,
        )

        success = manager.delete_artifact(
            metadata.artifact_id,
            reason="Archiving test",
            deleted_by="test",
            archive=True,
        )

        assert success is True
        assert not sample_artifact.exists()

        # Check archive
        archive_files = list(temp_dirs["archive_dir"].rglob("*"))
        assert len([f for f in archive_files if f.is_file()]) == 1

    def test_cleanup_expired(self, manager, temp_dirs):
        """cleanup_expired deletes expired auto-delete artifacts."""
        # Create artifact with short retention
        path = temp_dirs["artifacts_dir"] / "temp.log"
        path.write_text("Temporary")

        metadata = manager.register_artifact(
            path=path,
            artifact_class=ArtifactClass.DEBUG_LOG,
        )

        # Manually expire it
        metadata.expires_at = datetime.now(timezone.utc) - timedelta(days=1)

        deleted = manager.cleanup_expired()
        assert len(deleted) == 1
        assert metadata.artifact_id in deleted
        assert not path.exists()

    def test_cleanup_expired_skips_no_auto_delete(self, manager, temp_dirs):
        """cleanup_expired skips artifacts with auto_delete=False."""
        # Create audit log (no auto delete)
        path = temp_dirs["artifacts_dir"] / "audit.json"
        path.write_text("{}")

        metadata = manager.register_artifact(
            path=path,
            artifact_class=ArtifactClass.AUDIT_LOG,
        )

        # Manually expire it
        metadata.expires_at = datetime.now(timezone.utc) - timedelta(days=1)

        deleted = manager.cleanup_expired()
        assert len(deleted) == 0
        assert path.exists()  # Not deleted

    def test_get_retention_report(self, manager, temp_dirs):
        """get_retention_report returns summary."""
        # Create some artifacts
        for i in range(3):
            path = temp_dirs["artifacts_dir"] / f"log{i}.log"
            path.write_text(f"Log {i}")
            manager.register_artifact(path=path, artifact_class=ArtifactClass.RUN_LOG)

        report = manager.get_retention_report()

        assert report["total_artifacts"] == 3
        assert "by_class" in report
        assert "run_log" in report["by_class"]
        assert report["by_class"]["run_log"]["count"] == 3

    def test_persistence(self, temp_dirs):
        """State persists across manager instances."""
        # Create and register with first manager
        manager1 = ArtifactRetentionManager(
            artifacts_dir=temp_dirs["artifacts_dir"],
            storage_dir=temp_dirs["storage_dir"],
            archive_dir=temp_dirs["archive_dir"],
        )

        path = temp_dirs["artifacts_dir"] / "persist.log"
        path.write_text("Persistent")
        metadata = manager1.register_artifact(
            path=path,
            artifact_class=ArtifactClass.RUN_LOG,
            run_id="run-persist",
        )

        # Load with new manager
        manager2 = ArtifactRetentionManager(
            artifacts_dir=temp_dirs["artifacts_dir"],
            storage_dir=temp_dirs["storage_dir"],
            archive_dir=temp_dirs["archive_dir"],
        )

        loaded = manager2.get_artifact(metadata.artifact_id)
        assert loaded is not None
        assert loaded.run_id == "run-persist"


class TestRetentionWithRedaction:
    """Tests for redaction requirement enforcement."""

    @pytest.fixture
    def temp_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_dir = Path(tmpdir) / "artifacts"
            storage_dir = Path(tmpdir) / "retention"
            archive_dir = Path(tmpdir) / "archive"
            artifacts_dir.mkdir()
            storage_dir.mkdir()
            yield {
                "artifacts_dir": artifacts_dir,
                "storage_dir": storage_dir,
                "archive_dir": archive_dir,
            }

    def test_har_log_warns_without_redaction(self, temp_dirs, caplog):
        """HAR log registration warns if not redacted."""
        manager = ArtifactRetentionManager(
            artifacts_dir=temp_dirs["artifacts_dir"],
            storage_dir=temp_dirs["storage_dir"],
            archive_dir=temp_dirs["archive_dir"],
        )

        path = temp_dirs["artifacts_dir"] / "trace.har"
        path.write_text("{}")

        # Register without redaction flag
        manager.register_artifact(
            path=path,
            artifact_class=ArtifactClass.HAR_LOG,
            is_redacted=False,
        )

        assert "requires redaction" in caplog.text.lower()

    def test_har_log_no_warning_when_redacted(self, temp_dirs, caplog):
        """HAR log registration no warning when redacted."""
        manager = ArtifactRetentionManager(
            artifacts_dir=temp_dirs["artifacts_dir"],
            storage_dir=temp_dirs["storage_dir"],
            archive_dir=temp_dirs["archive_dir"],
        )

        path = temp_dirs["artifacts_dir"] / "trace.har"
        path.write_text("{}")

        # Register with redaction flag
        manager.register_artifact(
            path=path,
            artifact_class=ArtifactClass.HAR_LOG,
            is_redacted=True,
            is_encrypted=True,
        )

        assert "requires redaction" not in caplog.text.lower()
