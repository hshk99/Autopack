"""Tests for artifact endpoints (GAP-8.10.1)

Verifies:
- GET /runs/{run_id}/artifacts/index returns file list
- GET /runs/{run_id}/artifacts/file returns file content
- Path traversal attacks are blocked (security)
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch

# Uses shared client, db_session fixtures from conftest.py


@pytest.fixture
def run_with_artifacts(client, db_session, tmp_path):
    """Create a run with artifact files."""
    from autopack import models

    run_id = "test-run-artifacts"

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

    # Create test files
    (run_dir / "run_summary.md").write_text("# Test Run Summary\n")
    (run_dir / "phases").mkdir(exist_ok=True)
    (run_dir / "phases" / "phase_00_P1.md").write_text("# Phase 1\n")

    return run_id, run_dir


class TestArtifactsIndex:
    """Tests for GET /runs/{run_id}/artifacts/index endpoint."""

    def test_artifacts_index_run_not_found(self, client):
        """Returns 404 for non-existent run."""
        response = client.get("/runs/nonexistent/artifacts/index")
        assert response.status_code == 404

    def test_artifacts_index_empty_directory(self, client, db_session):
        """Returns empty list when run directory doesn't exist."""
        from autopack import models

        # Create a run without artifacts directory
        run = models.Run(
            id="run-no-dir",
            state=models.RunState.PHASE_EXECUTION,
            safety_profile="normal",
            run_scope="single_tier",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(run)
        db_session.commit()

        response = client.get("/runs/run-no-dir/artifacts/index")
        assert response.status_code == 200
        data = response.json()
        assert data["artifacts"] == []
        assert data["total_size_bytes"] == 0

    def test_artifacts_index_with_files(self, client, run_with_artifacts, tmp_path):
        """Returns list of artifact files."""
        run_id, run_dir = run_with_artifacts

        # Patch the RunFileLayout to use our temp directory
        with patch("autopack.main.RunFileLayout") as MockLayout:
            mock_instance = MockLayout.return_value
            mock_instance.base_dir = run_dir

            response = client.get(f"/runs/{run_id}/artifacts/index")
            assert response.status_code == 200

            data = response.json()
            assert data["run_id"] == run_id
            assert len(data["artifacts"]) >= 2  # At least our test files
            assert data["total_size_bytes"] > 0

            # Check artifact info structure
            paths = [a["path"] for a in data["artifacts"]]
            assert any("run_summary.md" in p for p in paths)


class TestArtifactFile:
    """Tests for GET /runs/{run_id}/artifacts/file endpoint."""

    def test_artifact_file_run_not_found(self, client):
        """Returns 404 for non-existent run."""
        response = client.get("/runs/nonexistent/artifacts/file?path=test.md")
        assert response.status_code == 404

    def test_artifact_file_path_traversal_dotdot(self, client, run_with_artifacts):
        """Blocks path traversal with '..' (security)."""
        run_id, _ = run_with_artifacts

        response = client.get(f"/runs/{run_id}/artifacts/file?path=../secrets.txt")
        assert response.status_code == 400
        assert "traversal" in response.json()["detail"].lower()

    def test_artifact_file_path_traversal_absolute(self, client, run_with_artifacts):
        """Blocks absolute paths (security)."""
        run_id, _ = run_with_artifacts

        response = client.get(f"/runs/{run_id}/artifacts/file?path=/etc/passwd")
        assert response.status_code == 400
        assert "absolute" in response.json()["detail"].lower()

    def test_artifact_file_path_traversal_windows_drive(self, client, run_with_artifacts):
        """Blocks Windows drive letters (security)."""
        run_id, _ = run_with_artifacts

        response = client.get(f"/runs/{run_id}/artifacts/file?path=C:/Windows/System32/config")
        assert response.status_code == 400
        assert "drive" in response.json()["detail"].lower()

    def test_artifact_file_success(self, client, run_with_artifacts, tmp_path):
        """Returns file content for valid path."""
        run_id, run_dir = run_with_artifacts

        with patch("autopack.main.RunFileLayout") as MockLayout:
            mock_instance = MockLayout.return_value
            mock_instance.base_dir = run_dir

            response = client.get(f"/runs/{run_id}/artifacts/file?path=run_summary.md")
            assert response.status_code == 200
            assert "Test Run Summary" in response.text

    def test_artifact_file_not_found(self, client, run_with_artifacts, tmp_path):
        """Returns 404 for non-existent file."""
        run_id, run_dir = run_with_artifacts

        with patch("autopack.main.RunFileLayout") as MockLayout:
            mock_instance = MockLayout.return_value
            mock_instance.base_dir = run_dir

            response = client.get(f"/runs/{run_id}/artifacts/file?path=nonexistent.txt")
            assert response.status_code == 404


class TestArtifactFileSecurity:
    """Security-focused tests for artifact file endpoint."""

    def test_path_traversal_encoded(self, client, run_with_artifacts):
        """Blocks URL-encoded path traversal."""
        run_id, _ = run_with_artifacts

        # %2e%2e = ..
        response = client.get(f"/runs/{run_id}/artifacts/file?path=%2e%2e/secrets.txt")
        assert response.status_code == 400

    def test_path_traversal_mixed(self, client, run_with_artifacts):
        """Blocks mixed traversal attempts."""
        run_id, _ = run_with_artifacts

        test_paths = [
            "phases/../../../etc/passwd",
            "phases/..\\..\\..\\windows\\system32",
            "..\\secrets.txt",
        ]

        for path in test_paths:
            response = client.get(f"/runs/{run_id}/artifacts/file?path={path}")
            assert response.status_code in (400, 403), f"Path should be blocked: {path}"
