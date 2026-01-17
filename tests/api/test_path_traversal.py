"""Tests for path traversal defense (IMP-SEC-003).

Verifies that path traversal attacks are blocked, including:
- Direct traversal with ..
- URL encoded traversal (%2e%2e = ..)
- Double URL encoded traversal (%252e%252e)
- Mixed encoding attacks
- Windows-specific attacks (backslash, drive letters)
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch


@pytest.fixture
def run_with_artifacts(client, db_session, tmp_path):
    """Create a run with artifact files for testing."""
    from autopack import models

    run_id = "test-run-path-traversal"

    run = models.Run(
        id=run_id,
        state=models.RunState.DONE_SUCCESS,
        safety_profile="normal",
        run_scope="multi_tier",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    db_session.commit()

    # Create artifact directory structure
    run_dir = tmp_path / "autopack" / "runs" / run_id / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Create a test file
    (run_dir / "test_artifact.txt").write_text("Test artifact content\n")

    return run_id, run_dir


class TestPathTraversalBlocked:
    """Verify path traversal attempts are blocked."""

    def test_direct_traversal_blocked(self, client, run_with_artifacts):
        """Direct traversal with .. is blocked."""
        run_id, _ = run_with_artifacts

        response = client.get(f"/runs/{run_id}/artifacts/file?path=../../../etc/passwd")
        assert response.status_code == 400
        assert "traversal" in response.json()["detail"].lower()

    def test_url_encoded_traversal_blocked(self, client, run_with_artifacts):
        """URL encoded traversal (%2e%2e = ..) is blocked."""
        run_id, _ = run_with_artifacts

        # %2e%2e%2f = ../
        response = client.get(f"/runs/{run_id}/artifacts/file?path=%2e%2e%2f%2e%2e%2fetc/passwd")
        assert response.status_code == 400
        assert "traversal" in response.json()["detail"].lower()

    def test_double_encoded_traversal_blocked(self, client, run_with_artifacts):
        """Double URL encoded traversal (%252e%252e) is blocked."""
        run_id, _ = run_with_artifacts

        # %252e%252e%252f decodes first to %2e%2e%2f, then to ../
        response = client.get(f"/runs/{run_id}/artifacts/file?path=%252e%252e%252f%252e%252e%252f")
        assert response.status_code == 400
        assert "traversal" in response.json()["detail"].lower()

    def test_absolute_path_blocked(self, client, run_with_artifacts):
        """Absolute paths starting with / are blocked."""
        run_id, _ = run_with_artifacts

        response = client.get(f"/runs/{run_id}/artifacts/file?path=/etc/passwd")
        assert response.status_code == 400
        assert "absolute" in response.json()["detail"].lower()

    def test_windows_drive_letter_blocked(self, client, run_with_artifacts):
        """Windows drive letters (C:) are blocked."""
        run_id, _ = run_with_artifacts

        response = client.get(f"/runs/{run_id}/artifacts/file?path=C:/Windows/System32/config/SAM")
        assert response.status_code == 400
        assert "drive" in response.json()["detail"].lower()

    def test_backslash_traversal_blocked(self, client, run_with_artifacts):
        """Backslash traversal (Windows-style) is blocked."""
        run_id, _ = run_with_artifacts

        response = client.get(f"/runs/{run_id}/artifacts/file?path=..\\..\\etc\\passwd")
        assert response.status_code == 400
        assert "traversal" in response.json()["detail"].lower()

    def test_mixed_slash_traversal_blocked(self, client, run_with_artifacts):
        """Mixed forward/backslash traversal is blocked."""
        run_id, _ = run_with_artifacts

        response = client.get(f"/runs/{run_id}/artifacts/file?path=subdir/../../../etc/passwd")
        assert response.status_code == 400
        assert "traversal" in response.json()["detail"].lower()


class TestCanonicalPathResolution:
    """Verify canonical path resolution catches traversal after decoding."""

    def test_resolved_path_must_be_within_base(self, client, run_with_artifacts, tmp_path):
        """Even if substring checks pass, resolved path must be within base."""
        run_id, run_dir = run_with_artifacts

        with patch("autopack.api.routes.artifacts.RunFileLayout") as MockLayout:
            mock_instance = MockLayout.return_value
            mock_instance.base_dir = run_dir

            # A path that looks safe but resolves outside base
            # This tests the Path.resolve().relative_to() check
            response = client.get(f"/runs/{run_id}/artifacts/file?path=subdir/../../outside.txt")
            assert response.status_code == 400

    def test_valid_nested_path_allowed(self, client, run_with_artifacts, tmp_path):
        """Valid nested paths are allowed."""
        run_id, run_dir = run_with_artifacts

        # Create a nested file
        nested_dir = run_dir / "subdir"
        nested_dir.mkdir(exist_ok=True)
        (nested_dir / "nested.txt").write_text("Nested content\n")

        with patch("autopack.api.routes.artifacts.RunFileLayout") as MockLayout:
            mock_instance = MockLayout.return_value
            mock_instance.base_dir = run_dir

            response = client.get(f"/runs/{run_id}/artifacts/file?path=subdir/nested.txt")
            assert response.status_code == 200
            assert "Nested content" in response.text

    def test_valid_file_at_root_allowed(self, client, run_with_artifacts, tmp_path):
        """Valid files at artifact root are allowed."""
        run_id, run_dir = run_with_artifacts

        with patch("autopack.api.routes.artifacts.RunFileLayout") as MockLayout:
            mock_instance = MockLayout.return_value
            mock_instance.base_dir = run_dir

            response = client.get(f"/runs/{run_id}/artifacts/file?path=test_artifact.txt")
            assert response.status_code == 200
            assert "Test artifact content" in response.text
