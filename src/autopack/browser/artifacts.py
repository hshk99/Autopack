"""Browser artifact storage and management.

Handles storage policy for browser-generated artifacts:
- Screenshots
- Videos (screen recordings)
- HAR logs (HTTP Archive)
- Session state

Integrates with the artifact retention system for lifecycle management.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..artifacts import ArtifactClass, ArtifactMetadata, ArtifactRedactor, ArtifactRetentionManager

logger = logging.getLogger(__name__)


@dataclass
class BrowserArtifactPolicy:
    """Policy for browser artifact storage."""

    max_screenshots_per_session: int = 20
    max_video_duration_seconds: int = 300
    max_har_size_mb: float = 10.0
    redact_before_storage: bool = True
    compress_videos: bool = True


class BrowserArtifactManager:
    """Manages browser automation artifacts.

    Handles storage, redaction, and lifecycle management for:
    - Screenshots (PNG)
    - Videos (WebM)
    - HAR logs (JSON)
    - Session summaries

    Integrates with ArtifactRetentionManager for automatic cleanup.

    Usage:
        manager = BrowserArtifactManager(
            base_dir=Path(".autonomous_runs/browser_artifacts"),
        )

        # Register a screenshot
        manager.register_screenshot(
            session_id="session_abc123",
            path=Path("screenshots/page.png"),
            run_id="run-001",
        )

        # Process HAR log with redaction
        manager.process_har(
            session_id="session_abc123",
            har_path=Path("network.har"),
        )
    """

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        policy: Optional[BrowserArtifactPolicy] = None,
        retention_manager: Optional[ArtifactRetentionManager] = None,
    ):
        """Initialize the manager.

        Args:
            base_dir: Base directory for browser artifacts
            policy: Storage policy
            retention_manager: Retention manager for lifecycle tracking
        """
        self._base_dir = base_dir or Path(".autonomous_runs/browser_artifacts")
        self._policy = policy or BrowserArtifactPolicy()
        self._retention = retention_manager or ArtifactRetentionManager(
            artifacts_dir=self._base_dir,
            storage_dir=self._base_dir / ".retention",
        )
        self._redactor = ArtifactRedactor()
        self._session_artifacts: dict[str, list[str]] = {}

    def _get_session_dir(self, session_id: str) -> Path:
        """Get directory for a session's artifacts."""
        return self._base_dir / session_id

    def register_screenshot(
        self,
        session_id: str,
        path: Path,
        run_id: Optional[str] = None,
        phase_number: Optional[int] = None,
    ) -> Optional[ArtifactMetadata]:
        """Register a screenshot artifact.

        Args:
            session_id: Browser session ID
            path: Path to screenshot file
            run_id: Associated run ID
            phase_number: Associated phase number

        Returns:
            ArtifactMetadata or None if limit exceeded
        """
        # Check session screenshot limit
        session_artifacts = self.get_session_artifacts(session_id)
        session_screenshots = [
            a for a in session_artifacts if a.artifact_class == ArtifactClass.SCREENSHOT
        ]
        if len(session_screenshots) >= self._policy.max_screenshots_per_session:
            logger.warning(
                f"Screenshot limit exceeded for session {session_id}: "
                f"{len(session_screenshots)}/{self._policy.max_screenshots_per_session}"
            )
            return None

        # Register with retention manager
        metadata = self._retention.register_artifact(
            path=path,
            artifact_class=ArtifactClass.SCREENSHOT,
            run_id=run_id,
            phase_number=phase_number,
            is_redacted=False,  # Screenshots aren't typically redacted
            tags=[f"session:{session_id}", "browser"],
        )

        # Track in session
        if session_id not in self._session_artifacts:
            self._session_artifacts[session_id] = []
        self._session_artifacts[session_id].append(metadata.artifact_id)

        return metadata

    def register_video(
        self,
        session_id: str,
        path: Path,
        run_id: Optional[str] = None,
        phase_number: Optional[int] = None,
    ) -> Optional[ArtifactMetadata]:
        """Register a video recording artifact.

        Args:
            session_id: Browser session ID
            path: Path to video file
            run_id: Associated run ID
            phase_number: Associated phase number

        Returns:
            ArtifactMetadata or None if validation fails
        """
        if not path.exists():
            logger.warning(f"Video file not found: {path}")
            return None

        # Check video size as proxy for duration
        size_mb = path.stat().st_size / (1024 * 1024)
        # Rough estimate: 1MB ~= 10 seconds at typical WebM compression
        estimated_duration = size_mb * 10

        if estimated_duration > self._policy.max_video_duration_seconds:
            logger.warning(
                f"Video may exceed duration limit: estimated {estimated_duration:.0f}s "
                f"(max {self._policy.max_video_duration_seconds}s)"
            )
            # Still register but tag as oversized
            tags = [f"session:{session_id}", "browser", "oversized"]
        else:
            tags = [f"session:{session_id}", "browser"]

        # Register with retention manager
        metadata = self._retention.register_artifact(
            path=path,
            artifact_class=ArtifactClass.VIDEO,
            run_id=run_id,
            phase_number=phase_number,
            is_redacted=False,
            tags=tags,
        )

        # Track in session
        if session_id not in self._session_artifacts:
            self._session_artifacts[session_id] = []
        self._session_artifacts[session_id].append(metadata.artifact_id)

        return metadata

    def process_har(
        self,
        session_id: str,
        har_path: Path,
        run_id: Optional[str] = None,
        phase_number: Optional[int] = None,
    ) -> Optional[ArtifactMetadata]:
        """Process and register a HAR log.

        Performs redaction of sensitive data before storage.

        Args:
            session_id: Browser session ID
            har_path: Path to HAR log file
            run_id: Associated run ID
            phase_number: Associated phase number

        Returns:
            ArtifactMetadata or None if validation fails
        """
        if not har_path.exists():
            logger.warning(f"HAR file not found: {har_path}")
            return None

        # Check size limit
        size_mb = har_path.stat().st_size / (1024 * 1024)
        if size_mb > self._policy.max_har_size_mb:
            logger.warning(
                f"HAR file exceeds size limit: {size_mb:.1f}MB "
                f"(max {self._policy.max_har_size_mb}MB)"
            )
            # Truncate or skip based on policy
            # For now, skip registration
            return None

        is_redacted = False
        if self._policy.redact_before_storage:
            # Redact HAR content
            try:
                har_data = json.loads(har_path.read_text(encoding="utf-8"))
                redacted_har = self._redactor.redact_har(har_data)

                # Write redacted version
                redacted_path = har_path.with_suffix(".redacted.har")
                redacted_path.write_text(json.dumps(redacted_har, indent=2), encoding="utf-8")

                # Remove original
                har_path.unlink()
                har_path = redacted_path
                is_redacted = True

                logger.info(f"Redacted HAR log: {har_path}")
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Failed to redact HAR: {e}")
                return None

        # Register with retention manager
        metadata = self._retention.register_artifact(
            path=har_path,
            artifact_class=ArtifactClass.HAR_LOG,
            run_id=run_id,
            phase_number=phase_number,
            is_redacted=is_redacted,
            tags=[f"session:{session_id}", "browser", "network"],
        )

        # Track in session
        if session_id not in self._session_artifacts:
            self._session_artifacts[session_id] = []
        self._session_artifacts[session_id].append(metadata.artifact_id)

        return metadata

    def process_session_summary(
        self,
        session_id: str,
        summary_path: Path,
        run_id: Optional[str] = None,
        phase_number: Optional[int] = None,
    ) -> Optional[ArtifactMetadata]:
        """Process and register a session summary.

        Args:
            session_id: Browser session ID
            summary_path: Path to session summary JSON
            run_id: Associated run ID
            phase_number: Associated phase number

        Returns:
            ArtifactMetadata
        """
        if not summary_path.exists():
            logger.warning(f"Session summary not found: {summary_path}")
            return None

        # Redact any sensitive data in summary
        try:
            summary_data = json.loads(summary_path.read_text(encoding="utf-8"))
            redacted = self._redactor.redact_dict(summary_data)
            summary_path.write_text(json.dumps(redacted, indent=2), encoding="utf-8")
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to redact summary: {e}")

        # Register with retention manager
        metadata = self._retention.register_artifact(
            path=summary_path,
            artifact_class=ArtifactClass.STRUCTURED_DATA,
            run_id=run_id,
            phase_number=phase_number,
            is_redacted=True,
            tags=[f"session:{session_id}", "browser", "summary"],
        )

        # Track in session
        if session_id not in self._session_artifacts:
            self._session_artifacts[session_id] = []
        self._session_artifacts[session_id].append(metadata.artifact_id)

        return metadata

    def process_session_artifacts(
        self,
        session_id: str,
        run_id: Optional[str] = None,
        phase_number: Optional[int] = None,
    ) -> dict:
        """Process all artifacts from a browser session.

        Scans the session directory and registers all artifacts.

        Args:
            session_id: Browser session ID
            run_id: Associated run ID
            phase_number: Associated phase number

        Returns:
            Summary of processed artifacts
        """
        session_dir = self._get_session_dir(session_id)
        if not session_dir.exists():
            return {"error": f"Session directory not found: {session_dir}"}

        results = {
            "session_id": session_id,
            "screenshots": [],
            "videos": [],
            "har_logs": [],
            "summaries": [],
            "errors": [],
        }

        # Process screenshots
        screenshots_dir = session_dir / "screenshots"
        if screenshots_dir.exists():
            for png_file in screenshots_dir.glob("*.png"):
                try:
                    metadata = self.register_screenshot(
                        session_id=session_id,
                        path=png_file,
                        run_id=run_id,
                        phase_number=phase_number,
                    )
                    if metadata:
                        results["screenshots"].append(metadata.artifact_id)
                except Exception as e:
                    results["errors"].append(f"Screenshot {png_file}: {e}")

        # Process videos
        videos_dir = session_dir / "videos"
        if videos_dir.exists():
            for video_file in videos_dir.glob("*.webm"):
                try:
                    metadata = self.register_video(
                        session_id=session_id,
                        path=video_file,
                        run_id=run_id,
                        phase_number=phase_number,
                    )
                    if metadata:
                        results["videos"].append(metadata.artifact_id)
                except Exception as e:
                    results["errors"].append(f"Video {video_file}: {e}")

        # Process HAR logs
        for har_file in session_dir.glob("*.har"):
            if ".redacted." in har_file.name:
                continue  # Skip already-redacted files
            try:
                metadata = self.process_har(
                    session_id=session_id,
                    har_path=har_file,
                    run_id=run_id,
                    phase_number=phase_number,
                )
                if metadata:
                    results["har_logs"].append(metadata.artifact_id)
            except Exception as e:
                results["errors"].append(f"HAR {har_file}: {e}")

        # Process session summary
        summary_file = session_dir / "session_summary.json"
        if summary_file.exists():
            try:
                metadata = self.process_session_summary(
                    session_id=session_id,
                    summary_path=summary_file,
                    run_id=run_id,
                    phase_number=phase_number,
                )
                if metadata:
                    results["summaries"].append(metadata.artifact_id)
            except Exception as e:
                results["errors"].append(f"Summary: {e}")

        results["total_artifacts"] = (
            len(results["screenshots"])
            + len(results["videos"])
            + len(results["har_logs"])
            + len(results["summaries"])
        )

        return results

    def get_session_artifacts(self, session_id: str) -> list[ArtifactMetadata]:
        """Get all artifacts for a session.

        Args:
            session_id: Browser session ID

        Returns:
            List of artifact metadata
        """
        artifact_ids = self._session_artifacts.get(session_id, [])
        return [
            self._retention.get_artifact(aid)
            for aid in artifact_ids
            if self._retention.get_artifact(aid) is not None
        ]

    def cleanup_session(self, session_id: str, reason: str = "session_ended") -> int:
        """Cleanup all artifacts for a session.

        Args:
            session_id: Browser session ID
            reason: Reason for cleanup

        Returns:
            Number of artifacts deleted
        """
        deleted = 0
        artifact_ids = self._session_artifacts.get(session_id, [])

        for aid in artifact_ids:
            if self._retention.delete_artifact(aid, reason=reason):
                deleted += 1

        # Clear session tracking
        if session_id in self._session_artifacts:
            del self._session_artifacts[session_id]

        # Remove session directory
        session_dir = self._get_session_dir(session_id)
        if session_dir.exists():
            import shutil

            shutil.rmtree(session_dir, ignore_errors=True)

        logger.info(f"Cleaned up session {session_id}: {deleted} artifacts deleted")
        return deleted

    def get_artifact_report(self) -> dict:
        """Get report of browser artifacts.

        Returns:
            Report dictionary
        """
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "active_sessions": len(self._session_artifacts),
            "artifacts_by_session": {
                sid: len(aids) for sid, aids in self._session_artifacts.items()
            },
            "retention_report": self._retention.get_retention_report(),
            "policy": {
                "max_screenshots_per_session": self._policy.max_screenshots_per_session,
                "max_video_duration_seconds": self._policy.max_video_duration_seconds,
                "max_har_size_mb": self._policy.max_har_size_mb,
                "redact_before_storage": self._policy.redact_before_storage,
            },
        }
