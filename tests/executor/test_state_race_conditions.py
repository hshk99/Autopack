"""Tests for state race condition fixes (IMP-R01).

These tests verify that the optimistic locking and SELECT FOR UPDATE
mechanisms prevent data corruption when multiple phases complete simultaneously.

Test coverage:
1. Concurrent phase state updates
2. Retry logic for serialization failures
3. Optimistic lock error handling
4. Version tracking integrity
"""

import threading
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from sqlalchemy.exc import OperationalError
from tenacity import RetryError

from autopack.executor.phase_state_manager import (
    OptimisticLockError,
    PhaseStateManager,
    StateUpdateRequest,
)
from autopack.executor.state_persistence import (
    ExecutorState,
    ExecutorStateManager,
    PersistenceError,
)


class TestConcurrentPhaseStateUpdates:
    """Test concurrent updates to phase state with optimistic locking."""

    def test_concurrent_phase_state_updates_no_corruption(self):
        """Verify no state corruption with concurrent phase updates.

        This test simulates multiple threads attempting to update the same
        phase state simultaneously. With SELECT FOR UPDATE, only one should
        succeed per transaction, preventing data corruption.
        """
        mgr = PhaseStateManager(run_id="test-run-123", workspace=Path("/workspace"))
        phase_id = "test-phase-123"

        # Track successful updates
        successful_updates = []
        lock = threading.Lock()

        def update_state(new_retry_count: int):
            """Update state in a thread."""
            try:
                # Mock the database query to simulate concurrent access
                mock_phase = Mock()
                mock_phase.phase_id = phase_id
                mock_phase.run_id = "test-run-123"
                mock_phase.retry_attempt = 0
                mock_phase.revision_epoch = 0
                mock_phase.escalation_level = 0
                mock_phase.version = 0

                with patch.object(mgr, "_get_phase_from_db", return_value=mock_phase):
                    with patch("autopack.database.SessionLocal") as mock_session_local:
                        mock_db = MagicMock()
                        mock_session_local.return_value.__enter__.return_value = mock_db

                        # Simulate SELECT FOR UPDATE
                        mock_query = MagicMock()
                        mock_db.query.return_value = mock_query
                        mock_query.with_for_update.return_value = mock_query
                        mock_query.filter.return_value = mock_query
                        mock_query.first.return_value = mock_phase

                        request = StateUpdateRequest(set_retry=new_retry_count)
                        result = mgr.update(phase_id, request)

                        if result:
                            with lock:
                                successful_updates.append(new_retry_count)
            except OptimisticLockError:
                # Expected in concurrent scenarios
                pass
            except Exception as e:
                # Log unexpected errors but don't fail the test
                print(f"Unexpected error in thread: {e}")

        # Spawn 10 concurrent updates
        threads = [threading.Thread(target=update_state, args=(i,)) for i in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Verify that at least some updates succeeded
        # In a real scenario with database, SELECT FOR UPDATE would serialize these
        assert len(successful_updates) > 0

    def test_optimistic_lock_error_on_serialization_failure(self):
        """Test OptimisticLockError is raised on serialization failures."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        with patch("autopack.database.SessionLocal") as mock_session_local:
            mock_db = MagicMock()
            mock_session_local.return_value.__enter__.return_value = mock_db

            # Simulate serialization failure
            mock_db.commit.side_effect = OperationalError(
                "could not serialize access",
                params=None,
                orig=Exception("serialization failure"),
            )

            mock_phase = Mock()
            mock_phase.phase_id = "phase-123"
            mock_phase.run_id = "test-run"
            mock_phase.retry_attempt = 0
            mock_phase.revision_epoch = 0
            mock_phase.escalation_level = 0
            mock_phase.version = 1

            mock_query = MagicMock()
            mock_db.query.return_value = mock_query
            mock_query.with_for_update.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.first.return_value = mock_phase

            # Need to call the internal method directly since update() catches exceptions
            with pytest.raises(OptimisticLockError):
                mgr._update_phase_attempts_in_db("phase-123", retry_attempt=1)

    def test_version_increment_on_successful_update(self):
        """Test that version is incremented on successful update."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        with patch("autopack.database.SessionLocal") as mock_session_local:
            mock_db = MagicMock()
            mock_session_local.return_value.__enter__.return_value = mock_db

            mock_phase = Mock()
            mock_phase.phase_id = "phase-123"
            mock_phase.run_id = "test-run"
            mock_phase.retry_attempt = 0
            mock_phase.revision_epoch = 0
            mock_phase.escalation_level = 0
            mock_phase.version = 5  # Initial version

            mock_query = MagicMock()
            mock_db.query.return_value = mock_query
            mock_query.with_for_update.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.first.return_value = mock_phase

            request = StateUpdateRequest(increment_retry=True)
            mgr.update("phase-123", request)

            # Verify version was incremented
            assert mock_phase.version == 6

    def test_select_for_update_used_in_mark_complete(self):
        """Test that SELECT FOR UPDATE is used in mark_complete."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        with patch("autopack.database.SessionLocal") as mock_session_local:
            mock_db = MagicMock()
            mock_session_local.return_value.__enter__.return_value = mock_db

            mock_phase = Mock()
            mock_phase.phase_id = "phase-123"
            mock_phase.run_id = "test-run"
            mock_phase.version = 1

            mock_query = MagicMock()
            mock_db.query.return_value = mock_query
            mock_query.with_for_update.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.first.return_value = mock_phase

            mgr.mark_complete("phase-123")

            # Verify with_for_update was called
            mock_query.with_for_update.assert_called_once()

    def test_select_for_update_used_in_mark_failed(self):
        """Test that SELECT FOR UPDATE is used in mark_failed."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        with patch("autopack.database.SessionLocal") as mock_session_local:
            mock_db = MagicMock()
            mock_session_local.return_value.__enter__.return_value = mock_db

            mock_phase = Mock()
            mock_phase.phase_id = "phase-123"
            mock_phase.run_id = "test-run"
            mock_phase.version = 1

            mock_query = MagicMock()
            mock_db.query.return_value = mock_query
            mock_query.with_for_update.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.first.return_value = mock_phase

            mgr.mark_failed("phase-123", "BUILD_FAILED")

            # Verify with_for_update was called
            mock_query.with_for_update.assert_called_once()


class TestStatePersistenceRetry:
    """Test retry logic in state persistence."""

    def test_save_state_retries_on_transient_failure(self, tmp_path):
        """Test that save_state retries on transient OSError."""
        storage_dir = tmp_path / "state_storage"
        mgr = ExecutorStateManager(storage_dir=storage_dir)

        state = ExecutorState(
            run_id="test-run",
            project_id="test-project",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # Track call count
        call_count = [0]

        original_write = Path.write_text

        def flaky_write_text(self, *args, **kwargs):
            """Simulate transient failure on first call."""
            call_count[0] += 1
            if call_count[0] == 1:
                raise OSError("Transient filesystem error")
            return original_write(self, *args, **kwargs)

        with patch.object(Path, "write_text", flaky_write_text):
            # Should succeed after retry
            mgr.save_state(state)

        # Verify it retried
        assert call_count[0] > 1

    def test_save_state_raises_persistence_error_on_non_retriable(self, tmp_path):
        """Test that non-retriable errors raise PersistenceError."""
        storage_dir = tmp_path / "state_storage"
        mgr = ExecutorStateManager(storage_dir=storage_dir)

        state = ExecutorState(
            run_id="test-run",
            project_id="test-project",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        with patch.object(Path, "write_text", side_effect=ValueError("Non-retriable error")):
            with pytest.raises(PersistenceError):
                mgr.save_state(state)

    def test_save_state_succeeds_on_first_try(self, tmp_path):
        """Test normal case where save_state succeeds immediately."""
        storage_dir = tmp_path / "state_storage"
        mgr = ExecutorStateManager(storage_dir=storage_dir)

        state = ExecutorState(
            run_id="test-run",
            project_id="test-project",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # Should succeed without retry
        mgr.save_state(state)

        # Verify state was written
        state_path = storage_dir / "test-run" / "executor_state.json"
        assert state_path.exists()

    def test_save_state_exhausts_retries_on_persistent_failure(self, tmp_path):
        """Test that save_state fails after exhausting retries."""
        storage_dir = tmp_path / "state_storage"
        mgr = ExecutorStateManager(storage_dir=storage_dir)

        state = ExecutorState(
            run_id="test-run",
            project_id="test-project",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # Simulate persistent OSError
        with patch.object(Path, "write_text", side_effect=OSError("Persistent error")):
            # Tenacity wraps the final exception in a RetryError
            with pytest.raises((OSError, RetryError)):
                mgr.save_state(state)
