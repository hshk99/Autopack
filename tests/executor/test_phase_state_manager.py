"""Contract tests for PhaseStateManager (PR-EXE-9).

These tests verify the phase state persistence layer extracted from
autonomous_executor.py as part of PR-EXE-9.

Test coverage (25 tests):
1. State loading and defaults
2. State updates and increments
3. Mark complete/failed operations
4. Error handling
5. Database integration
"""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from autopack.executor.phase_state_manager import (
    PhaseState,
    PhaseStateManager,
    StateUpdateRequest,
)


class TestPhaseStateLoading:
    """Test state loading and default creation."""

    def test_load_or_create_default_returns_defaults_when_no_db_record(self):
        """Test default state when phase not in database."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        with patch.object(mgr, "_get_phase_from_db", return_value=None):
            state = mgr.load_or_create_default("phase-123")

        assert state.retry_attempt == 0
        assert state.revision_epoch == 0
        assert state.escalation_level == 0
        assert state.last_failure_reason is None
        assert state.last_attempt_timestamp is None

    def test_load_or_create_default_loads_from_db_when_record_exists(self):
        """Test loading existing state from database."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        mock_phase = Mock()
        mock_phase.retry_attempt = 3
        mock_phase.revision_epoch = 1
        mock_phase.escalation_level = 2
        mock_phase.last_failure_reason = "BUILD_FAILED"
        mock_phase.last_attempt_timestamp = datetime.now(timezone.utc)

        with patch.object(mgr, "_get_phase_from_db", return_value=mock_phase):
            state = mgr.load_or_create_default("phase-123")

        assert state.retry_attempt == 3
        assert state.revision_epoch == 1
        assert state.escalation_level == 2
        assert state.last_failure_reason == "BUILD_FAILED"
        assert state.last_attempt_timestamp is not None

    def test_load_or_create_default_handles_missing_attributes(self):
        """Test graceful handling when DB record missing attributes."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        mock_phase = Mock()
        # Only set some attributes
        mock_phase.retry_attempt = 2
        del mock_phase.revision_epoch  # Simulate missing attribute
        del mock_phase.escalation_level

        with patch.object(mgr, "_get_phase_from_db", return_value=mock_phase):
            state = mgr.load_or_create_default("phase-123")

        assert state.retry_attempt == 2
        assert state.revision_epoch == 0  # Default when missing
        assert state.escalation_level == 0  # Default when missing


class TestStateUpdates:
    """Test state update operations."""

    def test_update_increment_retry(self):
        """Test incrementing retry attempt."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        # Mock current state: retry=2
        current_state = PhaseState(retry_attempt=2, revision_epoch=0, escalation_level=0)

        with patch.object(mgr, "load_or_create_default", return_value=current_state):
            with patch.object(
                mgr, "_update_phase_attempts_in_db", return_value=True
            ) as mock_update:
                request = StateUpdateRequest(increment_retry=True)
                result = mgr.update("phase-123", request)

        assert result is True
        mock_update.assert_called_once_with("phase-123", retry_attempt=3)

    def test_update_increment_epoch(self):
        """Test incrementing revision epoch."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        current_state = PhaseState(retry_attempt=0, revision_epoch=1, escalation_level=0)

        with patch.object(mgr, "load_or_create_default", return_value=current_state):
            with patch.object(
                mgr, "_update_phase_attempts_in_db", return_value=True
            ) as mock_update:
                request = StateUpdateRequest(increment_epoch=True)
                result = mgr.update("phase-123", request)

        assert result is True
        mock_update.assert_called_once_with("phase-123", revision_epoch=2)

    def test_update_increment_escalation(self):
        """Test incrementing escalation level."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        current_state = PhaseState(retry_attempt=0, revision_epoch=0, escalation_level=0)

        with patch.object(mgr, "load_or_create_default", return_value=current_state):
            with patch.object(
                mgr, "_update_phase_attempts_in_db", return_value=True
            ) as mock_update:
                request = StateUpdateRequest(increment_escalation=True)
                result = mgr.update("phase-123", request)

        assert result is True
        mock_update.assert_called_once_with("phase-123", escalation_level=1)

    def test_update_set_explicit_values(self):
        """Test setting explicit state values."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        current_state = PhaseState(retry_attempt=5, revision_epoch=2, escalation_level=1)

        with patch.object(mgr, "load_or_create_default", return_value=current_state):
            with patch.object(
                mgr, "_update_phase_attempts_in_db", return_value=True
            ) as mock_update:
                request = StateUpdateRequest(set_retry=10, set_epoch=5, set_escalation=3)
                result = mgr.update("phase-123", request)

        assert result is True
        # Should set to explicit values, not increment
        mock_update.assert_called_once_with(
            "phase-123", retry_attempt=10, revision_epoch=5, escalation_level=3
        )

    def test_update_with_failure_reason(self):
        """Test updating with failure reason."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        current_state = PhaseState(retry_attempt=1, revision_epoch=0, escalation_level=0)

        with patch.object(mgr, "load_or_create_default", return_value=current_state):
            with patch.object(
                mgr, "_update_phase_attempts_in_db", return_value=True
            ) as mock_update:
                request = StateUpdateRequest(
                    increment_retry=True, failure_reason="PATCH_APPLY_FAILED"
                )
                result = mgr.update("phase-123", request)

        assert result is True
        mock_update.assert_called_once_with(
            "phase-123", retry_attempt=2, last_failure_reason="PATCH_APPLY_FAILED"
        )

    def test_update_multiple_increments(self):
        """Test updating multiple counters simultaneously."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        current_state = PhaseState(retry_attempt=2, revision_epoch=1, escalation_level=0)

        with patch.object(mgr, "load_or_create_default", return_value=current_state):
            with patch.object(
                mgr, "_update_phase_attempts_in_db", return_value=True
            ) as mock_update:
                request = StateUpdateRequest(increment_retry=True, increment_escalation=True)
                result = mgr.update("phase-123", request)

        assert result is True
        mock_update.assert_called_once_with("phase-123", retry_attempt=3, escalation_level=1)

    def test_update_no_changes_returns_true_without_db_call(self):
        """Test that update with no changes doesn't call database."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        current_state = PhaseState(retry_attempt=2, revision_epoch=0, escalation_level=0)

        with patch.object(mgr, "load_or_create_default", return_value=current_state):
            with patch.object(mgr, "_update_phase_attempts_in_db") as mock_update:
                request = StateUpdateRequest()  # No changes
                result = mgr.update("phase-123", request)

        assert result is True
        mock_update.assert_not_called()  # No DB call for empty update


class TestMarkCompleteAndFailed:
    """Test mark complete and mark failed operations."""

    def test_mark_complete_calls_manager(self):
        """Test marking phase complete delegates to state manager."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        with patch.object(mgr, "_mark_phase_complete_in_db", return_value=True) as mock_complete:
            result = mgr.mark_complete("phase-123")

        assert result is True
        mock_complete.assert_called_once_with("phase-123")

    def test_mark_complete_returns_false_on_failure(self):
        """Test mark complete returns False on database error."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        with patch.object(mgr, "_mark_phase_complete_in_db", return_value=False):
            result = mgr.mark_complete("phase-123")

        assert result is False

    def test_mark_failed_calls_manager_with_reason(self):
        """Test marking phase failed delegates with reason."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        with patch.object(mgr, "_mark_phase_failed_in_db", return_value=True) as mock_failed:
            result = mgr.mark_failed("phase-123", "MAX_ATTEMPTS_EXHAUSTED")

        assert result is True
        mock_failed.assert_called_once_with("phase-123", "MAX_ATTEMPTS_EXHAUSTED")

    def test_mark_failed_returns_false_on_failure(self):
        """Test mark failed returns False on database error."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        with patch.object(mgr, "_mark_phase_failed_in_db", return_value=False):
            result = mgr.mark_failed("phase-123", "BUILDER_FAILED")

        assert result is False


class TestDatabaseIntegration:
    """Test actual database integration (mocked at DB level)."""

    @patch("autopack.database.SessionLocal")
    def test_get_phase_from_db_queries_database(self, mock_session_local):
        """Test _get_phase_from_db queries database correctly."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        mock_db = Mock()
        mock_session_local.return_value.__enter__ = Mock(return_value=mock_db)
        mock_session_local.return_value.__exit__ = Mock(return_value=False)

        mock_phase = Mock()
        mock_phase.retry_attempt = 2
        mock_phase.revision_epoch = 1
        mock_phase.escalation_level = 0
        mock_phase.state = "IN_PROGRESS"

        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = mock_phase
        mock_db.query.return_value = mock_query

        result = mgr._get_phase_from_db("phase-123")

        assert result == mock_phase
        mock_session_local.return_value.__exit__.assert_called_once()

    @patch("autopack.database.SessionLocal")
    def test_get_phase_from_db_returns_none_when_not_found(self, mock_session_local):
        """Test _get_phase_from_db returns None when phase not found."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        mock_db = Mock()
        mock_session_local.return_value = mock_db

        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = None
        mock_db.query.return_value = mock_query

        result = mgr._get_phase_from_db("phase-123")

        assert result is None

    @patch("autopack.database.SessionLocal")
    def test_update_phase_attempts_in_db_updates_counters(self, mock_session_local):
        """Test _update_phase_attempts_in_db updates database correctly."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        mock_db = Mock()
        mock_session_local.return_value.__enter__ = Mock(return_value=mock_db)
        mock_session_local.return_value.__exit__ = Mock(return_value=False)

        mock_phase = Mock()
        mock_phase.retry_attempt = 0
        mock_phase.revision_epoch = 0
        mock_phase.escalation_level = 0
        mock_phase.version = 1  # Add version attribute for optimistic locking

        # Set up proper query chain: query().with_for_update().filter().first()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.with_for_update.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_phase

        result = mgr._update_phase_attempts_in_db(
            "phase-123", retry_attempt=3, revision_epoch=1, escalation_level=0
        )

        assert result is True
        assert mock_phase.retry_attempt == 3
        assert mock_phase.revision_epoch == 1
        assert mock_phase.escalation_level == 0
        assert mock_phase.version == 2  # Version should be incremented
        mock_db.commit.assert_called_once()
        mock_session_local.return_value.__exit__.assert_called_once()

    @patch("autopack.database.SessionLocal")
    def test_update_phase_attempts_in_db_returns_false_when_phase_not_found(
        self, mock_session_local
    ):
        """Test update returns False when phase not found."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        mock_db = Mock()
        mock_session_local.return_value = mock_db

        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = None
        mock_db.query.return_value = mock_query

        result = mgr._update_phase_attempts_in_db("phase-123", retry_attempt=3)

        assert result is False
        mock_db.commit.assert_not_called()

    @patch("autopack.database.SessionLocal")
    def test_mark_phase_complete_in_db_sets_state_and_timestamp(self, mock_session_local):
        """Test _mark_phase_complete_in_db updates state correctly."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        mock_db = Mock()
        mock_session_local.return_value.__enter__ = Mock(return_value=mock_db)
        mock_session_local.return_value.__exit__ = Mock(return_value=False)

        mock_phase = Mock()
        mock_phase.created_at = datetime.now(timezone.utc)
        mock_phase.version = 1  # Add version attribute for optimistic locking

        # Set up proper query chain: query().with_for_update().filter().first()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.with_for_update.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_phase

        # Mock PhaseState enum
        with patch("autopack.models.PhaseState"):
            result = mgr._mark_phase_complete_in_db("phase-123")

        assert result is True
        assert hasattr(mock_phase, "completed_at")
        assert mock_phase.version == 2  # Version should be incremented
        mock_db.commit.assert_called_once()

    @patch("autopack.database.SessionLocal")
    def test_mark_phase_failed_in_db_sets_state_reason_and_timestamp(self, mock_session_local):
        """Test _mark_phase_failed_in_db updates state and reason."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        mock_db = Mock()
        mock_session_local.return_value.__enter__ = Mock(return_value=mock_db)
        mock_session_local.return_value.__exit__ = Mock(return_value=False)

        mock_phase = Mock()
        mock_phase.created_at = datetime.now(timezone.utc)
        mock_phase.version = 1  # Add version attribute for optimistic locking

        # Set up proper query chain: query().with_for_update().filter().first()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.with_for_update.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_phase

        with patch("autopack.models.PhaseState"):
            result = mgr._mark_phase_failed_in_db("phase-123", "MAX_ATTEMPTS_EXHAUSTED")

        assert result is True
        assert mock_phase.last_failure_reason == "MAX_ATTEMPTS_EXHAUSTED"
        assert hasattr(mock_phase, "completed_at")
        assert mock_phase.version == 2  # Version should be incremented
        mock_db.commit.assert_called_once()


class TestErrorHandling:
    """Test error handling and edge cases."""

    @patch("autopack.database.SessionLocal")
    def test_get_phase_from_db_handles_database_error(self, mock_session_local):
        """Test graceful error handling when database query fails."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        mock_session_local.side_effect = Exception("Database connection failed")

        result = mgr._get_phase_from_db("phase-123")

        assert result is None  # Returns None on error

    @patch("autopack.database.SessionLocal")
    def test_update_phase_attempts_handles_commit_error(self, mock_session_local):
        """Test error handling when commit fails."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        mock_db = Mock()
        mock_session_local.return_value = mock_db

        mock_phase = Mock()
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = mock_phase
        mock_db.query.return_value = mock_query

        mock_db.commit.side_effect = Exception("Commit failed")

        result = mgr._update_phase_attempts_in_db("phase-123", retry_attempt=3)

        assert result is False

    @patch("autopack.database.SessionLocal")
    def test_session_context_manager_closes_on_exception(self, mock_session_local):
        """Test that session context manager ensures cleanup even on exceptions."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        mock_db = Mock()
        mock_session_local.return_value.__enter__ = Mock(return_value=mock_db)
        mock_session_local.return_value.__exit__ = Mock(return_value=False)

        mock_query = Mock()
        mock_query.filter.return_value.first.side_effect = Exception("Query failed")
        mock_db.query.return_value = mock_query

        result = mgr._get_phase_from_db("phase-123")

        assert result is None  # Returns None on error
        # Context manager __exit__ should be called (automatic cleanup)
        mock_session_local.return_value.__exit__.assert_called_once()

    @patch("autopack.database.SessionLocal")
    def test_update_ensures_commit_called_before_context_exit(self, mock_session_local):
        """Test that commit is called within the context manager before session closes."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        mock_db = Mock()
        mock_session_local.return_value.__enter__ = Mock(return_value=mock_db)
        mock_session_local.return_value.__exit__ = Mock(return_value=False)

        mock_phase = Mock()
        mock_phase.retry_attempt = 0
        mock_phase.version = 1  # Add version attribute for optimistic locking

        # Set up proper query chain: query().with_for_update().filter().first()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.with_for_update.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_phase

        # Track call order
        call_order = []
        mock_db.commit.side_effect = lambda: call_order.append("commit")
        mock_session_local.return_value.__exit__.side_effect = lambda *args: call_order.append(
            "exit"
        )

        result = mgr._update_phase_attempts_in_db("phase-123", retry_attempt=3)

        assert result is True
        assert call_order == ["commit", "exit"]  # Commit before context exit

    @patch("autopack.database.SessionLocal")
    def test_mark_complete_ensures_transaction_boundaries(self, mock_session_local):
        """Test that mark_complete properly commits within transaction boundaries."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        mock_db = Mock()
        mock_session_local.return_value.__enter__ = Mock(return_value=mock_db)
        mock_session_local.return_value.__exit__ = Mock(return_value=False)

        mock_phase = Mock()
        mock_phase.version = 1  # Add version attribute for optimistic locking

        # Set up proper query chain: query().with_for_update().filter().first()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.with_for_update.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_phase

        with patch("autopack.models.PhaseState"):
            result = mgr._mark_phase_complete_in_db("phase-123")

        assert result is True
        mock_db.commit.assert_called_once()
        mock_session_local.return_value.__exit__.assert_called_once()

    @patch("autopack.database.SessionLocal")
    def test_mark_failed_ensures_transaction_boundaries(self, mock_session_local):
        """Test that mark_failed properly commits within transaction boundaries."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        mock_db = Mock()
        mock_session_local.return_value.__enter__ = Mock(return_value=mock_db)
        mock_session_local.return_value.__exit__ = Mock(return_value=False)

        mock_phase = Mock()
        mock_phase.version = 1  # Add version attribute for optimistic locking

        # Set up proper query chain: query().with_for_update().filter().first()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.with_for_update.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_phase

        with patch("autopack.models.PhaseState"):
            result = mgr._mark_phase_failed_in_db("phase-123", "MAX_ATTEMPTS_EXHAUSTED")

        assert result is True
        mock_db.commit.assert_called_once()
        mock_session_local.return_value.__exit__.assert_called_once()


class TestStateUpdateRequestBuilder:
    """Test StateUpdateRequest builder pattern."""

    def test_state_update_request_defaults(self):
        """Test StateUpdateRequest defaults to no changes."""
        request = StateUpdateRequest()

        assert request.increment_retry is False
        assert request.increment_epoch is False
        assert request.increment_escalation is False
        assert request.set_retry is None
        assert request.set_epoch is None
        assert request.set_escalation is None
        assert request.failure_reason is None
        assert request.timestamp is None

    def test_state_update_request_partial_fields(self):
        """Test StateUpdateRequest with partial fields set."""
        request = StateUpdateRequest(increment_retry=True, failure_reason="TIMEOUT")

        assert request.increment_retry is True
        assert request.increment_epoch is False
        assert request.failure_reason == "TIMEOUT"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
