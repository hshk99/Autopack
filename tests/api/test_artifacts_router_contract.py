"""Contract tests for artifacts router.

These tests verify the artifacts router behavior contract is preserved
during the extraction from main.py to api/routes/artifacts.py (PR-API-3g).
"""

import pytest


class TestArtifactsRouterContract:
    """Contract tests for artifacts router configuration."""

    def test_router_has_artifacts_tag(self):
        """Contract: Artifacts router is tagged as 'artifacts'."""
        from autopack.api.routes.artifacts import router

        assert "artifacts" in router.tags


class TestGetArtifactsIndexContract:
    """Contract tests for get_artifacts_index endpoint."""

    @pytest.mark.asyncio
    async def test_artifacts_index_returns_404_for_missing_run(self):
        """Contract: /runs/{run_id}/artifacts/index returns 404 for missing run."""
        from unittest.mock import MagicMock

        from fastapi import HTTPException

        from autopack.api.routes.artifacts import get_artifacts_index

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            await get_artifacts_index(run_id="nonexistent", db=mock_db, _auth="test")

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_artifacts_index_returns_expected_fields(self):
        """Contract: /runs/{run_id}/artifacts/index returns expected fields."""
        from unittest.mock import MagicMock, patch

        from autopack.api.routes.artifacts import get_artifacts_index

        mock_run = MagicMock()
        mock_run.id = "test-run"

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_run
        mock_db.query.return_value = mock_query

        # Mock RunFileLayout to avoid filesystem access
        with patch("autopack.api.routes.artifacts.RunFileLayout") as mock_layout_cls:
            mock_layout = MagicMock()
            mock_layout.base_dir.exists.return_value = False
            mock_layout_cls.return_value = mock_layout

            result = await get_artifacts_index(run_id="test-run", db=mock_db, _auth="test")

        assert "run_id" in result
        assert "artifacts" in result
        assert "total_size_bytes" in result
        assert result["run_id"] == "test-run"
        assert result["artifacts"] == []
        assert result["total_size_bytes"] == 0


class TestGetArtifactFileContract:
    """Contract tests for get_artifact_file endpoint."""

    @pytest.mark.asyncio
    async def test_artifact_file_rejects_path_traversal(self):
        """Contract: /runs/{run_id}/artifacts/file rejects path traversal."""
        from unittest.mock import MagicMock

        from fastapi import HTTPException

        from autopack.api.routes.artifacts import get_artifact_file

        mock_db = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await get_artifact_file(
                run_id="test-run", path="../../../etc/passwd", db=mock_db, _auth="test"
            )

        assert exc_info.value.status_code == 400
        assert "path traversal" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_artifact_file_rejects_absolute_paths(self):
        """Contract: /runs/{run_id}/artifacts/file rejects absolute paths."""
        from unittest.mock import MagicMock

        from fastapi import HTTPException

        from autopack.api.routes.artifacts import get_artifact_file

        mock_db = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await get_artifact_file(run_id="test-run", path="/etc/passwd", db=mock_db, _auth="test")

        assert exc_info.value.status_code == 400
        assert "absolute paths" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_artifact_file_rejects_windows_drive_letters(self):
        """Contract: /runs/{run_id}/artifacts/file rejects Windows drive letters."""
        from unittest.mock import MagicMock

        from fastapi import HTTPException

        from autopack.api.routes.artifacts import get_artifact_file

        mock_db = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await get_artifact_file(
                run_id="test-run", path="C:\\Windows\\System32", db=mock_db, _auth="test"
            )

        assert exc_info.value.status_code == 400
        assert "windows drive letters" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_artifact_file_returns_404_for_missing_run(self):
        """Contract: /runs/{run_id}/artifacts/file returns 404 for missing run."""
        from unittest.mock import MagicMock

        from fastapi import HTTPException

        from autopack.api.routes.artifacts import get_artifact_file

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            await get_artifact_file(run_id="nonexistent", path="file.txt", db=mock_db, _auth="test")

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_artifact_file_returns_404_for_missing_file(self):
        """Contract: /runs/{run_id}/artifacts/file returns 404 for missing file."""
        from pathlib import Path
        from unittest.mock import MagicMock, patch

        from fastapi import HTTPException

        from autopack.api.routes.artifacts import get_artifact_file

        mock_run = MagicMock()
        mock_run.id = "test-run"

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_run
        mock_db.query.return_value = mock_query

        # Mock RunFileLayout to avoid filesystem access
        with patch("autopack.api.routes.artifacts.RunFileLayout") as mock_layout_cls:
            mock_layout = MagicMock()
            # Create a mock base_dir path that exists but file doesn't
            mock_base = MagicMock(spec=Path)
            mock_base.resolve.return_value = Path("/runs/test-run")
            mock_layout.base_dir = mock_base

            # Mock the file path
            mock_file_path = MagicMock(spec=Path)
            mock_file_path.resolve.return_value = Path("/runs/test-run/file.txt")
            mock_file_path.exists.return_value = False
            mock_base.__truediv__ = MagicMock(return_value=mock_file_path)

            mock_layout_cls.return_value = mock_layout

            with pytest.raises(HTTPException) as exc_info:
                await get_artifact_file(
                    run_id="test-run", path="file.txt", db=mock_db, _auth="test"
                )

        assert exc_info.value.status_code == 404
        assert "file not found" in exc_info.value.detail.lower()


class TestGetBrowserArtifactsContract:
    """Contract tests for get_browser_artifacts endpoint."""

    @pytest.mark.asyncio
    async def test_browser_artifacts_returns_404_for_missing_run(self):
        """Contract: /runs/{run_id}/browser/artifacts returns 404 for missing run."""
        from unittest.mock import MagicMock

        from fastapi import HTTPException

        from autopack.api.routes.artifacts import get_browser_artifacts

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            await get_browser_artifacts(run_id="nonexistent", db=mock_db, _auth="test")

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_browser_artifacts_returns_expected_fields(self):
        """Contract: /runs/{run_id}/browser/artifacts returns expected fields."""
        from unittest.mock import MagicMock, patch

        from autopack.api.routes.artifacts import get_browser_artifacts

        mock_run = MagicMock()
        mock_run.id = "test-run"

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_run
        mock_db.query.return_value = mock_query

        # Mock RunFileLayout to avoid filesystem access
        with patch("autopack.api.routes.artifacts.RunFileLayout") as mock_layout_cls:
            mock_layout = MagicMock()
            mock_layout.base_dir.exists.return_value = False
            mock_layout_cls.return_value = mock_layout

            result = await get_browser_artifacts(run_id="test-run", db=mock_db, _auth="test")

        assert "run_id" in result
        assert "artifacts" in result
        assert "total_count" in result
        assert result["run_id"] == "test-run"
        assert result["artifacts"] == []
        assert result["total_count"] == 0
