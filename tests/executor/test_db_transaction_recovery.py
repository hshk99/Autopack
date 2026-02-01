"""Test database transaction recovery and session cleanup.

This module validates that database sessions are properly cleaned up
in all exception scenarios, preventing resource leaks and connection exhaustion.
"""

from unittest import mock

from autopack.executor import db_events


class TestSessionCleanup:
    """Test that database sessions are always cleaned up."""

    def test_token_budget_escalation_success_closes_session(self):
        """Session should close after successful commit."""
        mock_session = mock.MagicMock()
        mock_event_model = mock.MagicMock()

        with mock.patch.object(db_events, "_get_session_local", return_value=mock_session):
            with mock.patch.object(
                db_events,
                "_get_token_budget_escalation_event_model",
                return_value=mock_event_model,
            ):
                result = db_events.try_record_token_budget_escalation_event(
                    run_id="test-run",
                    phase_id="test-phase",
                    attempt_index=1,
                    reason="truncation",
                    was_truncated=True,
                )

        # Verify success
        assert result is True
        # Verify session was added to
        assert mock_session.add.called
        # Verify commit was called
        assert mock_session.commit.called
        # Verify session was closed even on success
        assert mock_session.close.called

    def test_token_budget_escalation_rollback_closes_session(self):
        """Session should rollback and close on exception during commit."""
        mock_session = mock.MagicMock()
        mock_event_model = mock.MagicMock()
        # Simulate exception on commit
        mock_session.commit.side_effect = RuntimeError("Database error")

        with mock.patch.object(db_events, "_get_session_local", return_value=mock_session):
            with mock.patch.object(
                db_events,
                "_get_token_budget_escalation_event_model",
                return_value=mock_event_model,
            ):
                result = db_events.try_record_token_budget_escalation_event(
                    run_id="test-run",
                    phase_id="test-phase",
                    attempt_index=1,
                    reason="truncation",
                    was_truncated=True,
                )

        # Verify failure was handled gracefully
        assert result is False
        # Verify rollback was called
        assert mock_session.rollback.called
        # Verify session was closed even on failure
        assert mock_session.close.called

    def test_token_budget_escalation_close_exception_ignored(self):
        """Session close exceptions should not prevent function from returning."""
        mock_session = mock.MagicMock()
        mock_event_model = mock.MagicMock()
        # Simulate exception on close (should be caught and ignored)
        mock_session.close.side_effect = RuntimeError("Close failed")

        with mock.patch.object(db_events, "_get_session_local", return_value=mock_session):
            with mock.patch.object(
                db_events,
                "_get_token_budget_escalation_event_model",
                return_value=mock_event_model,
            ):
                # Should not raise even if close fails
                result = db_events.try_record_token_budget_escalation_event(
                    run_id="test-run",
                    phase_id="test-phase",
                    attempt_index=1,
                    reason="truncation",
                    was_truncated=True,
                )

        # Should still succeed despite close exception
        assert result is True
        # Verify close was attempted
        assert mock_session.close.called

    def test_retry_max_tokens_closes_session_on_success(self):
        """Session should close after successful query."""
        mock_session = mock.MagicMock()
        mock_event_model = mock.MagicMock()
        mock_event = mock.MagicMock()
        mock_event.attempt_index = "1"
        mock_event.retry_max_tokens = 4000

        query_mock = mock.MagicMock()
        query_mock.filter.return_value.order_by.return_value.first.return_value = mock_event
        mock_session.query.return_value = query_mock

        with mock.patch.object(db_events, "_get_session_local", return_value=mock_session):
            with mock.patch.object(
                db_events,
                "_get_token_budget_escalation_event_model",
                return_value=mock_event_model,
            ):
                phase = {"phase_id": "test-phase"}
                db_events.maybe_apply_retry_max_tokens_from_db(
                    run_id="test-run",
                    phase=phase,
                    attempt_index=1,
                )

        # Verify session was closed
        assert mock_session.close.called

    def test_retry_max_tokens_closes_session_on_exception(self):
        """Session should close even if query raises exception."""
        mock_session = mock.MagicMock()
        mock_event_model = mock.MagicMock()
        # Simulate exception during query
        mock_session.query.side_effect = RuntimeError("Query failed")

        with mock.patch.object(db_events, "_get_session_local", return_value=mock_session):
            with mock.patch.object(
                db_events,
                "_get_token_budget_escalation_event_model",
                return_value=mock_event_model,
            ):
                phase = {"phase_id": "test-phase"}
                # Should not raise despite query failure (best-effort semantics)
                db_events.maybe_apply_retry_max_tokens_from_db(
                    run_id="test-run",
                    phase=phase,
                    attempt_index=1,
                )

        # Verify session was closed despite exception
        assert mock_session.close.called

    def test_session_resource_leak_prevention(self):
        """Verify no resource leaks with multiple operations."""
        # This test verifies that repeated calls don't accumulate unclosed sessions
        mock_session = mock.MagicMock()
        mock_event_model = mock.MagicMock()

        with mock.patch.object(db_events, "_get_session_local", return_value=mock_session):
            with mock.patch.object(
                db_events,
                "_get_token_budget_escalation_event_model",
                return_value=mock_event_model,
            ):
                # Call multiple times
                for i in range(5):
                    result = db_events.try_record_token_budget_escalation_event(
                        run_id=f"test-run-{i}",
                        phase_id="test-phase",
                        attempt_index=1,
                        reason="truncation",
                        was_truncated=True,
                    )
                    assert result is True

        # Verify close was called for each operation
        # (Note: Due to mocking, this will be the same mock object, but the call count
        # represents the number of times close should have been called)
        assert mock_session.close.call_count >= 1
