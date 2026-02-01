"""
Tests for StorageScanner.scan_drive method.

Verifies IMP-013 fix: scan_drive implementation that was referenced but not defined.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from autopack.storage_optimizer.scanner import StorageScanner


class TestScanDriveMethod:
    """Tests for the scan_drive method."""

    def test_scan_drive_exists(self):
        """Verify scan_drive method exists on StorageScanner."""
        scanner = StorageScanner()
        assert hasattr(scanner, "scan_drive")
        assert callable(scanner.scan_drive)

    def test_scan_drive_windows_single_letter(self, tmp_path):
        """Test scan_drive with single letter drive (Windows style)."""
        scanner = StorageScanner(max_depth=1)

        # Create test structure
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        # Mock to use tmp_path instead of actual drive
        with patch.object(scanner, "scan_directory") as mock_scan:
            mock_scan.return_value = []
            scanner.scan_drive("C")
            mock_scan.assert_called_once()
            call_args = mock_scan.call_args
            assert call_args[0][0] == "C:\\"

    def test_scan_drive_windows_with_colon(self, tmp_path):
        """Test scan_drive with drive letter and colon (C:)."""
        scanner = StorageScanner(max_depth=1)

        with patch.object(scanner, "scan_directory") as mock_scan:
            mock_scan.return_value = []
            scanner.scan_drive("D:")
            mock_scan.assert_called_once()
            call_args = mock_scan.call_args
            assert call_args[0][0] == "D:\\"

    def test_scan_drive_windows_full_path(self, tmp_path):
        """Test scan_drive with full Windows path (C:\\)."""
        scanner = StorageScanner(max_depth=1)

        with patch.object(scanner, "scan_directory") as mock_scan:
            mock_scan.return_value = []
            scanner.scan_drive("E:\\")
            mock_scan.assert_called_once()
            call_args = mock_scan.call_args
            assert call_args[0][0] == "E:\\"

    def test_scan_drive_unix_root(self):
        """Test scan_drive with Unix root path (/)."""
        scanner = StorageScanner(max_depth=1)

        with patch.object(scanner, "scan_directory") as mock_scan:
            mock_scan.return_value = []
            scanner.scan_drive("/")
            mock_scan.assert_called_once()
            call_args = mock_scan.call_args
            assert call_args[0][0] == "/"

    def test_scan_drive_max_depth_override(self):
        """Test that max_depth parameter overrides instance max_depth."""
        scanner = StorageScanner(max_depth=5)

        with patch.object(scanner, "scan_directory") as mock_scan:
            mock_scan.return_value = []
            scanner.scan_drive("C", max_depth=2)
            # After call, original max_depth should be restored
            assert scanner.max_depth == 5

    def test_scan_drive_max_items_passed(self):
        """Test that max_items is passed to scan_directory."""
        scanner = StorageScanner(max_depth=1)

        with patch.object(scanner, "scan_directory") as mock_scan:
            mock_scan.return_value = []
            scanner.scan_drive("C", max_items=500)
            call_args = mock_scan.call_args
            assert call_args[1]["max_items"] == 500

    def test_scan_drive_admin_mode_ignored(self):
        """Test that admin_mode parameter is accepted but ignored."""
        scanner = StorageScanner(max_depth=1)

        with patch.object(scanner, "scan_directory") as mock_scan:
            mock_scan.return_value = []
            # Should not raise, even though admin_mode is ignored
            scanner.scan_drive("C", admin_mode=True)
            mock_scan.assert_called_once()

    def test_scan_drive_returns_scan_results(self, tmp_path):
        """Test that scan_drive returns results from scan_directory."""
        scanner = StorageScanner(max_depth=2)

        # Create test structure
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        test_file = subdir / "file.txt"
        test_file.write_text("hello world")

        # Use actual scan on tmp_path
        results = scanner.scan_drive(str(tmp_path))

        # Should have found at least the subdir and file
        assert len(results) >= 1
        paths = [r.path for r in results]
        assert any("subdir" in p for p in paths)

    def test_scan_drive_restores_max_depth_on_error(self):
        """Test that max_depth is restored even if scan_directory raises."""
        scanner = StorageScanner(max_depth=5)

        with patch.object(scanner, "scan_directory") as mock_scan:
            mock_scan.side_effect = Exception("Simulated error")

            with pytest.raises(Exception, match="Simulated error"):
                scanner.scan_drive("C", max_depth=2)

            # max_depth should be restored
            assert scanner.max_depth == 5

    def test_scan_drive_lowercase_drive_letter(self):
        """Test that lowercase drive letters are handled correctly."""
        scanner = StorageScanner(max_depth=1)

        with patch.object(scanner, "scan_directory") as mock_scan:
            mock_scan.return_value = []
            scanner.scan_drive("c")
            call_args = mock_scan.call_args
            # Should be uppercased
            assert call_args[0][0] == "C:\\"


class TestScanDriveIntegration:
    """Integration tests for scan_drive with create_scanner factory."""

    def test_create_scanner_returns_scanner_with_scan_drive(self):
        """Verify factory returns scanner with scan_drive method."""
        from autopack.storage_optimizer.scanner import create_scanner

        # Force Python scanner (no WizTree)
        scanner = create_scanner(prefer_wiztree=False)
        assert hasattr(scanner, "scan_drive")
        assert callable(scanner.scan_drive)

    def test_wiztree_fallback_calls_storage_scanner_scan_drive(self):
        """Test WizTreeScanner fallback to StorageScanner.scan_drive works."""
        try:
            from autopack.storage_optimizer.wiztree_scanner import \
                WizTreeScanner
        except ImportError:
            pytest.skip("WizTreeScanner not available")

        # Create WizTreeScanner with no WizTree available
        scanner = WizTreeScanner(wiztree_path=Path("/nonexistent/path"))

        with patch.object(scanner.fallback_scanner, "scan_drive") as mock_scan:
            mock_scan.return_value = []
            scanner.scan_drive("C")
            mock_scan.assert_called_once()
