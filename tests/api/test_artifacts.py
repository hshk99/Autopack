"""Tests for artifact endpoints (GAP-8.10.1)

Verifies:
- GET /runs/{run_id}/artifacts/index returns file list
- GET /runs/{run_id}/artifacts/file returns file content
- GET /runs/{run_id}/artifacts/code-generation returns code artifacts (IMP-ARTIFACT-001)
- Path traversal attacks are blocked (security)
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

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


@pytest.fixture
def run_with_code_artifacts(client, db_session, tmp_path):
    """Create a run with code generation artifacts."""
    from autopack import models

    run_id = "test-run-code-gen"

    run = models.Run(
        id=run_id,
        state=models.RunState.DONE_SUCCESS,
        safety_profile="normal",
        run_scope="multi_tier",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    db_session.commit()

    # Create artifact directory structure with code files
    run_dir = tmp_path / "autopack" / "runs" / run_id / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Create code files in src directory
    (run_dir / "src").mkdir(exist_ok=True)
    (run_dir / "src" / "main.py").write_text("#!/usr/bin/env python\n# Generated code\n")
    (run_dir / "src" / "utils.ts").write_text("// TypeScript utility\nexport function helper() {}\n")
    (run_dir / "src" / "helper.js").write_text("// JavaScript helper\nmodule.exports = {};\n")

    # Create config files
    (run_dir / "config").mkdir(exist_ok=True)
    (run_dir / "config" / "settings.yaml").write_text("debug: true\n")
    (run_dir / "config" / "app.json").write_text("{}\n")

    # Create non-code artifacts
    (run_dir / "docs").mkdir(exist_ok=True)
    (run_dir / "docs" / "README.md").write_text("# Documentation\n")

    # Create excluded directory (should be filtered out)
    (run_dir / "node_modules").mkdir(exist_ok=True)
    (run_dir / "node_modules" / "package.js").write_text("// Should be excluded\n")

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
        with patch("autopack.api.routes.artifacts.RunFileLayout") as MockLayout:
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

    def test_artifact_file_run_not_found(self, client, db_session):
        """Returns 404 for non-existent run after security checks pass."""
        # Use a valid-looking path that passes security checks
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

        with patch("autopack.api.routes.artifacts.RunFileLayout") as MockLayout:
            mock_instance = MockLayout.return_value
            mock_instance.base_dir = run_dir

            response = client.get(f"/runs/{run_id}/artifacts/file?path=run_summary.md")
            assert response.status_code == 200
            assert "Test Run Summary" in response.text

    def test_artifact_file_not_found(self, client, run_with_artifacts, tmp_path):
        """Returns 404 for non-existent file."""
        run_id, run_dir = run_with_artifacts

        with patch("autopack.api.routes.artifacts.RunFileLayout") as MockLayout:
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


class TestCodeGenerationArtifacts:
    """Tests for GET /runs/{run_id}/artifacts/code-generation endpoint (IMP-ARTIFACT-001)."""

    def test_code_generation_artifacts_run_not_found(self, client):
        """Returns 404 for non-existent run."""
        response = client.get("/runs/nonexistent/artifacts/code-generation")
        assert response.status_code == 404

    def test_code_generation_artifacts_empty_directory(self, client, db_session):
        """Returns empty list when run directory doesn't exist."""
        from autopack import models

        # Create a run without artifacts directory
        run = models.Run(
            id="run-no-code",
            state=models.RunState.PHASE_EXECUTION,
            safety_profile="normal",
            run_scope="single_tier",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(run)
        db_session.commit()

        response = client.get("/runs/run-no-code/artifacts/code-generation")
        assert response.status_code == 200
        data = response.json()
        assert data["artifacts"] == []
        assert data["total_size_bytes"] == 0
        assert data["total_count"] == 0

    def test_code_generation_artifacts_with_files(self, client, run_with_code_artifacts):
        """Returns list of code generation artifacts."""
        run_id, run_dir = run_with_code_artifacts

        with patch("autopack.api.routes.artifacts.RunFileLayout") as MockLayout:
            mock_instance = MockLayout.return_value
            mock_instance.base_dir = run_dir

            response = client.get(f"/runs/{run_id}/artifacts/code-generation")
            assert response.status_code == 200

            data = response.json()
            assert data["run_id"] == run_id
            assert data["total_count"] == 5  # 3 code files + 2 config files
            assert data["total_size_bytes"] > 0

            # Verify correct files are included
            paths = [a["path"] for a in data["artifacts"]]
            assert any("main.py" in p for p in paths)
            assert any("utils.ts" in p for p in paths)
            assert any("helper.js" in p for p in paths)
            assert any("settings.yaml" in p for p in paths)
            assert any("app.json" in p for p in paths)

            # Verify non-code files are excluded
            assert not any("README.md" in p for p in paths)

            # Verify excluded directories are not included
            assert not any("node_modules" in p for p in paths)

    def test_code_generation_artifacts_file_types(self, client, run_with_code_artifacts):
        """Verifies correct file type classification."""
        run_id, run_dir = run_with_code_artifacts

        with patch("autopack.api.routes.artifacts.RunFileLayout") as MockLayout:
            mock_instance = MockLayout.return_value
            mock_instance.base_dir = run_dir

            response = client.get(f"/runs/{run_id}/artifacts/code-generation")
            assert response.status_code == 200

            data = response.json()
            # Normalize paths to use forward slashes for cross-platform compatibility
            artifacts = {a["path"].replace("\\", "/"): a for a in data["artifacts"]}

            # Check file type classifications
            assert artifacts["src/main.py"]["type"] == "python"
            assert artifacts["src/utils.ts"]["type"] == "typescript"
            assert artifacts["src/helper.js"]["type"] == "javascript"
            assert artifacts["config/settings.yaml"]["type"] == "config"
            assert artifacts["config/app.json"]["type"] == "config"

    def test_code_generation_artifacts_metadata(self, client, run_with_code_artifacts):
        """Verifies artifact metadata is complete."""
        run_id, run_dir = run_with_code_artifacts

        with patch("autopack.api.routes.artifacts.RunFileLayout") as MockLayout:
            mock_instance = MockLayout.return_value
            mock_instance.base_dir = run_dir

            response = client.get(f"/runs/{run_id}/artifacts/code-generation")
            assert response.status_code == 200

            data = response.json()

            # Verify response structure
            assert "run_id" in data
            assert "artifacts" in data
            assert "total_size_bytes" in data
            assert "total_count" in data

            # Verify artifact structure
            for artifact in data["artifacts"]:
                assert "path" in artifact
                assert "type" in artifact
                assert "size_bytes" in artifact
                assert "modified_at" in artifact
                assert artifact["size_bytes"] > 0
                assert artifact["modified_at"]  # Should have timestamp
