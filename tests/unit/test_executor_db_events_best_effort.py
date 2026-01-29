"""Unit tests for executor.db_events module.

Tests for best-effort DB/telemetry operations that must never raise.
"""

from __future__ import annotations

import pytest

from autopack.executor.db_events import (
    maybe_apply_retry_max_tokens_from_db,
    try_record_token_budget_escalation_event)


class TestMaybeApplyRetryMaxTokensFromDb:
    """Tests for maybe_apply_retry_max_tokens_from_db."""

    def test_does_not_raise_when_db_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify function returns safely when DB is unavailable."""

        # Monkeypatch to simulate DB failure
        def raise_db_error():
            raise Exception("Database connection failed")

        monkeypatch.setattr(
            "autopack.executor.db_events._get_session_local",
            raise_db_error,
        )

        phase: dict = {"phase_id": "test-phase"}

        # Should not raise
        maybe_apply_retry_max_tokens_from_db(
            run_id="test-run",
            phase=phase,
            attempt_index=0,
        )

        # Phase should be unchanged
        assert "_escalated_tokens" not in phase

    def test_does_not_raise_when_query_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify function returns safely when query fails."""

        class FakeSession:
            def query(self, *args, **kwargs):
                raise Exception("Query failed")

            def close(self):
                pass

        def get_fake_session():
            return FakeSession()

        monkeypatch.setattr(
            "autopack.executor.db_events._get_session_local",
            get_fake_session,
        )

        phase: dict = {"phase_id": "test-phase"}

        # Should not raise
        maybe_apply_retry_max_tokens_from_db(
            run_id="test-run",
            phase=phase,
            attempt_index=1,
        )

        # Phase should be unchanged
        assert "_escalated_tokens" not in phase

    def test_does_not_raise_when_model_import_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify function returns safely when model import fails."""

        def raise_import_error():
            raise ImportError("autopack.models not found")

        monkeypatch.setattr(
            "autopack.executor.db_events._get_token_budget_escalation_event_model",
            raise_import_error,
        )

        phase: dict = {"phase_id": "test-phase"}

        # Should not raise
        maybe_apply_retry_max_tokens_from_db(
            run_id="test-run",
            phase=phase,
            attempt_index=0,
        )

        assert "_escalated_tokens" not in phase

    def test_does_not_modify_phase_when_no_event_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify phase is not modified when no escalation event exists."""

        class FakeQuery:
            def filter(self, *args):
                return self

            def order_by(self, *args):
                return self

            def first(self):
                return None  # No event found

        class FakeSession:
            def query(self, *args, **kwargs):
                return FakeQuery()

            def close(self):
                pass

        class FakeModel:
            run_id = None
            phase_id = None

            class timestamp:
                @staticmethod
                def desc():
                    return "desc"

        monkeypatch.setattr(
            "autopack.executor.db_events._get_session_local",
            lambda: FakeSession(),
        )
        monkeypatch.setattr(
            "autopack.executor.db_events._get_token_budget_escalation_event_model",
            lambda: FakeModel,
        )

        phase: dict = {"phase_id": "test-phase"}

        maybe_apply_retry_max_tokens_from_db(
            run_id="test-run",
            phase=phase,
            attempt_index=0,
        )

        assert "_escalated_tokens" not in phase


class TestTryRecordTokenBudgetEscalationEvent:
    """Tests for try_record_token_budget_escalation_event."""

    def test_does_not_raise_when_db_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify function returns safely when DB is unavailable."""

        def raise_db_error():
            raise Exception("Database connection failed")

        monkeypatch.setattr(
            "autopack.executor.db_events._get_session_local",
            raise_db_error,
        )

        # Should not raise
        result = try_record_token_budget_escalation_event(
            run_id="test-run",
            phase_id="test-phase",
            attempt_index=1,
            reason="truncation",
            was_truncated=True,
            completion_tokens_used=1000,
            retry_max_tokens=8000,
        )

        # Should return False to indicate failure
        assert result is False

    def test_does_not_raise_when_commit_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify function returns safely when commit fails."""
        commit_called = []

        class FakeSession:
            def add(self, obj):
                pass

            def commit(self):
                commit_called.append(True)
                raise Exception("Commit failed - disk full")

            def close(self):
                pass

        class FakeModel:
            def __init__(self, **kwargs):
                pass

        monkeypatch.setattr(
            "autopack.executor.db_events._get_session_local",
            lambda: FakeSession(),
        )
        monkeypatch.setattr(
            "autopack.executor.db_events._get_token_budget_escalation_event_model",
            lambda: FakeModel,
        )

        # Should not raise
        result = try_record_token_budget_escalation_event(
            run_id="test-run",
            phase_id="test-phase",
            attempt_index=1,
            reason="utilization",
            was_truncated=False,
            completion_tokens_used=2000,
            retry_max_tokens=16000,
        )

        assert result is False
        assert len(commit_called) == 1

    def test_does_not_raise_when_model_import_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify function returns safely when model import fails."""

        def raise_import_error():
            raise ImportError("autopack.models not found")

        monkeypatch.setattr(
            "autopack.executor.db_events._get_token_budget_escalation_event_model",
            raise_import_error,
        )

        # Should not raise
        result = try_record_token_budget_escalation_event(
            run_id="test-run",
            phase_id="test-phase",
            attempt_index=1,
            reason="truncation",
            was_truncated=True,
            completion_tokens_used=1000,
            retry_max_tokens=8000,
        )

        assert result is False

    def test_returns_true_on_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify function returns True on successful write."""
        added_objects = []
        committed = []

        class FakeSession:
            def add(self, obj):
                added_objects.append(obj)

            def commit(self):
                committed.append(True)

            def close(self):
                pass

        class FakeModel:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        monkeypatch.setattr(
            "autopack.executor.db_events._get_session_local",
            lambda: FakeSession(),
        )
        monkeypatch.setattr(
            "autopack.executor.db_events._get_token_budget_escalation_event_model",
            lambda: FakeModel,
        )

        result = try_record_token_budget_escalation_event(
            run_id="test-run",
            phase_id="test-phase",
            attempt_index=1,
            reason="truncation",
            was_truncated=True,
            completion_tokens_used=1000,
            retry_max_tokens=8000,
        )

        assert result is True
        assert len(added_objects) == 1
        assert len(committed) == 1
