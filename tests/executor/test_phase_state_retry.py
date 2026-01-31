"""Tests for PhaseStateManager retry logic (IMP-REL-007).

Tests verify that phase state operations retry on transient database errors
with exponential backoff, improving reliability for critical state updates.

Test coverage:
1. Retry on transient errors (OperationalError, InterfaceError)
2. Successful recovery after transient failure
3. Proper exhaustion of retries on persistent errors
4. OptimisticLockError not retried
5. Logging of retry attempts
"""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from sqlalchemy.exc import InterfaceError, OperationalError

from autopack.executor.phase_state_manager import (OptimisticLockError,
                                                   PhaseStateManager)


class TestRetryOnOperationalError:
    """Test retry behavior on OperationalError (transient DB failures)."""

    @patch("autopack.database.SessionLocal")
    def test_get_phase_from_db_retries_on_operational_error(self, mock_session_local):
        """Test _get_phase_from_db retries on OperationalError."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        # First two calls fail with OperationalError, third succeeds
        mock_db = Mock()
        mock_session_local.return_value.__enter__ = Mock(return_value=mock_db)
        mock_session_local.return_value.__exit__ = Mock(return_value=False)

        mock_phase = Mock()
        mock_phase.retry_attempt = 2
        mock_phase.revision_epoch = 0
        mock_phase.escalation_level = 0
        mock_phase.state = "IN_PROGRESS"

        mock_query = Mock()

        # Set up side effect: fail twice, then succeed
        mock_query.filter.return_value.first.side_effect = [
            OperationalError("Connection timeout", None, None),
            OperationalError("Connection timeout", None, None),
            mock_phase,
        ]
        mock_db.query.return_value = mock_query

        result = mgr._get_phase_from_db("phase-123")

        # Should succeed after retries
        assert result == mock_phase
        # Should have called query 3 times (2 failures + 1 success)
        assert mock_db.query.call_count == 3

    @patch("autopack.database.SessionLocal")
    def test_update_phase_attempts_retries_on_operational_error(self, mock_session_local):
        """Test _update_phase_attempts_in_db retries on transient OperationalError."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        mock_db = Mock()
        mock_session_local.return_value.__enter__ = Mock(return_value=mock_db)
        mock_session_local.return_value.__exit__ = Mock(return_value=False)

        mock_phase = Mock()
        mock_phase.retry_attempt = 0
        mock_phase.revision_epoch = 0
        mock_phase.escalation_level = 0
        mock_phase.version = 1

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.with_for_update.return_value = mock_query
        mock_query.filter.return_value = mock_query

        # First commit fails with connection timeout (transient, not deadlock), second succeeds
        mock_db.commit.side_effect = [
            OperationalError("Connection timeout", None, None),
            None,
        ]
        mock_query.first.return_value = mock_phase

        result = mgr._update_phase_attempts_in_db("phase-123", retry_attempt=3)

        # Should succeed after retry
        assert result is True
        assert mock_db.commit.call_count == 2

    @patch("autopack.database.SessionLocal")
    def test_mark_complete_retries_on_operational_error(self, mock_session_local):
        """Test _mark_phase_complete_in_db retries on OperationalError."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        mock_db = Mock()
        mock_session_local.return_value.__enter__ = Mock(return_value=mock_db)
        mock_session_local.return_value.__exit__ = Mock(return_value=False)

        mock_phase = Mock()
        mock_phase.version = 1

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.with_for_update.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_phase

        # First commit fails with transient error, second succeeds
        mock_db.commit.side_effect = [
            OperationalError("Connection lost", None, None),
            None,
        ]

        with patch("autopack.models.PhaseState"):
            result = mgr._mark_phase_complete_in_db("phase-123")

        assert result is True
        assert mock_db.commit.call_count == 2

    @patch("autopack.database.SessionLocal")
    def test_mark_failed_retries_on_operational_error(self, mock_session_local):
        """Test _mark_phase_failed_in_db retries on transient OperationalError."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        mock_db = Mock()
        mock_session_local.return_value.__enter__ = Mock(return_value=mock_db)
        mock_session_local.return_value.__exit__ = Mock(return_value=False)

        mock_phase = Mock()
        mock_phase.version = 1

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.with_for_update.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_phase

        # First commit fails with transient error, second succeeds
        mock_db.commit.side_effect = [
            OperationalError("Connection reset", None, None),
            None,
        ]

        with patch("autopack.models.PhaseState"):
            result = mgr._mark_phase_failed_in_db("phase-123", "TEST_FAILURE")

        assert result is True
        assert mock_db.commit.call_count == 2


class TestRetryOnInterfaceError:
    """Test retry behavior on InterfaceError (connection failures)."""

    @patch("autopack.database.SessionLocal")
    def test_get_phase_from_db_retries_on_interface_error(self, mock_session_local):
        """Test _get_phase_from_db retries on InterfaceError."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        mock_db = Mock()
        mock_session_local.return_value.__enter__ = Mock(return_value=mock_db)
        mock_session_local.return_value.__exit__ = Mock(return_value=False)

        mock_phase = Mock()
        mock_phase.retry_attempt = 1
        mock_phase.revision_epoch = 0
        mock_phase.escalation_level = 0
        mock_phase.state = "PENDING"

        mock_query = Mock()

        # Fail once with connection error, then succeed
        mock_query.filter.return_value.first.side_effect = [
            InterfaceError("Lost connection to database", None, None),
            mock_phase,
        ]
        mock_db.query.return_value = mock_query

        result = mgr._get_phase_from_db("phase-123")

        assert result == mock_phase
        assert mock_db.query.call_count == 2

    @patch("autopack.database.SessionLocal")
    def test_update_retries_on_interface_error(self, mock_session_local):
        """Test _update_phase_attempts_in_db retries on InterfaceError."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        mock_db = Mock()
        mock_session_local.return_value.__enter__ = Mock(return_value=mock_db)
        mock_session_local.return_value.__exit__ = Mock(return_value=False)

        mock_phase = Mock()
        mock_phase.retry_attempt = 0
        mock_phase.revision_epoch = 0
        mock_phase.escalation_level = 0
        mock_phase.version = 1

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.with_for_update.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_phase

        # First commit fails, second succeeds
        mock_db.commit.side_effect = [
            InterfaceError("Connection pool exhausted", None, None),
            None,
        ]

        result = mgr._update_phase_attempts_in_db("phase-123", retry_attempt=5)

        assert result is True
        assert mock_db.commit.call_count == 2


class TestRetryExhaustion:
    """Test behavior when retries are exhausted."""

    @patch("autopack.database.SessionLocal")
    def test_get_phase_from_db_exhausts_retries_on_persistent_error(self, mock_session_local):
        """Test _get_phase_from_db exhausts retries and re-raises on persistent error."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        mock_db = Mock()
        mock_session_local.return_value.__enter__ = Mock(return_value=mock_db)
        mock_session_local.return_value.__exit__ = Mock(return_value=False)

        mock_query = Mock()
        # All attempts fail
        mock_query.filter.return_value.first.side_effect = OperationalError(
            "Persistent connection error", None, None
        )
        mock_db.query.return_value = mock_query

        # Should exhaust retries and re-raise
        with pytest.raises(OperationalError):
            mgr._get_phase_from_db("phase-123")

        # Should have attempted 3 times
        assert mock_db.query.call_count == 3

    @patch("autopack.database.SessionLocal")
    def test_update_exhausts_retries_on_persistent_error(self, mock_session_local):
        """Test _update_phase_attempts_in_db exhausts retries and re-raises."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        mock_db = Mock()
        mock_session_local.return_value.__enter__ = Mock(return_value=mock_db)
        mock_session_local.return_value.__exit__ = Mock(return_value=False)

        mock_phase = Mock()
        mock_phase.retry_attempt = 0
        mock_phase.version = 1

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.with_for_update.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_phase

        # All attempts fail
        mock_db.commit.side_effect = OperationalError("Persistent database error", None, None)

        # Should exhaust retries and re-raise
        with pytest.raises(OperationalError):
            mgr._update_phase_attempts_in_db("phase-123", retry_attempt=10)

        # Should have attempted 3 times
        assert mock_db.commit.call_count == 3


class TestOptimisticLockErrorNoRetry:
    """Test that OptimisticLockError is not retried."""

    @patch("autopack.database.SessionLocal")
    def test_update_does_not_retry_optimistic_lock_error(self, mock_session_local):
        """Test that OptimisticLockError is raised immediately without retry."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        mock_db = Mock()
        mock_session_local.return_value.__enter__ = Mock(return_value=mock_db)
        mock_session_local.return_value.__exit__ = Mock(return_value=False)

        mock_phase = Mock()
        mock_phase.retry_attempt = 0
        mock_phase.version = 1

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.with_for_update.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_phase

        # Commit raises OperationalError with serialization failure (converts to OptimisticLockError)
        mock_db.commit.side_effect = OperationalError("serialization failure", None, None)

        # Should raise OptimisticLockError immediately without retrying
        with pytest.raises(OptimisticLockError):
            mgr._update_phase_attempts_in_db("phase-123", retry_attempt=5)

        # Should only attempt once because OptimisticLockError is not retried
        assert mock_db.commit.call_count == 1

    @patch("autopack.database.SessionLocal")
    def test_mark_complete_does_not_retry_optimistic_lock_error(self, mock_session_local):
        """Test _mark_phase_complete_in_db doesn't retry OptimisticLockError."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        mock_db = Mock()
        mock_session_local.return_value.__enter__ = Mock(return_value=mock_db)
        mock_session_local.return_value.__exit__ = Mock(return_value=False)

        mock_phase = Mock()
        mock_phase.version = 1

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.with_for_update.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_phase

        # Simulate deadlock (triggers OptimisticLockError)
        mock_db.commit.side_effect = OperationalError("deadlock detected", None, None)

        with patch("autopack.models.PhaseState"):
            with pytest.raises(OptimisticLockError):
                mgr._mark_phase_complete_in_db("phase-123")

        # Should only attempt once
        assert mock_db.commit.call_count == 1


class TestNonTransientErrors:
    """Test that non-transient errors are not retried."""

    @patch("autopack.database.SessionLocal")
    def test_get_phase_from_db_does_not_retry_generic_exception(self, mock_session_local):
        """Test that generic exceptions are not retried."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        mock_db = Mock()
        mock_session_local.return_value.__enter__ = Mock(return_value=mock_db)
        mock_session_local.return_value.__exit__ = Mock(return_value=False)

        mock_query = Mock()
        # Raise a non-transient error (programming error)
        mock_query.filter.return_value.first.side_effect = AttributeError("Invalid column name")
        mock_db.query.return_value = mock_query

        # Should return None (not retry)
        result = mgr._get_phase_from_db("phase-123")

        assert result is None
        # Should only attempt once
        assert mock_db.query.call_count == 1

    @patch("autopack.database.SessionLocal")
    def test_update_returns_false_on_generic_exception(self, mock_session_local):
        """Test that generic exceptions in update return False without retry."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        mock_db = Mock()
        mock_session_local.return_value.__enter__ = Mock(return_value=mock_db)
        mock_session_local.return_value.__exit__ = Mock(return_value=False)

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.with_for_update.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.side_effect = ValueError("Invalid value")

        result = mgr._update_phase_attempts_in_db("phase-123", retry_attempt=3)

        # Should return False (not retry generic exceptions)
        assert result is False
        # Should only attempt once
        assert mock_db.query.call_count == 1


class TestRetryLogging:
    """Test that retry attempts are properly logged."""

    @patch("autopack.database.SessionLocal")
    @patch("autopack.executor.phase_state_manager.logger")
    def test_get_phase_logs_retry_warnings(self, mock_logger, mock_session_local):
        """Test that retry attempts are logged as warnings."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        mock_db = Mock()
        mock_session_local.return_value.__enter__ = Mock(return_value=mock_db)
        mock_session_local.return_value.__exit__ = Mock(return_value=False)

        mock_phase = Mock()
        mock_phase.retry_attempt = 0
        mock_phase.revision_epoch = 0
        mock_phase.escalation_level = 0

        mock_query = Mock()
        # Fail once, then succeed
        mock_query.filter.return_value.first.side_effect = [
            OperationalError("Connection timeout", None, None),
            mock_phase,
        ]
        mock_db.query.return_value = mock_query

        result = mgr._get_phase_from_db("phase-123")

        assert result == mock_phase
        # Check that warning was logged for retry
        assert mock_logger.warning.called

    @patch("autopack.database.SessionLocal")
    @patch("autopack.executor.phase_state_manager.logger")
    def test_update_logs_retry_warnings(self, mock_logger, mock_session_local):
        """Test that update retries are logged as warnings."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        mock_db = Mock()
        mock_session_local.return_value.__enter__ = Mock(return_value=mock_db)
        mock_session_local.return_value.__exit__ = Mock(return_value=False)

        mock_phase = Mock()
        mock_phase.retry_attempt = 0
        mock_phase.revision_epoch = 0
        mock_phase.escalation_level = 0
        mock_phase.version = 1

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.with_for_update.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_phase

        # Fail once, then succeed
        mock_db.commit.side_effect = [
            OperationalError("Connection lost", None, None),
            None,
        ]

        result = mgr._update_phase_attempts_in_db("phase-123", retry_attempt=3)

        assert result is True
        # Check that warning was logged for retry
        assert mock_logger.warning.called


class TestIntegrationWithLoadOrCreate:
    """Test retry behavior integrated with load_or_create_default."""

    @patch("autopack.database.SessionLocal")
    def test_load_or_create_retries_on_transient_db_error(self, mock_session_local):
        """Test that load_or_create_default benefits from retry on transient errors."""
        mgr = PhaseStateManager(run_id="test-run", workspace=Path("/workspace"))

        mock_db = Mock()
        mock_session_local.return_value.__enter__ = Mock(return_value=mock_db)
        mock_session_local.return_value.__exit__ = Mock(return_value=False)

        mock_phase = Mock()
        mock_phase.retry_attempt = 5
        mock_phase.revision_epoch = 2
        mock_phase.escalation_level = 1
        mock_phase.last_failure_reason = "TIMEOUT"
        mock_phase.last_attempt_timestamp = datetime.now(timezone.utc)

        mock_query = Mock()
        # Fail once, then succeed
        mock_query.filter.return_value.first.side_effect = [
            OperationalError("Network timeout", None, None),
            mock_phase,
        ]
        mock_db.query.return_value = mock_query

        state = mgr.load_or_create_default("phase-123")

        # Should successfully load state after retry
        assert state.retry_attempt == 5
        assert state.revision_epoch == 2
        assert state.escalation_level == 1
        assert state.last_failure_reason == "TIMEOUT"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
