"""Tests for ExecutorStateManager.

IMP-MAINT-006: Tests for state management utilities extracted from autonomous_executor.py.
"""

from unittest.mock import MagicMock, patch

from autopack.executor.state_manager import (ExecutorStateManager,
                                             force_mark_phase_failed,
                                             status_to_outcome,
                                             update_phase_status)


class TestExecutorStateManager:
    """Tests for ExecutorStateManager class."""

    def test_init(self):
        """Test initialization."""
        mock_client = MagicMock()
        manager = ExecutorStateManager(
            run_id="test-run-123",
            api_client=mock_client,
        )
        assert manager.run_id == "test-run-123"
        assert manager.api_client == mock_client
        assert manager._http_500_count == 0
        assert manager._patch_failure_count == 0
        assert manager._total_failures == 0

    def test_update_phase_status_success(self):
        """Test successful status update."""
        mock_client = MagicMock()
        manager = ExecutorStateManager(
            run_id="test-run-123",
            api_client=mock_client,
        )

        result = manager.update_phase_status("phase-1", "COMPLETE")

        assert result is True
        mock_client.update_phase_status.assert_called_once_with(
            "test-run-123", "phase-1", "COMPLETE", timeout=30
        )

    def test_update_phase_status_blocked_converts_to_failed(self):
        """Test that BLOCKED status is converted to FAILED."""
        mock_client = MagicMock()
        manager = ExecutorStateManager(
            run_id="test-run-123",
            api_client=mock_client,
        )

        result = manager.update_phase_status("phase-1", "BLOCKED")

        assert result is True
        mock_client.update_phase_status.assert_called_once_with(
            "test-run-123", "phase-1", "FAILED", timeout=30
        )

    def test_update_phase_status_calls_summary_callback(self):
        """Test that terminal statuses trigger summary callback."""
        mock_client = MagicMock()
        mock_callback = MagicMock()
        manager = ExecutorStateManager(
            run_id="test-run-123",
            api_client=mock_client,
            write_run_summary_callback=mock_callback,
        )

        # Terminal statuses should trigger callback
        for status in ["COMPLETE", "FAILED", "SKIPPED"]:
            mock_callback.reset_mock()
            manager.update_phase_status("phase-1", status)
            mock_callback.assert_called_once()

    def test_update_phase_status_non_terminal_no_callback(self):
        """Test that non-terminal statuses don't trigger summary callback."""
        mock_client = MagicMock()
        mock_callback = MagicMock()
        manager = ExecutorStateManager(
            run_id="test-run-123",
            api_client=mock_client,
            write_run_summary_callback=mock_callback,
        )

        # Non-terminal statuses should NOT trigger callback
        for status in ["QUEUED", "EXECUTING", "CI_RUNNING"]:
            mock_callback.reset_mock()
            manager.update_phase_status("phase-1", status)
            mock_callback.assert_not_called()

    def test_update_phase_status_failure(self):
        """Test status update failure handling."""
        mock_client = MagicMock()
        mock_client.update_phase_status.side_effect = Exception("API Error")
        manager = ExecutorStateManager(
            run_id="test-run-123",
            api_client=mock_client,
        )

        result = manager.update_phase_status("phase-1", "COMPLETE")

        assert result is False

    def test_status_to_outcome_known_statuses(self):
        """Test status to outcome mapping for known statuses."""
        mock_client = MagicMock()
        manager = ExecutorStateManager(
            run_id="test-run-123",
            api_client=mock_client,
        )

        assert manager.status_to_outcome("FAILED") == "auditor_reject"
        assert manager.status_to_outcome("PATCH_FAILED") == "patch_apply_error"
        assert manager.status_to_outcome("BLOCKED") == "auditor_reject"
        assert manager.status_to_outcome("CI_FAILED") == "ci_fail"
        assert (
            manager.status_to_outcome("DELIVERABLES_VALIDATION_FAILED")
            == "deliverables_validation_failed"
        )

    def test_status_to_outcome_unknown_status(self):
        """Test status to outcome mapping for unknown status."""
        mock_client = MagicMock()
        manager = ExecutorStateManager(
            run_id="test-run-123",
            api_client=mock_client,
        )

        # Unknown statuses should default to auditor_reject
        assert manager.status_to_outcome("UNKNOWN_STATUS") == "auditor_reject"

    def test_force_mark_phase_failed_success(self):
        """Test successful force mark failed."""
        mock_client = MagicMock()
        manager = ExecutorStateManager(
            run_id="test-run-123",
            api_client=mock_client,
        )

        result = manager.force_mark_phase_failed("phase-1")

        assert result is True
        mock_client.update_phase_status.assert_called_once()

    def test_force_mark_phase_failed_retries(self):
        """Test force mark failed with retries.

        Note: force_mark_phase_failed catches exceptions from update_phase_status
        and retries, so we need to set up the mock to return False (failure)
        then True (success).
        """
        mock_client = MagicMock()
        manager = ExecutorStateManager(
            run_id="test-run-123",
            api_client=mock_client,
        )

        # Use patch to control update_phase_status behavior
        with patch.object(manager, "update_phase_status") as mock_update:
            # First two calls fail (return False), third succeeds
            mock_update.side_effect = [False, False, True]

            result = manager.force_mark_phase_failed("phase-1", max_retries=3)

            assert result is True
            assert mock_update.call_count == 3

    def test_force_mark_phase_failed_all_retries_fail(self):
        """Test force mark failed when all retries fail."""
        mock_client = MagicMock()
        manager = ExecutorStateManager(
            run_id="test-run-123",
            api_client=mock_client,
        )

        # Use patch to control update_phase_status behavior
        with patch.object(manager, "update_phase_status") as mock_update:
            mock_update.return_value = False  # Always fail

            result = manager.force_mark_phase_failed("phase-1", max_retries=3)

            assert result is False
            assert mock_update.call_count == 3

    def test_get_health_budget(self):
        """Test getting health budget."""
        mock_client = MagicMock()
        manager = ExecutorStateManager(
            run_id="test-run-123",
            api_client=mock_client,
        )

        budget = manager.get_health_budget()

        assert budget == {
            "http_500": 0,
            "patch_failures": 0,
            "total_failures": 0,
        }

    def test_increment_counters(self):
        """Test incrementing health budget counters."""
        mock_client = MagicMock()
        manager = ExecutorStateManager(
            run_id="test-run-123",
            api_client=mock_client,
        )

        assert manager.increment_http_500_count() == 1
        assert manager.increment_http_500_count() == 2

        assert manager.increment_patch_failure_count() == 1
        assert manager.increment_patch_failure_count() == 2
        assert manager.increment_patch_failure_count() == 3

        assert manager.increment_total_failures() == 1

        budget = manager.get_health_budget()
        assert budget == {
            "http_500": 2,
            "patch_failures": 3,
            "total_failures": 1,
        }

    def test_set_counters(self):
        """Test setting health budget counters."""
        mock_client = MagicMock()
        manager = ExecutorStateManager(
            run_id="test-run-123",
            api_client=mock_client,
        )

        manager.set_counters(
            http_500_count=5,
            patch_failure_count=3,
            total_failures=10,
        )

        budget = manager.get_health_budget()
        assert budget == {
            "http_500": 5,
            "patch_failures": 3,
            "total_failures": 10,
        }

    def test_set_counters_partial(self):
        """Test setting only some counters."""
        mock_client = MagicMock()
        manager = ExecutorStateManager(
            run_id="test-run-123",
            api_client=mock_client,
        )

        # Set initial values
        manager.set_counters(http_500_count=5, patch_failure_count=3, total_failures=10)

        # Update only one
        manager.set_counters(http_500_count=8)

        budget = manager.get_health_budget()
        assert budget == {
            "http_500": 8,
            "patch_failures": 3,
            "total_failures": 10,
        }


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_update_phase_status_wrapper(self):
        """Test the convenience wrapper function."""
        mock_executor = MagicMock()
        mock_executor.run_id = "test-run-123"

        result = update_phase_status(mock_executor, "phase-1", "COMPLETE")

        assert result is True
        mock_executor.api_client.update_phase_status.assert_called_once()

    def test_update_phase_status_wrapper_blocked(self):
        """Test that BLOCKED is converted to FAILED in wrapper."""
        mock_executor = MagicMock()
        mock_executor.run_id = "test-run-123"

        update_phase_status(mock_executor, "phase-1", "BLOCKED")

        mock_executor.api_client.update_phase_status.assert_called_once_with(
            "test-run-123", "phase-1", "FAILED", timeout=30
        )

    def test_status_to_outcome_wrapper(self):
        """Test the convenience wrapper function."""
        assert status_to_outcome("FAILED") == "auditor_reject"
        assert status_to_outcome("CI_FAILED") == "ci_fail"
        assert status_to_outcome("UNKNOWN") == "auditor_reject"

    def test_force_mark_phase_failed_wrapper(self):
        """Test the convenience wrapper function."""
        mock_executor = MagicMock()
        mock_executor.run_id = "test-run-123"

        result = force_mark_phase_failed(mock_executor, "phase-1")

        assert result is True
        mock_executor.api_client.update_phase_status.assert_called()
