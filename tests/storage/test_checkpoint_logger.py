"""
Unit tests for CheckpointLogger (BUILD-152).

Tests checkpoint logging, SHA256 computation, and dual-write fallback.
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from autopack.storage_optimizer.checkpoint_logger import CheckpointLogger, compute_sha256


class TestCheckpointLogger:
    """Test suite for execution checkpoint logging."""

    # ========================================================================
    # SHA256 Checksum Tests
    # ========================================================================

    def test_compute_sha256_for_file(self):
        """Test SHA256 computation for a regular file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("Hello, BUILD-152 checkpoint logging test!")
            temp_path = Path(f.name)

        try:
            sha256 = compute_sha256(temp_path)
            assert sha256 is not None
            assert len(sha256) == 64  # SHA256 hex digest is 64 chars
            assert sha256.isalnum()  # Only hex characters

            # Verify deterministic (same file = same hash)
            sha256_2 = compute_sha256(temp_path)
            assert sha256 == sha256_2
        finally:
            temp_path.unlink()

    def test_compute_sha256_for_directory(self):
        """Test SHA256 computation for a directory (should aggregate contents)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create some files
            (temp_path / "file1.txt").write_text("Content 1")
            (temp_path / "file2.txt").write_text("Content 2")
            (temp_path / "subdir").mkdir()
            (temp_path / "subdir" / "file3.txt").write_text("Content 3")

            sha256 = compute_sha256(temp_path)
            assert sha256 is not None
            assert len(sha256) == 64

            # Verify deterministic
            sha256_2 = compute_sha256(temp_path)
            assert sha256 == sha256_2

    def test_compute_sha256_nonexistent_path(self):
        """Test SHA256 computation for nonexistent path returns None."""
        nonexistent = Path("C:/nonexistent/path/file.txt")
        sha256 = compute_sha256(nonexistent)
        assert sha256 is None

    # ========================================================================
    # JSONL Fallback Logging Tests
    # ========================================================================

    def test_log_execution_jsonl_fallback(self):
        """Test JSONL fallback logging when PostgreSQL unavailable."""
        with tempfile.TemporaryDirectory() as temp_dir:
            jsonl_path = Path(temp_dir) / "test_checkpoints.log"

            # Create logger with no database (forces JSONL fallback)
            logger = CheckpointLogger(dsn=None)
            logger.fallback = jsonl_path

            # Log execution
            logger.log_execution(
                run_id="test-run-001",
                candidate_id=123,
                action="delete",
                path="C:/test/file.txt",
                size_bytes=1024,
                sha256="abc123def456",
                status="completed",
                error=None,
                lock_type=None,
                retry_count=0,
            )

            # Verify JSONL written
            assert jsonl_path.exists()
            lines = jsonl_path.read_text().strip().split("\n")
            assert len(lines) == 1

            # Parse and validate
            record = json.loads(lines[0])
            assert record["run_id"] == "test-run-001"
            assert record["candidate_id"] == 123
            assert record["action"] == "delete"
            assert record["path"] == "C:/test/file.txt"
            assert record["size_bytes"] == 1024
            assert record["sha256"] == "abc123def456"
            assert record["status"] == "completed"
            assert record["retry_count"] == 0
            assert "timestamp" in record

    def test_log_execution_with_lock_info(self):
        """Test logging execution with lock type and retry count."""
        with tempfile.TemporaryDirectory() as temp_dir:
            jsonl_path = Path(temp_dir) / "test_checkpoints.log"

            logger = CheckpointLogger(dsn=None)
            logger.fallback = jsonl_path

            # Log failed execution with lock info
            logger.log_execution(
                run_id="test-run-002",
                candidate_id=456,
                action="delete",
                path="C:/test/locked.txt",
                size_bytes=2048,
                sha256="xyz789",
                status="failed",
                error="PermissionError: Access is denied",
                lock_type="permission",
                retry_count=0,
            )

            # Verify lock info captured
            lines = jsonl_path.read_text().strip().split("\n")
            record = json.loads(lines[0])
            assert record["status"] == "failed"
            assert record["error"] == "PermissionError: Access is denied"
            assert record["lock_type"] == "permission"
            assert record["retry_count"] == 0

    def test_log_multiple_executions_append(self):
        """Test that multiple log_execution calls append to JSONL."""
        with tempfile.TemporaryDirectory() as temp_dir:
            jsonl_path = Path(temp_dir) / "test_checkpoints.log"

            logger = CheckpointLogger(dsn=None)
            logger.fallback = jsonl_path

            # Log 3 executions
            for i in range(3):
                logger.log_execution(
                    run_id=f"test-run-{i}",
                    candidate_id=100 + i,
                    action="delete",
                    path=f"C:/test/file{i}.txt",
                    size_bytes=1024 * i,
                    sha256=f"hash{i}",
                    status="completed",
                )

            # Verify all 3 logged
            lines = jsonl_path.read_text().strip().split("\n")
            assert len(lines) == 3

            for i, line in enumerate(lines):
                record = json.loads(line)
                assert record["run_id"] == f"test-run-{i}"
                assert record["candidate_id"] == 100 + i

    # ========================================================================
    # PostgreSQL Logging Tests (requires DATABASE_URL)
    # ========================================================================

    @pytest.mark.skipif(
        not Path("autopack.db").exists() and not Path("C:/dev/Autopack/autopack.db").exists(),
        reason="Database not available for integration test",
    )
    def test_log_execution_to_database(self):
        """Integration test: Log to PostgreSQL execution_checkpoints table."""
        import os

        from autopack.database import SessionLocal

        # Skip if no database configured
        dsn = os.getenv("DATABASE_URL")
        if not dsn:
            pytest.skip("DATABASE_URL not set")

        # This test is specifically for PostgreSQL-backed logging.
        if "postgres" not in dsn.lower():
            pytest.skip("DATABASE_URL is not PostgreSQL (skipping Postgres integration test)")

        logger = CheckpointLogger()

        # Log execution
        run_id = f"test-run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        logger.log_execution(
            run_id=run_id,
            candidate_id=999,
            action="delete",
            path="C:/test/db_test.txt",
            size_bytes=4096,
            sha256="db_test_hash",
            status="completed",
        )

        # Verify written to database
        session = SessionLocal()
        try:
            from autopack.models import ExecutionCheckpoint

            checkpoints = session.query(ExecutionCheckpoint).filter_by(run_id=run_id).all()
            assert len(checkpoints) >= 1

            checkpoint = checkpoints[0]
            assert checkpoint.run_id == run_id
            assert checkpoint.candidate_id == 999
            assert checkpoint.action == "delete"
            assert checkpoint.status == "completed"
            assert checkpoint.sha256 == "db_test_hash"
        finally:
            session.close()

    # ========================================================================
    # Idempotency Support Tests
    # ========================================================================

    def test_get_deleted_checksums_from_jsonl(self):
        """Test retrieval of deleted file checksums for idempotency."""
        with tempfile.TemporaryDirectory() as temp_dir:
            jsonl_path = Path(temp_dir) / "test_checkpoints.log"

            logger = CheckpointLogger(dsn=None)
            logger.fallback = jsonl_path

            # Log some completed deletions
            logger.log_execution("run1", 1, "delete", "C:/file1.txt", 1024, "hash1", "completed")
            logger.log_execution("run1", 2, "delete", "C:/file2.txt", 2048, "hash2", "completed")
            logger.log_execution(
                "run1", 3, "delete", "C:/file3.txt", 3072, "hash3", "failed"
            )  # Failed
            logger.log_execution(
                "run1", 4, "compress", "C:/file4.txt", 4096, "hash4", "completed"
            )  # Compress

            # Get deleted checksums (should only include completed deletions)
            deleted = logger.get_deleted_checksums(lookback_days=7)

            # Only hash1 and hash2 should be in deleted set (completed delete actions)
            assert "hash1" in deleted
            assert "hash2" in deleted
            assert "hash3" not in deleted  # Failed
            assert "hash4" not in deleted  # Compress, not delete

    def test_get_deleted_checksums_lookback_period(self):
        """Test that lookback_days filters old checkpoints."""
        from datetime import timedelta, timezone

        with tempfile.TemporaryDirectory() as temp_dir:
            jsonl_path = Path(temp_dir) / "test_checkpoints.log"

            logger = CheckpointLogger(dsn=None)
            logger.fallback = jsonl_path

            # Create checkpoint from 100 days ago (ISO format timestamp)
            old_timestamp = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
            old_record = {
                "run_id": "old-run",
                "candidate_id": 1,
                "action": "delete",
                "path": "C:/old.txt",
                "size_bytes": 1024,
                "sha256": "old_hash",
                "status": "completed",
                "error": None,
                "lock_type": None,
                "retry_count": 0,
                "timestamp": old_timestamp,
            }

            with jsonl_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(old_record) + "\n")

            # Recent checkpoint
            logger.log_execution(
                "new-run", 2, "delete", "C:/new.txt", 2048, "new_hash", "completed"
            )

            # Lookback 7 days: should only get new_hash
            deleted = logger.get_deleted_checksums(lookback_days=7)
            assert "new_hash" in deleted
            assert "old_hash" not in deleted

            # Lookback 200 days: should get both
            deleted_all = logger.get_deleted_checksums(lookback_days=200)
            assert "new_hash" in deleted_all
            assert "old_hash" in deleted_all
