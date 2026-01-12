"""Contract tests for files router.

These tests verify the files router behavior contract is preserved
during the extraction from main.py to api/routes/files.py (PR-API-3b).
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestUploadEndpointContract:
    """Contract tests for the file upload endpoint."""

    @pytest.mark.asyncio
    async def test_upload_requires_file(self):
        """Contract: Upload returns 400 if no file provided."""
        from autopack.api.routes.files import upload_file
        from fastapi import HTTPException

        # Create mock request with empty form
        mock_request = MagicMock()
        mock_form = AsyncMock(return_value={})
        mock_request.form = mock_form

        with pytest.raises(HTTPException) as exc_info:
            await upload_file(mock_request)

        assert exc_info.value.status_code == 400
        assert "No file provided" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_upload_generates_unique_filename(self):
        """Contract: Upload generates unique UUID-based filename."""
        from autopack.api.routes.files import upload_file

        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create mock file object
            mock_file = MagicMock()
            mock_file.filename = "test.txt"
            mock_file.read = AsyncMock(side_effect=[b"test content", b""])

            # Create mock request
            mock_request = MagicMock()
            mock_form = AsyncMock(return_value={"file": mock_file})
            mock_request.form = mock_form

            # Patch settings to use temp directory
            with patch("autopack.api.routes.files.settings") as mock_settings:
                mock_settings.autonomous_runs_dir = tmp_dir

                result = await upload_file(mock_request)

        assert result["status"] == "success"
        assert result["filename"] == "test.txt"
        assert result["stored_as"].endswith(".txt")
        assert len(result["stored_as"]) == 36  # 32 hex + 4 for ".txt"

    @pytest.mark.asyncio
    async def test_upload_returns_relative_path(self):
        """Contract: Upload returns relative path, never absolute."""
        from autopack.api.routes.files import upload_file

        with tempfile.TemporaryDirectory() as tmp_dir:
            mock_file = MagicMock()
            mock_file.filename = "test.txt"
            mock_file.read = AsyncMock(side_effect=[b"test", b""])

            mock_request = MagicMock()
            mock_form = AsyncMock(return_value={"file": mock_file})
            mock_request.form = mock_form

            with patch("autopack.api.routes.files.settings") as mock_settings:
                mock_settings.autonomous_runs_dir = tmp_dir

                result = await upload_file(mock_request)

        # Path should be relative (security)
        assert result["relative_path"].startswith("_uploads/")
        assert not result["relative_path"].startswith("/")
        assert ":" not in result["relative_path"]  # No drive letter

    @pytest.mark.asyncio
    async def test_upload_streams_large_files(self):
        """Contract: Upload uses chunked streaming to avoid OOM."""
        from autopack.api.routes.files import upload_file

        with tempfile.TemporaryDirectory() as tmp_dir:
            # Simulate large file with multiple chunks
            chunk1 = b"x" * 64 * 1024  # 64KB
            chunk2 = b"y" * 64 * 1024  # 64KB
            chunk3 = b"z" * 1024  # 1KB

            mock_file = MagicMock()
            mock_file.filename = "large.bin"
            mock_file.read = AsyncMock(side_effect=[chunk1, chunk2, chunk3, b""])

            mock_request = MagicMock()
            mock_form = AsyncMock(return_value={"file": mock_file})
            mock_request.form = mock_form

            with patch("autopack.api.routes.files.settings") as mock_settings:
                mock_settings.autonomous_runs_dir = tmp_dir

                result = await upload_file(mock_request)

        # Total size should match all chunks
        expected_size = len(chunk1) + len(chunk2) + len(chunk3)
        assert result["size"] == expected_size

    @pytest.mark.asyncio
    async def test_upload_preserves_extension(self):
        """Contract: Upload preserves original file extension."""
        from autopack.api.routes.files import upload_file

        with tempfile.TemporaryDirectory() as tmp_dir:
            mock_file = MagicMock()
            mock_file.filename = "document.pdf"
            mock_file.read = AsyncMock(side_effect=[b"pdf content", b""])

            mock_request = MagicMock()
            mock_form = AsyncMock(return_value={"file": mock_file})
            mock_request.form = mock_form

            with patch("autopack.api.routes.files.settings") as mock_settings:
                mock_settings.autonomous_runs_dir = tmp_dir

                result = await upload_file(mock_request)

        assert result["stored_as"].endswith(".pdf")

    @pytest.mark.asyncio
    async def test_upload_handles_no_extension(self):
        """Contract: Upload handles files without extension."""
        from autopack.api.routes.files import upload_file

        with tempfile.TemporaryDirectory() as tmp_dir:
            mock_file = MagicMock()
            mock_file.filename = "Makefile"
            mock_file.read = AsyncMock(side_effect=[b"make content", b""])

            mock_request = MagicMock()
            mock_form = AsyncMock(return_value={"file": mock_file})
            mock_request.form = mock_form

            with patch("autopack.api.routes.files.settings") as mock_settings:
                mock_settings.autonomous_runs_dir = tmp_dir

                result = await upload_file(mock_request)

        # Should still work, just no extension
        assert result["status"] == "success"
        assert "." not in result["stored_as"]

    @pytest.mark.asyncio
    async def test_upload_creates_uploads_directory(self):
        """Contract: Upload creates _uploads directory if not exists."""
        from autopack.api.routes.files import upload_file

        with tempfile.TemporaryDirectory() as tmp_dir:
            mock_file = MagicMock()
            mock_file.filename = "test.txt"
            mock_file.read = AsyncMock(side_effect=[b"test", b""])

            mock_request = MagicMock()
            mock_form = AsyncMock(return_value={"file": mock_file})
            mock_request.form = mock_form

            with patch("autopack.api.routes.files.settings") as mock_settings:
                mock_settings.autonomous_runs_dir = tmp_dir

                await upload_file(mock_request)

            # Verify directory was created (check inside context manager)
            uploads_dir = Path(tmp_dir) / "_uploads"
            assert uploads_dir.exists()


class TestFilesRouterContract:
    """Contract tests for files router configuration."""

    def test_router_has_files_prefix(self):
        """Contract: Files router uses /files prefix."""
        from autopack.api.routes.files import router

        assert router.prefix == "/files"

    def test_router_has_files_tag(self):
        """Contract: Files router is tagged as 'files'."""
        from autopack.api.routes.files import router

        assert "files" in router.tags
