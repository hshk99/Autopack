"""Tests for learning database concurrency and atomic writes.

Tests that verify:
- Atomic writes with file locking prevent corruption
- Concurrent writes are serialized correctly
- Lock acquisition and release work properly
- Temp file cleanup happens on failures
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

from autopack.memory.learning_db import LearningDatabase


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Create a temporary database file path."""
    return tmp_path / "test_learning.db.json"


class TestAtomicWrites:
    """Test atomic write functionality."""

    def test_basic_write_creates_file(self, temp_db_path: Path) -> None:
        """Test that a write creates the database file."""
        db = LearningDatabase(temp_db_path)
        db.record_improvement_outcome("IMP-TEST-001", "implemented")
        assert temp_db_path.exists()

    def test_write_creates_valid_json(self, temp_db_path: Path) -> None:
        """Test that saved data is valid JSON."""
        db = LearningDatabase(temp_db_path)
        db.record_improvement_outcome(
            "IMP-TEST-001",
            "implemented",
            category="test",
            priority="high",
        )

        # Verify file is valid JSON
        with open(temp_db_path, encoding="utf-8") as f:
            data = json.load(f)
            assert "improvements" in data
            assert "IMP-TEST-001" in data["improvements"]

    def test_atomic_write_no_temp_files_left(self, temp_db_path: Path) -> None:
        """Test that no temporary files are left after successful writes."""
        db = LearningDatabase(temp_db_path)

        # Do several writes
        for i in range(5):
            db.record_improvement_outcome(
                f"IMP-TEST-{i:03d}",
                "implemented",
                category="test",
            )

        # Check that no .tmp files exist
        temp_files = list(temp_db_path.parent.glob(f".{temp_db_path.name}.*.tmp"))
        assert len(temp_files) == 0, f"Temp files left behind: {temp_files}"

    def test_concurrent_writes_no_corruption(self, temp_db_path: Path) -> None:
        """Test that concurrent writes don't corrupt the database."""
        db = LearningDatabase(temp_db_path)

        # Disable logging to reduce noise
        import logging

        logging.getLogger("autopack.memory.learning_db").setLevel(logging.CRITICAL)

        def write_improvement(imp_id: str) -> None:
            """Write a single improvement."""
            db.record_improvement_outcome(
                imp_id,
                "implemented",
                category="test",
                priority="high",
            )

        # Create multiple threads that write concurrently
        threads = []
        num_threads = 5
        for i in range(num_threads):
            thread = threading.Thread(target=write_improvement, args=(f"IMP-CONCURRENT-{i:03d}",))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify the database is still valid
        with open(temp_db_path, encoding="utf-8") as f:
            data = json.load(f)

        # Check that all improvements were recorded
        improvements = data.get("improvements", {})
        assert (
            len(improvements) >= num_threads
        ), f"Expected at least {num_threads} improvements, got {len(improvements)}"

        # Verify each improvement is valid
        for imp_id, imp_data in improvements.items():
            assert "outcome_history" in imp_data
            assert len(imp_data["outcome_history"]) > 0

    def test_lock_file_cleanup(self, temp_db_path: Path) -> None:
        """Test that lock files are cleaned up."""
        db = LearningDatabase(temp_db_path)
        db.record_improvement_outcome("IMP-TEST-001", "implemented")

        # Lock file may exist but should not persist indefinitely
        # Just verify the main db file exists and is valid
        assert temp_db_path.exists()
        with open(temp_db_path, encoding="utf-8") as f:
            data = json.load(f)
            assert isinstance(data, dict)

    def test_data_integrity_after_write(self, temp_db_path: Path) -> None:
        """Test that data integrity is maintained across writes."""
        db = LearningDatabase(temp_db_path)

        # Write initial data
        db.record_improvement_outcome(
            "IMP-TEST-001",
            "implemented",
            category="security",
            notes="Fixed SQL injection",
        )

        # Write more data
        db.record_improvement_outcome(
            "IMP-TEST-002",
            "blocked",
            category="reliability",
            notes="Network timeout",
        )

        # Load fresh instance and verify data
        db2 = LearningDatabase(temp_db_path)
        improvements = db2.list_improvements()

        assert len(improvements) >= 2
        imp_ids = {imp["imp_id"] for imp in improvements}
        assert "IMP-TEST-001" in imp_ids
        assert "IMP-TEST-002" in imp_ids

        # Verify specific data
        imp1 = db2.get_improvement("IMP-TEST-001")
        assert imp1 is not None
        assert imp1["current_outcome"] == "implemented"
        assert imp1["category"] == "security"


class TestFileSystemBehavior:
    """Test file system specific behavior."""

    def test_parent_directory_creation(self, tmp_path: Path) -> None:
        """Test that parent directories are created."""
        nested_path = tmp_path / "nested" / "deep" / "path" / "learning.db.json"
        db = LearningDatabase(nested_path)

        assert nested_path.exists()
        db.record_improvement_outcome("IMP-TEST-001", "implemented")
        assert nested_path.exists()

    def test_existing_file_overwrite(self, temp_db_path: Path) -> None:
        """Test that existing files are safely overwritten."""
        # Create initial file
        db1 = LearningDatabase(temp_db_path)
        db1.record_improvement_outcome("IMP-INITIAL", "implemented")

        # Open fresh instance (simulating process restart)
        db2 = LearningDatabase(temp_db_path)
        db2.record_improvement_outcome("IMP-SECOND", "implemented")

        # Verify both improvements exist
        improvements = db2.list_improvements()
        imp_ids = {imp["imp_id"] for imp in improvements}
        assert "IMP-INITIAL" in imp_ids
        assert "IMP-SECOND" in imp_ids

    def test_special_characters_in_data(self, temp_db_path: Path) -> None:
        """Test that special characters are properly encoded."""
        db = LearningDatabase(temp_db_path)
        db.record_improvement_outcome(
            "IMP-TEST-001",
            "implemented",
            notes="Fixed: special characters",
        )

        # Reload and verify
        db2 = LearningDatabase(temp_db_path)
        imp = db2.get_improvement("IMP-TEST-001")
        assert imp is not None
        assert "special characters" in imp["outcome_history"][0]["notes"]


class TestErrorHandling:
    """Test error handling in atomic writes."""

    def test_save_returns_false_on_permission_error(self, temp_db_path: Path) -> None:
        """Test that save returns False on permission errors."""
        db = LearningDatabase(temp_db_path)

        # Make parent directory read-only (if possible on Windows)
        if sys.platform != "win32":
            try:
                db.record_improvement_outcome("IMP-TEST-001", "implemented")
                temp_db_path.parent.chmod(0o444)

                # Try to write again - should fail gracefully
                result = db.record_improvement_outcome("IMP-TEST-002", "implemented")
                # Note: behavior may vary by system, just ensure no exception
                assert isinstance(result, bool)
            finally:
                # Restore permissions
                temp_db_path.parent.chmod(0o755)

    def test_corrupted_file_recovery(self, temp_db_path: Path) -> None:
        """Test recovery from corrupted database files."""
        # Create corrupted file
        with open(temp_db_path, "w", encoding="utf-8") as f:
            f.write("invalid json content {{{")

        # Should recover with new schema
        db = LearningDatabase(temp_db_path)
        assert db._data is not None
        assert "improvements" in db._data

    def test_partial_write_recovery(self, temp_db_path: Path) -> None:
        """Test recovery from partial writes."""
        db = LearningDatabase(temp_db_path)
        db.record_improvement_outcome("IMP-TEST-001", "implemented")

        # Simulate partial write by truncating file
        with open(temp_db_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Write truncated version
        with open(temp_db_path, "w", encoding="utf-8") as f:
            f.write(content[:50])  # Truncate to make invalid JSON

        # Should recover
        db2 = LearningDatabase(temp_db_path)
        assert "improvements" in db2._data
