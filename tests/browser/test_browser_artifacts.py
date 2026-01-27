"""Tests for browser artifact management."""

import json
import tempfile
from pathlib import Path

from autopack.artifacts import ArtifactClass
from autopack.browser.artifacts import BrowserArtifactManager, BrowserArtifactPolicy


class TestBrowserArtifactPolicy:
    """Tests for BrowserArtifactPolicy."""

    def test_default_policy(self):
        """Test default policy values."""
        policy = BrowserArtifactPolicy()
        assert policy.max_screenshots_per_session == 20
        assert policy.max_video_duration_seconds == 300
        assert policy.max_har_size_mb == 10.0
        assert policy.redact_before_storage is True
        assert policy.compress_videos is True

    def test_custom_policy(self):
        """Test custom policy values."""
        policy = BrowserArtifactPolicy(
            max_screenshots_per_session=10,
            max_har_size_mb=5.0,
            redact_before_storage=False,
        )
        assert policy.max_screenshots_per_session == 10
        assert policy.max_har_size_mb == 5.0
        assert policy.redact_before_storage is False


class TestBrowserArtifactManager:
    """Tests for BrowserArtifactManager."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.base_dir = Path(self.temp_dir) / "browser_artifacts"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.manager = BrowserArtifactManager(base_dir=self.base_dir)

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_initialization(self):
        """Test manager initialization."""
        assert self.manager._base_dir == self.base_dir
        assert self.manager._policy is not None

    def test_get_session_dir(self):
        """Test session directory path."""
        session_dir = self.manager._get_session_dir("session_abc123")
        assert session_dir == self.base_dir / "session_abc123"

    def test_register_screenshot(self):
        """Test screenshot registration."""
        session_id = "session_test1"
        session_dir = self.base_dir / session_id / "screenshots"
        session_dir.mkdir(parents=True)

        # Create a test screenshot
        screenshot_path = session_dir / "test.png"
        screenshot_path.write_bytes(b"\x89PNG\r\n\x1a\n")  # PNG magic bytes

        metadata = self.manager.register_screenshot(
            session_id=session_id,
            path=screenshot_path,
            run_id="run-001",
        )

        assert metadata is not None
        assert metadata.artifact_class == ArtifactClass.SCREENSHOT
        assert "session:session_test1" in metadata.tags
        assert "browser" in metadata.tags

    def test_screenshot_limit(self):
        """Test screenshot limit enforcement."""
        session_id = "session_limited"
        session_dir = self.base_dir / session_id / "screenshots"
        session_dir.mkdir(parents=True)

        # Set low limit
        self.manager._policy = BrowserArtifactPolicy(max_screenshots_per_session=2)

        # Register screenshots up to limit
        for i in range(3):
            path = session_dir / f"screenshot_{i}.png"
            path.write_bytes(b"\x89PNG\r\n\x1a\n")
            result = self.manager.register_screenshot(session_id, path)

            if i < 2:
                assert result is not None
            else:
                # Third screenshot should be rejected
                assert result is None

    def test_register_video(self):
        """Test video registration."""
        session_id = "session_video"
        videos_dir = self.base_dir / session_id / "videos"
        videos_dir.mkdir(parents=True)

        # Create a test video file
        video_path = videos_dir / "recording.webm"
        video_path.write_bytes(b"\x1a\x45\xdf\xa3")  # WebM magic bytes

        metadata = self.manager.register_video(
            session_id=session_id,
            path=video_path,
            run_id="run-002",
        )

        assert metadata is not None
        assert metadata.artifact_class == ArtifactClass.VIDEO

    def test_register_video_missing_file(self):
        """Test video registration with missing file."""
        metadata = self.manager.register_video(
            session_id="session_missing",
            path=Path("/nonexistent/video.webm"),
        )
        assert metadata is None

    def test_process_har(self):
        """Test HAR log processing with redaction."""
        session_id = "session_har"
        session_dir = self.base_dir / session_id
        session_dir.mkdir(parents=True)

        # Create a test HAR with sensitive data
        har_data = {
            "log": {
                "entries": [
                    {
                        "request": {
                            "url": "https://api.example.com/data",
                            "headers": [
                                {"name": "Authorization", "value": "Bearer secret123"},
                                {"name": "Content-Type", "value": "application/json"},
                            ],
                            "cookies": [
                                {"name": "session", "value": "abc123"},
                            ],
                        },
                        "response": {
                            "headers": [],
                            "content": {"text": "password=secret"},
                        },
                    }
                ]
            }
        }

        har_path = session_dir / "network.har"
        har_path.write_text(json.dumps(har_data), encoding="utf-8")

        metadata = self.manager.process_har(
            session_id=session_id,
            har_path=har_path,
            run_id="run-003",
        )

        assert metadata is not None
        assert metadata.artifact_class == ArtifactClass.HAR_LOG
        assert metadata.is_redacted is True

        # Verify redaction occurred
        redacted_path = session_dir / "network.redacted.har"
        assert redacted_path.exists()

        redacted_data = json.loads(redacted_path.read_text(encoding="utf-8"))
        # Check that Authorization header was redacted
        auth_header = redacted_data["log"]["entries"][0]["request"]["headers"][0]
        assert auth_header["value"] == "[REDACTED]"

    def test_process_har_too_large(self):
        """Test HAR log size limit."""
        self.manager._policy = BrowserArtifactPolicy(max_har_size_mb=0.001)  # 1KB

        session_id = "session_large_har"
        session_dir = self.base_dir / session_id
        session_dir.mkdir(parents=True)

        # Create a large HAR file
        har_path = session_dir / "large.har"
        har_path.write_text("x" * 2000, encoding="utf-8")  # 2KB

        metadata = self.manager.process_har(session_id, har_path)
        assert metadata is None  # Should be rejected due to size

    def test_process_session_summary(self):
        """Test session summary processing."""
        session_id = "session_summary"
        session_dir = self.base_dir / session_id
        session_dir.mkdir(parents=True)

        summary_data = {
            "start_time": "2026-01-09T10:00:00Z",
            "total_actions": 5,
            "actions": [
                {"type": "click", "selector": "button"},
                {"type": "fill", "value": "password=secret123"},
            ],
        }

        summary_path = session_dir / "session_summary.json"
        summary_path.write_text(json.dumps(summary_data), encoding="utf-8")

        metadata = self.manager.process_session_summary(
            session_id=session_id,
            summary_path=summary_path,
            run_id="run-004",
        )

        assert metadata is not None
        assert metadata.artifact_class == ArtifactClass.STRUCTURED_DATA

    def test_process_session_artifacts(self):
        """Test processing all session artifacts."""
        session_id = "session_full"
        session_dir = self.base_dir / session_id
        screenshots_dir = session_dir / "screenshots"
        screenshots_dir.mkdir(parents=True)

        # Create test artifacts
        (screenshots_dir / "page1.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (screenshots_dir / "page2.png").write_bytes(b"\x89PNG\r\n\x1a\n")

        summary = {
            "total_actions": 2,
        }
        (session_dir / "session_summary.json").write_text(json.dumps(summary), encoding="utf-8")

        result = self.manager.process_session_artifacts(
            session_id=session_id,
            run_id="run-005",
        )

        assert "error" not in result
        assert len(result["screenshots"]) == 2
        assert len(result["summaries"]) == 1
        assert result["total_artifacts"] == 3

    def test_get_session_artifacts(self):
        """Test getting artifacts for a session."""
        session_id = "session_get"
        session_dir = self.base_dir / session_id / "screenshots"
        session_dir.mkdir(parents=True)

        # Register an artifact
        path = session_dir / "test.png"
        path.write_bytes(b"\x89PNG\r\n\x1a\n")
        self.manager.register_screenshot(session_id, path)

        artifacts = self.manager.get_session_artifacts(session_id)
        assert len(artifacts) == 1

    def test_cleanup_session(self):
        """Test session cleanup."""
        session_id = "session_cleanup"
        session_dir = self.base_dir / session_id / "screenshots"
        session_dir.mkdir(parents=True)

        # Register an artifact
        path = session_dir / "test.png"
        path.write_bytes(b"\x89PNG\r\n\x1a\n")
        self.manager.register_screenshot(session_id, path)

        # Cleanup
        deleted = self.manager.cleanup_session(session_id)

        assert deleted == 1
        assert not (self.base_dir / session_id).exists()

    def test_get_artifact_report(self):
        """Test artifact report generation."""
        session_id = "session_report"
        session_dir = self.base_dir / session_id / "screenshots"
        session_dir.mkdir(parents=True)

        path = session_dir / "test.png"
        path.write_bytes(b"\x89PNG\r\n\x1a\n")
        self.manager.register_screenshot(session_id, path)

        report = self.manager.get_artifact_report()

        assert "generated_at" in report
        assert "active_sessions" in report
        assert report["active_sessions"] == 1
        assert "policy" in report
        assert "retention_report" in report
