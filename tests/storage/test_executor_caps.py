"""
Unit tests for CleanupExecutor caps and retry logic (BUILD-152).

Tests GB caps, file count caps, retry backoff, and skip_locked behavior.
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from autopack.storage_optimizer.executor import CleanupExecutor, ExecutionResult, ExecutionStatus
from autopack.storage_optimizer.policy import load_policy


class TestExecutorCaps:
    """Test suite for CleanupExecutor category caps and safety features."""

    def setup_method(self):
        """Load policy for each test."""
        policy_path = Path("c:/dev/Autopack/config/storage_policy.yaml")
        self.policy = load_policy(policy_path)

    # ========================================================================
    # Category GB Cap Tests
    # ========================================================================

    def test_category_gb_cap_enforcement(self):
        """Test that execution stops when GB cap is reached."""
        # Create executor with dry_run=False to test cap logic
        executor = CleanupExecutor(
            policy=self.policy,
            dry_run=True,  # Use dry run to avoid actual deletion
            skip_locked=False,
        )

        # Mock candidates that would exceed cap
        # dev_caches cap: 50 GB
        mock_candidates = []
        for i in range(60):
            candidate = Mock()
            candidate.id = i
            candidate.path = f"C:/dev/project{i}/node_modules"
            candidate.category = "dev_caches"
            candidate.size_bytes = 1 * 1024**3  # 1 GB each
            candidate.confidence = 0.9
            candidate.reasoning = "Test candidate"
            mock_candidates.append(candidate)

        # Mock database session (execute_approved_candidates uses query(...).filter(...).filter(...).all())
        mock_session = Mock()
        mock_query = mock_session.query.return_value
        mock_query.filter.return_value.filter.return_value.all.return_value = mock_candidates

        # Execute with cap enforcement
        with patch.object(executor, "execute_cleanup_candidate") as mock_execute:
            # Mock successful execution
            mock_execute.return_value = ExecutionResult(
                candidate_id=1,
                path="C:/test/file.txt",
                status=ExecutionStatus.COMPLETED,
                original_size_bytes=1 * 1024**3,
                freed_bytes=1 * 1024**3,
            )

            result = executor.execute_approved_candidates(
                mock_session, scan_id=1, category="dev_caches"
            )

            # Should stop at 50 GB cap (50 files processed out of 60)
            # Note: Exact count depends on cap enforcement logic
            assert result.total_candidates == 60
            assert result.successful < 60, "Should not process all candidates due to GB cap"
            assert result.successful > 0, "Should process some candidates before cap"
            assert result.stopped_due_to_cap is True

    def test_category_file_count_cap(self):
        """Test that execution stops when file count cap is reached."""
        executor = CleanupExecutor(policy=self.policy, dry_run=True, skip_locked=False)

        # Create candidates exceeding file count cap
        # dev_caches cap: 1000 files
        mock_candidates = []
        for i in range(1500):
            candidate = Mock()
            candidate.id = i
            candidate.path = f"C:/cache/file{i}.tmp"
            candidate.category = "dev_caches"
            candidate.size_bytes = 1024  # 1 KB each (small files)
            candidate.confidence = 0.9
            candidate.reasoning = "Test candidate"
            mock_candidates.append(candidate)

        mock_session = Mock()
        mock_query = mock_session.query.return_value
        mock_query.filter.return_value.filter.return_value.all.return_value = mock_candidates

        with patch.object(executor, "execute_cleanup_candidate") as mock_execute:
            mock_execute.return_value = ExecutionResult(
                candidate_id=1,
                path="C:/test/file.txt",
                status=ExecutionStatus.COMPLETED,
                original_size_bytes=1024,
                freed_bytes=1024,
            )

            result = executor.execute_approved_candidates(
                mock_session, scan_id=1, category="dev_caches"
            )

            # Should stop at 1000 file cap
            assert result.total_candidates == 1500
            assert result.successful <= 1000, "Should not exceed file count cap"
            assert result.stopped_due_to_cap is True

    # ========================================================================
    # Retry with Exponential Backoff Tests
    # ========================================================================

    @patch("time.sleep")  # Mock sleep to avoid waiting in tests
    def test_retry_with_exponential_backoff(self, mock_sleep):
        """Test retry logic with exponential backoff for transient locks."""
        executor = CleanupExecutor(policy=self.policy, dry_run=False, skip_locked=False)

        # Create temporary file to test retry
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test content")
            temp_path = Path(f.name)

        try:
            # Mock send2trash to fail with transient lock (searchindexer)
            with patch("send2trash.send2trash") as mock_delete:
                # Fail first 2 times, succeed on 3rd
                mock_delete.side_effect = [
                    Exception("SearchIndexer.exe is using this file"),  # Retry 1
                    Exception("SearchIndexer.exe is using this file"),  # Retry 2
                    None,  # Success
                ]

                # Execute deletion
                success, error, lock_type, retry_count = executor._delete_with_retry(
                    path=temp_path, deletion_func=mock_delete, max_retries=3
                )

                # Should succeed after retries
                assert success is True
                assert retry_count == 2  # 2 retries before success
                assert mock_delete.call_count == 3

                # Verify backoff progression: [2, 5, 10] seconds for searchindexer
                assert mock_sleep.call_count == 2
                mock_sleep.assert_any_call(2)  # First retry: 2s
                mock_sleep.assert_any_call(5)  # Second retry: 5s

        finally:
            if temp_path.exists():
                temp_path.unlink()

    @patch("time.sleep")
    def test_retry_stops_after_max_retries(self, mock_sleep):
        """Test that retry stops after max_retries for persistent transient lock."""
        executor = CleanupExecutor(policy=self.policy, dry_run=False, skip_locked=False)

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test content")
            temp_path = Path(f.name)

        try:
            with patch("send2trash.send2trash") as mock_delete:
                # Always fail with transient lock
                mock_delete.side_effect = Exception("SearchIndexer.exe is using this file")

                success, error, lock_type, retry_count = executor._delete_with_retry(
                    path=temp_path, deletion_func=mock_delete, max_retries=3
                )

                # Should fail after max retries
                assert success is False
                assert lock_type == "searchindexer"
                assert retry_count == 3  # Attempted 3 retries
                assert mock_delete.call_count == 4  # Initial + 3 retries

        finally:
            if temp_path.exists():
                temp_path.unlink()

    @patch("time.sleep")
    def test_no_retry_for_permanent_lock(self, mock_sleep):
        """Test that permanent locks (permission) are not retried."""
        executor = CleanupExecutor(policy=self.policy, dry_run=False, skip_locked=False)

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test content")
            temp_path = Path(f.name)

        try:
            with patch("send2trash.send2trash") as mock_delete:
                # Fail with permanent lock (permission)
                mock_delete.side_effect = Exception("Access is denied")

                success, error, lock_type, retry_count = executor._delete_with_retry(
                    path=temp_path, deletion_func=mock_delete, max_retries=3
                )

                # Should fail immediately without retry
                assert success is False
                assert lock_type == "permission"
                assert retry_count == 0  # No retries for permanent lock
                assert mock_delete.call_count == 1  # Only initial attempt
                assert mock_sleep.call_count == 0  # No sleep/backoff

        finally:
            if temp_path.exists():
                temp_path.unlink()

    # ========================================================================
    # Skip Locked Tests
    # ========================================================================

    @patch("time.sleep")
    def test_skip_locked_flag_disables_retry(self, mock_sleep):
        """Test that skip_locked=True disables retry for transient locks."""
        executor = CleanupExecutor(
            policy=self.policy, dry_run=False, skip_locked=True  # Enable skip_locked
        )

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test content")
            temp_path = Path(f.name)

        try:
            with patch("send2trash.send2trash") as mock_delete:
                # Fail with transient lock (would normally retry)
                mock_delete.side_effect = Exception("SearchIndexer.exe is using this file")

                success, error, lock_type, retry_count = executor._delete_with_retry(
                    path=temp_path,
                    deletion_func=mock_delete,
                    max_retries=None,  # None should be overridden to 0 by skip_locked
                )

                # Should skip immediately without retry
                assert success is False
                assert lock_type == "searchindexer"
                assert retry_count == 0  # No retries
                assert mock_delete.call_count == 1  # Only initial attempt
                assert mock_sleep.call_count == 0  # No backoff

        finally:
            if temp_path.exists():
                temp_path.unlink()

    # ========================================================================
    # Cap Reporting Tests
    # ========================================================================

    def test_cap_stopped_reporting_in_result(self):
        """Test that BatchExecutionResult indicates when stopped due to cap."""
        executor = CleanupExecutor(policy=self.policy, dry_run=True, skip_locked=False)

        # Create candidates exceeding GB cap
        mock_candidates = []
        for i in range(60):
            candidate = Mock()
            candidate.id = i
            candidate.path = f"C:/dev/project{i}/node_modules"
            candidate.category = "dev_caches"
            candidate.size_bytes = 1 * 1024**3  # 1 GB each
            candidate.confidence = 0.9
            candidate.reasoning = "Test candidate"
            mock_candidates.append(candidate)

        mock_session = Mock()
        mock_query = mock_session.query.return_value
        mock_query.filter.return_value.filter.return_value.all.return_value = mock_candidates

        with patch.object(executor, "execute_cleanup_candidate") as mock_execute:
            mock_execute.return_value = ExecutionResult(
                candidate_id=1,
                path="C:/test/file.txt",
                status=ExecutionStatus.COMPLETED,
                original_size_bytes=1 * 1024**3,
                freed_bytes=1 * 1024**3,
            )

            result = executor.execute_approved_candidates(
                mock_session, scan_id=1, category="dev_caches"
            )

            # Result should indicate cap was hit
            assert result.total_candidates == len(mock_candidates)
            assert result.successful < len(mock_candidates), "Should not process all candidates"
            assert result.stopped_due_to_cap is True

    # ========================================================================
    # Checkpoint Logging Integration Tests
    # ========================================================================

    def test_checkpoint_logging_on_execution(self):
        """Test that checkpoint logger is called during execution."""
        executor = CleanupExecutor(policy=self.policy, dry_run=False, skip_locked=False)

        # Mock checkpoint logger + db session
        executor.checkpoint_logger = Mock()
        mock_db = Mock()

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test content")
            temp_path = Path(f.name)

        try:
            candidate = Mock()
            candidate.id = 123
            candidate.path = str(temp_path)
            candidate.category = "dev_caches"
            candidate.size_bytes = 1024
            candidate.requires_approval = False
            candidate.approval_status = "approved"

            # Set run_id
            executor.current_run_id = "test-run-001"

            # Execute (no actual deletion)
            with patch("send2trash.send2trash"):
                executor.execute_cleanup_candidate(mock_db, candidate)

            # Verify checkpoint logger was called
            assert executor.checkpoint_logger.log_execution.called
            call_args = executor.checkpoint_logger.log_execution.call_args[1]
            assert call_args["run_id"] == "test-run-001"
            assert call_args["candidate_id"] == 123
            assert call_args["action"] == "delete"
            assert call_args["status"] in ["completed", "skipped"]  # Dry run may skip

        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_sha256_computed_before_deletion(self):
        """Test that SHA256 is computed before file deletion."""
        executor = CleanupExecutor(policy=self.policy, dry_run=False, skip_locked=False)

        # Mock checkpoint logger to capture SHA256
        executor.checkpoint_logger = Mock()
        mock_db = Mock()

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test content for sha256")
            temp_path = Path(f.name)

        try:
            candidate = Mock()
            candidate.id = 456
            candidate.path = str(temp_path)
            candidate.category = "dev_caches"
            candidate.size_bytes = len("test content for sha256")
            candidate.requires_approval = False
            candidate.approval_status = "approved"

            executor.current_run_id = "test-run-002"

            # Execute (will actually delete with send2trash)
            with patch("send2trash.send2trash"):  # Mock to avoid actual deletion
                executor.execute_cleanup_candidate(mock_db, candidate)

            # Verify SHA256 was logged
            assert executor.checkpoint_logger.log_execution.called
            call_args = executor.checkpoint_logger.log_execution.call_args[1]
            sha256 = call_args.get("sha256")
            assert sha256 is not None
            assert len(sha256) == 64  # SHA256 hex digest

        finally:
            if temp_path.exists():
                temp_path.unlink()
