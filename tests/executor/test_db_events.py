"""Tests for db_events.py - best-effort DB operations.

IMP-REL-001: Verify database session rollback on commit failure.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestDBEventPersisterRollback:
    """Test rollback behavior on commit failure (IMP-REL-001)."""

    def test_rollback_on_commit_failure(self):
        """Verify session.rollback() is called when commit fails."""
        from autopack.executor.db_events import try_record_token_budget_escalation_event

        mock_session = MagicMock()
        mock_session.commit.side_effect = Exception("commit failed")

        mock_event_class = Mock()

        with patch(
            "autopack.executor.db_events._get_session_local",
            return_value=mock_session,
        ):
            with patch(
                "autopack.executor.db_events._get_token_budget_escalation_event_model",
                return_value=mock_event_class,
            ):
                result = try_record_token_budget_escalation_event(
                    run_id="test-run",
                    phase_id="test-phase",
                    attempt_index=1,
                    reason="truncation",
                    was_truncated=True,
                )

        # Should return False on failure (best-effort semantics)
        assert result is False
        # Verify rollback was called
        mock_session.rollback.assert_called_once()
        # Verify session was closed
        mock_session.close.assert_called_once()

    def test_successful_commit_no_rollback(self):
        """Verify rollback is NOT called on successful commit."""
        from autopack.executor.db_events import try_record_token_budget_escalation_event

        mock_session = MagicMock()
        mock_event_class = Mock()

        with patch(
            "autopack.executor.db_events._get_session_local",
            return_value=mock_session,
        ):
            with patch(
                "autopack.executor.db_events._get_token_budget_escalation_event_model",
                return_value=mock_event_class,
            ):
                result = try_record_token_budget_escalation_event(
                    run_id="test-run",
                    phase_id="test-phase",
                    attempt_index=1,
                    reason="truncation",
                    was_truncated=True,
                )

        # Should return True on success
        assert result is True
        # Verify rollback was NOT called
        mock_session.rollback.assert_not_called()
        # Verify commit was called
        mock_session.commit.assert_called_once()
        # Verify session was closed
        mock_session.close.assert_called_once()

    def test_rollback_on_db_operational_error(self):
        """Verify rollback handles SQLAlchemy OperationalError."""
        from sqlalchemy.exc import OperationalError
        from autopack.executor.db_events import try_record_token_budget_escalation_event

        mock_session = MagicMock()
        mock_session.commit.side_effect = OperationalError("statement", {}, Exception())
        mock_event_class = Mock()

        with patch(
            "autopack.executor.db_events._get_session_local",
            return_value=mock_session,
        ):
            with patch(
                "autopack.executor.db_events._get_token_budget_escalation_event_model",
                return_value=mock_event_class,
            ):
                result = try_record_token_budget_escalation_event(
                    run_id="test-run",
                    phase_id="test-phase",
                    attempt_index=1,
                    reason="utilization",
                    was_truncated=False,
                    output_utilization=0.95,
                )

        # Should return False on failure
        assert result is False
        # Verify rollback was called
        mock_session.rollback.assert_called_once()

    def test_session_closed_even_when_rollback_fails(self):
        """Verify session.close() is called even if rollback fails."""
        from autopack.executor.db_events import try_record_token_budget_escalation_event

        mock_session = MagicMock()
        mock_session.commit.side_effect = Exception("commit failed")
        mock_session.rollback.side_effect = Exception("rollback also failed")
        mock_event_class = Mock()

        with patch(
            "autopack.executor.db_events._get_session_local",
            return_value=mock_session,
        ):
            with patch(
                "autopack.executor.db_events._get_token_budget_escalation_event_model",
                return_value=mock_event_class,
            ):
                # Should not raise - best-effort semantics
                result = try_record_token_budget_escalation_event(
                    run_id="test-run",
                    phase_id="test-phase",
                    attempt_index=1,
                    reason="truncation",
                    was_truncated=True,
                )

        # Should return False on failure
        assert result is False
        # Session close should still be attempted
        mock_session.close.assert_called_once()


class TestMaybeApplyRetryMaxTokensFromDB:
    """Test read-only DB operation (no commit/rollback needed)."""

    def test_read_does_not_mutate_on_failure(self):
        """Verify read operation doesn't modify phase dict on DB failure."""
        from autopack.executor.db_events import maybe_apply_retry_max_tokens_from_db

        phase = {"phase_id": "test-phase"}

        with patch(
            "autopack.executor.db_events._get_session_local",
            side_effect=Exception("DB unavailable"),
        ):
            # Should not raise - best-effort semantics
            maybe_apply_retry_max_tokens_from_db(
                run_id="test-run",
                phase=phase,
                attempt_index=1,
            )

        # Phase should not have _escalated_tokens added
        assert "_escalated_tokens" not in phase

    def test_read_applies_escalated_tokens_on_success(self):
        """Verify escalated tokens are applied when event found."""
        from autopack.executor.db_events import maybe_apply_retry_max_tokens_from_db

        phase = {"phase_id": "test-phase"}

        mock_session = MagicMock()
        mock_event = Mock()
        mock_event.attempt_index = 1
        mock_event.retry_max_tokens = 8000

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = mock_event
        mock_session.query.return_value = mock_query

        mock_event_class = Mock()

        with patch(
            "autopack.executor.db_events._get_session_local",
            return_value=mock_session,
        ):
            with patch(
                "autopack.executor.db_events._get_token_budget_escalation_event_model",
                return_value=mock_event_class,
            ):
                maybe_apply_retry_max_tokens_from_db(
                    run_id="test-run",
                    phase=phase,
                    attempt_index=1,
                )

        # Phase should have _escalated_tokens set
        assert phase.get("_escalated_tokens") == 8000
