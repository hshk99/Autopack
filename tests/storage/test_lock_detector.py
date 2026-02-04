"""
Unit tests for LockDetector (BUILD-152).

Tests lock classification, transient/permanent detection, and remediation hints.
"""

from pathlib import Path

from autopack.storage_optimizer.lock_detector import LockDetector


class TestLockDetector:
    """Test suite for Windows file lock detection and classification."""

    def setup_method(self):
        """Initialize lock detector for each test."""
        self.detector = LockDetector()

    # ========================================================================
    # Lock Type Detection Tests
    # ========================================================================

    def test_detect_searchindexer_lock(self):
        """Test detection of Windows Search indexer locks."""
        path = Path("C:/test/file.log")

        # Test various SearchIndexer error patterns
        test_cases = [
            Exception(
                "The process cannot access the file because it is being used by SearchIndexer.exe"
            ),
            Exception("Windows Search indexing service is accessing this file"),
            Exception("Search Indexer has locked this file"),
        ]

        for exc in test_cases:
            lock_type = self.detector.detect_lock_type(path, exc)
            assert lock_type == "searchindexer", f"Failed to detect searchindexer for: {exc}"

    def test_detect_antivirus_lock(self):
        """Test detection of antivirus/Windows Defender locks."""
        path = Path("C:/test/file.exe")

        test_cases = [
            Exception("Windows Defender is scanning this file"),
            Exception("Antivirus software has quarantined this file"),
            Exception("Malware detection is in progress"),
            Exception("Security threat scan in progress"),
        ]

        for exc in test_cases:
            lock_type = self.detector.detect_lock_type(path, exc)
            assert lock_type == "antivirus", f"Failed to detect antivirus for: {exc}"

    def test_detect_handle_lock(self):
        """Test detection of open file handle locks."""
        path = Path("C:/test/document.txt")

        test_cases = [
            Exception(
                "The process cannot access the file because it is being used by another process"
            ),
            Exception("File is in use by another application"),
            Exception("Sharing violation - cannot access the file"),
        ]

        for exc in test_cases:
            lock_type = self.detector.detect_lock_type(path, exc)
            assert lock_type == "handle", f"Failed to detect handle lock for: {exc}"

    def test_detect_permission_lock(self):
        """Test detection of permission/access denied locks."""
        path = Path("C:/System/protected.sys")

        test_cases = [
            Exception("Access is denied"),
            Exception("Permission denied - insufficient privileges"),
            Exception("You do not have permission to access this file"),
            Exception("Unauthorized access attempt"),
        ]

        for exc in test_cases:
            lock_type = self.detector.detect_lock_type(path, exc)
            assert lock_type == "permission", f"Failed to detect permission lock for: {exc}"

    def test_detect_path_too_long_lock(self):
        """Test detection of path length exceeded errors."""
        path = Path("C:/very/deep/nested/path/that/exceeds/windows/max/path/limit")

        test_cases = [
            Exception("The path too long to process"),
            Exception("Path length exceeds maximum allowed"),
            Exception("File name too long for Windows"),
        ]

        for exc in test_cases:
            lock_type = self.detector.detect_lock_type(path, exc)
            assert lock_type == "path_too_long", f"Failed to detect path_too_long for: {exc}"

    def test_detect_unknown_lock(self):
        """Test unknown lock type classification."""
        path = Path("C:/test/file.dat")
        exc = Exception("Some unrecognized error message")

        lock_type = self.detector.detect_lock_type(path, exc)
        assert lock_type == "unknown"

    # ========================================================================
    # Transient vs Permanent Classification Tests
    # ========================================================================

    def test_transient_lock_classification(self):
        """Test that transient locks are correctly identified."""
        # Transient locks (should retry)
        transient_types = ["searchindexer", "antivirus", "handle"]
        for lock_type in transient_types:
            assert self.detector.is_transient_lock(lock_type), (
                f"{lock_type} should be classified as transient"
            )

    def test_permanent_lock_classification(self):
        """Test that permanent locks are correctly identified."""
        # Permanent locks (should not retry)
        permanent_types = ["permission", "path_too_long", "unknown"]
        for lock_type in permanent_types:
            assert not self.detector.is_transient_lock(lock_type), (
                f"{lock_type} should be classified as permanent"
            )

    # ========================================================================
    # Remediation Hints Tests
    # ========================================================================

    def test_remediation_hints_all_types(self):
        """Test that all lock types have remediation hints."""
        lock_types = [
            "searchindexer",
            "antivirus",
            "handle",
            "permission",
            "path_too_long",
            "unknown",
        ]

        for lock_type in lock_types:
            hint = self.detector.get_remediation_hint(lock_type)
            assert hint is not None, f"No hint for {lock_type}"
            assert len(hint) > 0, f"Empty hint for {lock_type}"
            assert "Options:" in hint or "option" in hint.lower(), (
                f"Hint for {lock_type} should include actionable options"
            )

    def test_searchindexer_hint_content(self):
        """Test SearchIndexer hint has expected guidance."""
        hint = self.detector.get_remediation_hint("searchindexer")
        assert "Windows Search" in hint or "indexing" in hint
        assert "resmon.exe" in hint or "Resource Monitor" in hint

    def test_permission_hint_content(self):
        """Test permission hint has expected guidance."""
        hint = self.detector.get_remediation_hint("permission")
        assert "Administrator" in hint or "permissions" in hint

    # ========================================================================
    # Retry Configuration Tests
    # ========================================================================

    def test_recommended_retry_counts(self):
        """Test recommended retry counts for different lock types."""
        # Transient locks should have retries
        assert self.detector.get_recommended_retry_count("searchindexer") == 3
        assert self.detector.get_recommended_retry_count("antivirus") == 2
        assert self.detector.get_recommended_retry_count("handle") == 3

        # Permanent locks should have no retries
        assert self.detector.get_recommended_retry_count("permission") == 0
        assert self.detector.get_recommended_retry_count("path_too_long") == 0
        assert self.detector.get_recommended_retry_count("unknown") == 0

    def test_backoff_seconds_progression(self):
        """Test exponential backoff progression for lock types."""
        # SearchIndexer: [2, 5, 10]
        assert self.detector.get_backoff_seconds("searchindexer", 0) == 2
        assert self.detector.get_backoff_seconds("searchindexer", 1) == 5
        assert self.detector.get_backoff_seconds("searchindexer", 2) == 10

        # Antivirus: [10, 30, 60]
        assert self.detector.get_backoff_seconds("antivirus", 0) == 10
        assert self.detector.get_backoff_seconds("antivirus", 1) == 30
        assert self.detector.get_backoff_seconds("antivirus", 2) == 60

        # Handle: [2, 5, 10]
        assert self.detector.get_backoff_seconds("handle", 0) == 2
        assert self.detector.get_backoff_seconds("handle", 1) == 5
        assert self.detector.get_backoff_seconds("handle", 2) == 10

    def test_backoff_seconds_out_of_range(self):
        """Test backoff returns last value when retry_attempt exceeds list length."""
        # Beyond defined backoff list, should return last value
        assert self.detector.get_backoff_seconds("searchindexer", 10) == 10
        assert self.detector.get_backoff_seconds("antivirus", 5) == 60
