"""Tests for file operation logging in context_selector.py.

IMP-QUAL-004: Verifies that file operation failures are properly logged
instead of being silently swallowed.
"""

import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from autopack.context_selector import ContextSelector


class TestFileOperationLogging:
    """Test suite for file operation failure logging."""

    @pytest.fixture
    def temp_repo(self, tmp_path: Path) -> Path:
        """Create a temporary repository structure."""
        # Create some test files
        (tmp_path / "readable.txt").write_text("readable content")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "nested.txt").write_text("nested content")
        return tmp_path

    @pytest.fixture
    def selector(self, temp_repo: Path) -> ContextSelector:
        """Create a ContextSelector instance for the temp repo."""
        return ContextSelector(temp_repo)

    def test_get_files_by_paths_logs_permission_error(
        self, selector: ContextSelector, temp_repo: Path, caplog
    ):
        """Verify PermissionError is logged at WARNING level."""
        test_file = temp_repo / "test.txt"
        test_file.write_text("content")

        with patch.object(Path, "read_text", side_effect=PermissionError("Access denied")):
            with caplog.at_level(logging.WARNING):
                result = selector._get_files_by_paths(["test.txt"])

        assert result == {}
        assert "Permission denied reading" in caplog.text
        assert "Access denied" in caplog.text

    def test_get_files_by_paths_logs_unicode_decode_error(
        self, selector: ContextSelector, temp_repo: Path, caplog
    ):
        """Verify UnicodeDecodeError is logged at DEBUG level."""
        test_file = temp_repo / "binary.bin"
        test_file.write_bytes(b"\x80\x81\x82")

        with caplog.at_level(logging.DEBUG):
            result = selector._get_files_by_paths(["binary.bin"])

        assert result == {}
        assert "Unicode decode error reading" in caplog.text

    def test_get_files_by_paths_logs_os_error(
        self, selector: ContextSelector, temp_repo: Path, caplog
    ):
        """Verify OSError is logged at ERROR level."""
        test_file = temp_repo / "test.txt"
        test_file.write_text("content")

        with patch.object(Path, "read_text", side_effect=OSError("Disk error")):
            with caplog.at_level(logging.ERROR):
                result = selector._get_files_by_paths(["test.txt"])

        assert result == {}
        assert "OS error reading" in caplog.text
        assert "Disk error" in caplog.text

    def test_get_files_by_glob_logs_permission_error(
        self, selector: ContextSelector, temp_repo: Path, caplog
    ):
        """Verify PermissionError during glob is logged at WARNING level."""
        test_file = temp_repo / "test.py"
        test_file.write_text("content")

        with patch.object(Path, "read_text", side_effect=PermissionError("Access denied")):
            with caplog.at_level(logging.WARNING):
                result = selector._get_files_by_glob("*.py")

        assert result == {}
        assert "Permission denied reading" in caplog.text

    def test_get_files_by_glob_logs_glob_os_error(
        self, selector: ContextSelector, temp_repo: Path, caplog
    ):
        """Verify OSError during glob operation is logged at ERROR level."""
        with patch.object(Path, "glob", side_effect=OSError("Glob failed")):
            with caplog.at_level(logging.ERROR):
                result = selector._get_files_by_glob("*.py")

        assert result == {}
        assert "OS error during glob pattern" in caplog.text
        assert "Glob failed" in caplog.text

    def test_recency_score_logs_timeout(self, selector: ContextSelector, temp_repo: Path, caplog):
        """Verify subprocess timeout is logged at DEBUG level."""
        import subprocess

        test_file = temp_repo / "test.txt"
        test_file.write_text("content")

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 2)):
            with caplog.at_level(logging.DEBUG):
                score = selector._recency_score("test.txt")

        assert "Git log timed out" in caplog.text
        assert score >= 0  # Should still return a valid score

    def test_recency_score_logs_subprocess_error(
        self, selector: ContextSelector, temp_repo: Path, caplog
    ):
        """Verify subprocess error is logged at DEBUG level."""
        import subprocess

        test_file = temp_repo / "test.txt"
        test_file.write_text("content")

        with patch("subprocess.run", side_effect=subprocess.SubprocessError("Git failed")):
            with caplog.at_level(logging.DEBUG):
                score = selector._recency_score("test.txt")

        assert "Git subprocess error" in caplog.text
        assert score >= 0  # Should still return a valid score

    def test_get_mtime_score_logs_file_not_found(
        self, selector: ContextSelector, temp_repo: Path, caplog
    ):
        """Verify FileNotFoundError in mtime check is logged at DEBUG level."""
        non_existent = temp_repo / "does_not_exist.txt"

        with caplog.at_level(logging.DEBUG):
            score = selector._get_mtime_score(non_existent)

        assert score == 0.0
        assert "File not found for mtime check" in caplog.text

    def test_get_mtime_score_logs_permission_error(
        self, selector: ContextSelector, temp_repo: Path, caplog
    ):
        """Verify PermissionError in mtime check is logged at WARNING level."""
        test_file = temp_repo / "test.txt"
        test_file.write_text("content")

        with patch.object(Path, "stat", side_effect=PermissionError("Access denied")):
            with caplog.at_level(logging.WARNING):
                score = selector._get_mtime_score(test_file)

        assert score == 0.0
        assert "Permission denied checking mtime" in caplog.text

    def test_load_directory_files_logs_permission_error_on_file(
        self, selector: ContextSelector, temp_repo: Path, caplog
    ):
        """Verify PermissionError reading directory files is logged at WARNING level."""
        test_dir = temp_repo / "protected"
        test_dir.mkdir()
        test_file = test_dir / "file.txt"
        test_file.write_text("content")

        context = {}
        with patch.object(Path, "read_text", side_effect=PermissionError("Access denied")):
            with caplog.at_level(logging.WARNING):
                selector._load_directory_files(test_dir, context)

        assert context == {}
        assert "Permission denied reading" in caplog.text

    def test_load_directory_files_logs_directory_access_error(
        self, selector: ContextSelector, temp_repo: Path, caplog
    ):
        """Verify OSError accessing directory is logged at ERROR level."""
        test_dir = temp_repo / "protected"
        test_dir.mkdir()

        context = {}
        with patch.object(Path, "rglob", side_effect=OSError("Directory access error")):
            with caplog.at_level(logging.ERROR):
                selector._load_directory_files(test_dir, context)

        assert context == {}
        assert "OS error accessing directory" in caplog.text

    def test_build_scoped_context_logs_scope_file_errors(
        self, selector: ContextSelector, temp_repo: Path, caplog
    ):
        """Verify errors reading scope files are logged appropriately."""
        test_file = temp_repo / "scope_file.py"
        test_file.write_text("content")

        with patch.object(Path, "read_text", side_effect=PermissionError("Access denied")):
            with caplog.at_level(logging.WARNING):
                result = selector._build_scoped_context(
                    scope_paths=["scope_file.py"],
                    readonly_context=[],
                    token_budget=None,
                    phase_spec={},
                )

        assert result == {}
        assert "Permission denied reading scope file" in caplog.text

    def test_build_scoped_context_logs_readonly_errors(
        self, selector: ContextSelector, temp_repo: Path, caplog
    ):
        """Verify errors reading readonly context files are logged appropriately."""
        readonly_file = temp_repo / "readonly.txt"
        readonly_file.write_text("content")

        with patch.object(Path, "read_text", side_effect=PermissionError("Access denied")):
            with caplog.at_level(logging.WARNING):
                result = selector._build_scoped_context(
                    scope_paths=[],
                    readonly_context=["readonly.txt"],
                    token_budget=None,
                    phase_spec={},
                )

        assert result == {}
        assert "Permission denied reading readonly context" in caplog.text

    def test_successful_file_read_no_errors_logged(
        self, selector: ContextSelector, temp_repo: Path, caplog
    ):
        """Verify successful file reads don't log errors."""
        test_file = temp_repo / "success.txt"
        test_file.write_text("success content")

        with caplog.at_level(logging.DEBUG):
            result = selector._get_files_by_paths(["success.txt"])

        assert "success.txt" in result
        assert result["success.txt"] == "success content"
        assert "error" not in caplog.text.lower()
        assert "warning" not in caplog.text.lower()
