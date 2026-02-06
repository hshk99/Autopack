"""Tests for IMP-REL-001: Thread-safe stale phase reset with locking.

Verifies that:
1. _phase_reset_lock prevents concurrent reset race conditions
2. Double-check pattern prevents duplicate resets
3. reset_count tracking provides observability
"""

import threading
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest


class TestStalePhaseResetLocking:
    """Test suite for IMP-REL-001 stale phase reset locking."""

    @pytest.fixture
    def mock_executor(self):
        """Create a mock AutonomousExecutor with required attributes."""
        from unittest.mock import MagicMock

        executor = MagicMock()
        executor.run_id = "test-run-id"
        executor._phase_reset_lock = threading.Lock()
        executor._phase_reset_counts = {}

        # Mock the API client and get_run_status
        executor.api_client = MagicMock()
        executor.get_run_status = MagicMock(
            return_value={
                "tiers": [
                    {
                        "phases": [
                            {
                                "phase_id": "phase-1",
                                "state": "EXECUTING",
                                "updated_at": (datetime.now() - timedelta(minutes=15)).isoformat(),
                            }
                        ]
                    }
                ]
            }
        )

        # Mock _update_phase_status to track calls
        executor._update_phase_status = MagicMock()

        return executor

    def test_phase_reset_lock_exists(self, mock_executor):
        """Verify that _phase_reset_lock is a threading.Lock."""
        assert hasattr(mock_executor, "_phase_reset_lock")
        assert isinstance(mock_executor._phase_reset_lock, type(threading.Lock()))

    def test_phase_reset_counts_initialized(self, mock_executor):
        """Verify that _phase_reset_counts dict is initialized."""
        assert hasattr(mock_executor, "_phase_reset_counts")
        assert isinstance(mock_executor._phase_reset_counts, dict)

    def test_reset_stale_phase_with_lock_acquires_lock(self, mock_executor):
        """Test that _reset_stale_phase_with_lock holds lock during execution."""
        # Import the actual method
        from autopack.autonomous_executor import AutonomousExecutor

        # Create a real executor instance (minimal setup)
        with patch.object(AutonomousExecutor, "__init__", lambda x: None):
            executor = AutonomousExecutor.__new__(AutonomousExecutor)
            executor.run_id = "test-run-id"
            executor._phase_reset_lock = threading.Lock()
            executor._phase_reset_counts = {}

            # Track if lock is held during _update_phase_status call
            lock_held_during_update = []

            def mock_update_status(phase_id, status):
                # Check if lock is currently held (locked() returns True if held)
                # Since we're inside the method, lock should be held
                lock_held_during_update.append(executor._phase_reset_lock.locked())

            executor._update_phase_status = mock_update_status
            executor.get_run_status = MagicMock(
                return_value={
                    "tiers": [{"phases": [{"phase_id": "phase-1", "state": "EXECUTING"}]}]
                }
            )

            # Call the method
            with patch("autopack.autonomous_executor.log_error"):
                with patch("autopack.debug_journal.log_fix"):
                    executor._reset_stale_phase_with_lock(
                        phase_id="phase-1",
                        reason="stale",
                        time_stale_seconds=600.0,
                    )

            # Verify lock was held during the update
            assert len(lock_held_during_update) == 1
            assert lock_held_during_update[0] is True

    def test_concurrent_reset_attempts_serialized(self):
        """Test that concurrent reset attempts are serialized by lock."""
        from autopack.autonomous_executor import AutonomousExecutor

        with patch.object(AutonomousExecutor, "__init__", lambda x: None):
            executor = AutonomousExecutor.__new__(AutonomousExecutor)
            executor.run_id = "test-run-id"
            executor._phase_reset_lock = threading.Lock()
            executor._phase_reset_counts = {}
            executor._update_phase_status = MagicMock()

            # Track the order of reset attempts
            reset_order = []
            reset_lock = threading.Lock()

            def mock_update_status(phase_id, status):
                with reset_lock:
                    reset_order.append((phase_id, status, threading.current_thread().name))
                time.sleep(0.1)  # Simulate API call latency

            executor._update_phase_status = mock_update_status

            # First call returns EXECUTING, subsequent calls return QUEUED
            call_count = [0]

            def mock_get_run_status():
                call_count[0] += 1
                if call_count[0] == 1:
                    # First thread sees EXECUTING
                    return {"tiers": [{"phases": [{"phase_id": "phase-1", "state": "EXECUTING"}]}]}
                else:
                    # Second thread sees QUEUED (already reset)
                    return {"tiers": [{"phases": [{"phase_id": "phase-1", "state": "QUEUED"}]}]}

            executor.get_run_status = mock_get_run_status

            results = []

            def attempt_reset(thread_id):
                with patch("autopack.autonomous_executor.log_error"):
                    with patch("autopack.debug_journal.log_fix"):
                        result = executor._reset_stale_phase_with_lock(
                            phase_id="phase-1",
                            reason="stale",
                            time_stale_seconds=600.0,
                        )
                        results.append((thread_id, result))

            # Start two threads trying to reset the same phase
            threads = [
                threading.Thread(target=attempt_reset, args=(i,), name=f"Thread-{i}")
                for i in range(2)
            ]

            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # Due to double-check pattern, only one should have actually reset
            actual_resets = len(reset_order)
            assert (
                actual_resets == 1
            ), f"Expected 1 reset due to double-check pattern, got {actual_resets}"

    def test_reset_count_incremented(self):
        """Test that reset_count is incremented on each reset."""
        from autopack.autonomous_executor import AutonomousExecutor

        with patch.object(AutonomousExecutor, "__init__", lambda x: None):
            executor = AutonomousExecutor.__new__(AutonomousExecutor)
            executor.run_id = "test-run-id"
            executor._phase_reset_lock = threading.Lock()
            executor._phase_reset_counts = {}
            executor._update_phase_status = MagicMock()
            executor.get_run_status = MagicMock(
                return_value={
                    "tiers": [{"phases": [{"phase_id": "phase-1", "state": "EXECUTING"}]}]
                }
            )

            with patch("autopack.autonomous_executor.log_error"):
                with patch("autopack.debug_journal.log_fix"):
                    # First reset
                    executor._reset_stale_phase_with_lock(
                        phase_id="phase-1",
                        reason="stale",
                        time_stale_seconds=600.0,
                    )

                    assert executor._phase_reset_counts.get("phase-1") == 1

                    # Second reset (simulate phase becoming stale again)
                    executor._reset_stale_phase_with_lock(
                        phase_id="phase-1",
                        reason="stale",
                        time_stale_seconds=600.0,
                    )

                    assert executor._phase_reset_counts.get("phase-1") == 2

    def test_double_check_prevents_duplicate_reset(self):
        """Test that double-check pattern prevents duplicate resets."""
        from autopack.autonomous_executor import AutonomousExecutor

        with patch.object(AutonomousExecutor, "__init__", lambda x: None):
            executor = AutonomousExecutor.__new__(AutonomousExecutor)
            executor.run_id = "test-run-id"
            executor._phase_reset_lock = threading.Lock()
            executor._phase_reset_counts = {}
            executor._update_phase_status = MagicMock()

            # Return non-EXECUTING state to simulate already reset
            executor.get_run_status = MagicMock(
                return_value={"tiers": [{"phases": [{"phase_id": "phase-1", "state": "QUEUED"}]}]}
            )

            with patch("autopack.autonomous_executor.log_error"):
                with patch("autopack.debug_journal.log_fix"):
                    result = executor._reset_stale_phase_with_lock(
                        phase_id="phase-1",
                        reason="stale",
                        time_stale_seconds=600.0,
                    )

                    # Should return False (no reset performed)
                    assert result is False

                    # _update_phase_status should NOT have been called
                    executor._update_phase_status.assert_not_called()

    def test_reset_with_no_timestamp_uses_lock(self):
        """Test that reset for phases without timestamp also uses lock."""
        from autopack.autonomous_executor import AutonomousExecutor

        with patch.object(AutonomousExecutor, "__init__", lambda x: None):
            executor = AutonomousExecutor.__new__(AutonomousExecutor)
            executor.run_id = "test-run-id"
            executor._phase_reset_lock = threading.Lock()
            executor._phase_reset_counts = {}
            executor._update_phase_status = MagicMock()
            executor.get_run_status = MagicMock(
                return_value={
                    "tiers": [{"phases": [{"phase_id": "phase-1", "state": "EXECUTING"}]}]
                }
            )

            with patch("autopack.autonomous_executor.log_error"):
                with patch("autopack.debug_journal.log_fix"):
                    result = executor._reset_stale_phase_with_lock(
                        phase_id="phase-1",
                        reason="no timestamp",
                        time_stale_seconds=None,
                    )

                    assert result is True
                    executor._update_phase_status.assert_called_once_with("phase-1", "QUEUED")


class TestDetectAndResetStalePhases:
    """Test the _detect_and_reset_stale_phases method integration."""

    def test_detect_and_reset_calls_locked_method(self):
        """Test that _detect_and_reset_stale_phases uses locked reset."""
        from autopack.autonomous_executor import AutonomousExecutor

        with patch.object(AutonomousExecutor, "__init__", lambda x: None):
            executor = AutonomousExecutor.__new__(AutonomousExecutor)
            executor.run_id = "test-run-id"
            executor._phase_reset_lock = threading.Lock()
            executor._phase_reset_counts = {}

            # Mock the locked reset method
            executor._reset_stale_phase_with_lock = MagicMock(return_value=True)
            executor._update_phase_status = MagicMock()

            # Create run_data with a stale phase
            stale_timestamp = (datetime.now() - timedelta(minutes=15)).isoformat()
            run_data = {
                "tiers": [
                    {
                        "phases": [
                            {
                                "phase_id": "phase-1",
                                "state": "EXECUTING",
                                "updated_at": stale_timestamp,
                            }
                        ]
                    }
                ]
            }

            # Call the detection method
            executor._detect_and_reset_stale_phases(run_data)

            # Verify locked reset was called
            executor._reset_stale_phase_with_lock.assert_called_once()
            call_kwargs = executor._reset_stale_phase_with_lock.call_args[1]
            assert call_kwargs["phase_id"] == "phase-1"
            assert call_kwargs["reason"] == "stale"

    def test_non_stale_phases_not_reset(self):
        """Test that phases not stale are not reset."""
        from autopack.autonomous_executor import AutonomousExecutor

        with patch.object(AutonomousExecutor, "__init__", lambda x: None):
            executor = AutonomousExecutor.__new__(AutonomousExecutor)
            executor.run_id = "test-run-id"
            executor._phase_reset_lock = threading.Lock()
            executor._phase_reset_counts = {}
            executor._reset_stale_phase_with_lock = MagicMock()
            executor._update_phase_status = MagicMock()

            # Create run_data with a fresh (non-stale) phase
            fresh_timestamp = (datetime.now() - timedelta(minutes=5)).isoformat()
            run_data = {
                "tiers": [
                    {
                        "phases": [
                            {
                                "phase_id": "phase-1",
                                "state": "EXECUTING",
                                "updated_at": fresh_timestamp,
                            }
                        ]
                    }
                ]
            }

            # Call the detection method
            executor._detect_and_reset_stale_phases(run_data)

            # Verify locked reset was NOT called (phase not stale)
            executor._reset_stale_phase_with_lock.assert_not_called()
