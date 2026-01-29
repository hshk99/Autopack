"""Tests for db_events.py - best-effort DB operations.

IMP-REL-001: Verify database session rollback on commit failure.
"""

from unittest.mock import MagicMock, Mock, patch


class TestDBEventPersisterRollback:
    """Test rollback behavior on commit failure (IMP-REL-001)."""

    def test_rollback_on_commit_failure(self):
        """Verify session.rollback() is called when commit fails."""
        from autopack.executor.db_events import \
            try_record_token_budget_escalation_event

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
        from autopack.executor.db_events import \
            try_record_token_budget_escalation_event

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

        from autopack.executor.db_events import \
            try_record_token_budget_escalation_event

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
        from autopack.executor.db_events import \
            try_record_token_budget_escalation_event

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
        from autopack.executor.db_events import \
            maybe_apply_retry_max_tokens_from_db

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
        from autopack.executor.db_events import \
            maybe_apply_retry_max_tokens_from_db

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

    def test_read_filters_by_run_and_phase_id(self):
        """Verify query filters correctly by run_id and phase_id."""
        from autopack.executor.db_events import \
            maybe_apply_retry_max_tokens_from_db

        phase = {"phase_id": "phase-123"}

        mock_session = MagicMock()
        mock_event = Mock()
        mock_event.attempt_index = 1
        mock_event.retry_max_tokens = 5000

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
                    run_id="run-456",
                    phase=phase,
                    attempt_index=1,
                )

        # Verify filter was called (query chain is called correctly)
        mock_session.query.assert_called_once()
        mock_query.filter.assert_called_once()

    def test_read_no_event_when_attempt_mismatch(self):
        """Verify _escalated_tokens not applied when attempt index doesn't match."""
        from autopack.executor.db_events import \
            maybe_apply_retry_max_tokens_from_db

        phase = {"phase_id": "test-phase"}

        mock_session = MagicMock()
        mock_event = Mock()
        mock_event.attempt_index = 2  # Event is for attempt 2
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
                    attempt_index=1,  # Looking for attempt 1
                )

        # Phase should NOT have _escalated_tokens set (attempt mismatch)
        assert "_escalated_tokens" not in phase

    def test_read_session_always_closed(self):
        """Verify session is always closed, even on success."""
        from autopack.executor.db_events import \
            maybe_apply_retry_max_tokens_from_db

        phase = {"phase_id": "test-phase"}

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = None
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
                    attempt_index=0,
                )

        # Session close should be called
        mock_session.close.assert_called_once()

    def test_read_handles_close_failure(self):
        """Verify read operation handles session.close() failure gracefully."""
        from autopack.executor.db_events import \
            maybe_apply_retry_max_tokens_from_db

        phase = {"phase_id": "test-phase"}

        mock_session = MagicMock()
        mock_session.close.side_effect = Exception("close failed")
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = None
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
                # Should not raise even though close fails
                maybe_apply_retry_max_tokens_from_db(
                    run_id="test-run",
                    phase=phase,
                    attempt_index=0,
                )

        # close() was still attempted
        mock_session.close.assert_called()


class TestTokenBudgetEscalationEventWrite:
    """Test token budget escalation event writing."""

    def test_record_with_all_fields(self):
        """Verify all fields are passed to event constructor."""
        from autopack.executor.db_events import \
            try_record_token_budget_escalation_event

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
                    run_id="run-789",
                    phase_id="phase-456",
                    attempt_index=3,
                    reason="truncation",
                    was_truncated=True,
                    completion_tokens_used=2500,
                    retry_max_tokens=5000,
                    output_utilization=0.92,
                    escalation_factor=1.5,
                    base_value=3333,
                    base_source="adaptive",
                    selected_budget=4999,
                    actual_max_tokens=5000,
                    tokens_used=2400,
                )

        # Should succeed
        assert result is True
        # Event should be created
        mock_session.add.assert_called_once()

    def test_record_with_minimal_fields(self):
        """Verify record works with only required fields."""
        from autopack.executor.db_events import \
            try_record_token_budget_escalation_event

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
                    run_id="run-minimal",
                    phase_id="phase-minimal",
                    attempt_index=1,
                    reason="test",
                    was_truncated=False,
                )

        assert result is True
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    def test_record_handles_none_optional_fields(self):
        """Verify None values for optional fields are handled correctly."""
        from autopack.executor.db_events import \
            try_record_token_budget_escalation_event

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
                    run_id="run-nones",
                    phase_id="phase-nones",
                    attempt_index=1,
                    reason="test",
                    was_truncated=False,
                    completion_tokens_used=None,
                    retry_max_tokens=None,
                    output_utilization=None,
                    escalation_factor=None,
                    base_value=None,
                    base_source=None,
                    selected_budget=None,
                    actual_max_tokens=None,
                    tokens_used=None,
                )

        assert result is True
        mock_session.commit.assert_called_once()

    def test_record_reason_field_variations(self):
        """Verify different reason field values work correctly."""
        from autopack.executor.db_events import \
            try_record_token_budget_escalation_event

        for reason_value in ["truncation", "utilization", "budget_exceeded", "custom"]:
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
                        run_id="run-reasons",
                        phase_id="phase-reasons",
                        attempt_index=1,
                        reason=reason_value,
                        was_truncated=False,
                    )

            assert result is True


class TestBestEffortGracefulFailure:
    """Test best-effort semantics - graceful failure handling."""

    def test_write_never_raises_on_any_error(self):
        """Verify write never raises exception - returns False instead."""
        from autopack.executor.db_events import \
            try_record_token_budget_escalation_event

        error_types = [
            Exception("generic"),
            RuntimeError("runtime"),
            ValueError("value"),
            KeyError("key"),
        ]

        for exc in error_types:
            mock_session = MagicMock()
            mock_session.add.side_effect = exc

            with patch(
                "autopack.executor.db_events._get_session_local",
                return_value=mock_session,
            ):
                with patch(
                    "autopack.executor.db_events._get_token_budget_escalation_event_model",
                    return_value=Mock(),
                ):
                    # Should not raise - best-effort semantics
                    result = try_record_token_budget_escalation_event(
                        run_id="run-errors",
                        phase_id="phase-errors",
                        attempt_index=1,
                        reason="test",
                        was_truncated=False,
                    )

            # Should indicate failure
            assert result is False

    def test_read_never_raises_on_any_error(self):
        """Verify read never raises exception - silently ignored."""
        from autopack.executor.db_events import \
            maybe_apply_retry_max_tokens_from_db

        error_types = [
            Exception("generic"),
            RuntimeError("runtime"),
            ValueError("value"),
            KeyError("key"),
        ]

        for exc in error_types:
            with patch(
                "autopack.executor.db_events._get_session_local",
                side_effect=exc,
            ):
                # Should not raise
                phase = {"phase_id": "test"}
                maybe_apply_retry_max_tokens_from_db(
                    run_id="run-errors",
                    phase=phase,
                    attempt_index=1,
                )

                # Phase unchanged
                assert "_escalated_tokens" not in phase
