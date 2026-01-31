"""
Tests for guaranteed DB cleanup in Doctor integration (IMP-REL-011).

Verifies that database sessions are always closed, even when exceptions occur.
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from autopack.executor.doctor_integration import (DoctorIntegration,
                                                  DoctorResponse)


class MockSession:
    """Mock database session for testing."""

    def __init__(self):
        self.closed = False
        self.rolled_back = False
        self.committed = False

    def add(self, obj):
        pass

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True

    def query(self, model):
        return MagicMock()


@pytest.fixture
def doctor_integration():
    """Create DoctorIntegration instance."""
    return DoctorIntegration()


@pytest.fixture
def sample_doctor_response():
    """Create a sample Doctor response."""
    return DoctorResponse(
        action="retry_with_fix",
        rationale="Try a different approach",
        builder_hint="Review the error logs",
        confidence=0.8,
    )


def test_record_doctor_outcome_closes_session_on_success(
    doctor_integration, sample_doctor_response
):
    """Verify session is closed after successful record_doctor_outcome."""
    mock_session = MockSession()

    with patch("os.getenv") as mock_getenv:
        mock_getenv.return_value = "true"
        with patch("autopack.database.SessionLocal") as mock_session_local:
            mock_session_local.return_value = mock_session

            doctor_integration.record_doctor_outcome(
                run_id="run123",
                phase_id="phase1",
                error_category="test_error",
                builder_attempts=2,
                doctor_response=sample_doctor_response,
            )

    assert mock_session.closed, "Session should be closed after successful record"
    assert mock_session.committed, "Session should be committed"
    assert not mock_session.rolled_back, "Session should not be rolled back on success"


def test_record_doctor_outcome_closes_session_on_exception(
    doctor_integration, sample_doctor_response
):
    """Verify session is closed even when exception occurs during record_doctor_outcome."""
    mock_session = MockSession()
    mock_session.add = Mock(side_effect=RuntimeError("DB error"))

    with patch("os.getenv") as mock_getenv:
        mock_getenv.return_value = "true"
        with patch("autopack.database.SessionLocal") as mock_session_local:
            mock_session_local.return_value = mock_session

            doctor_integration.record_doctor_outcome(
                run_id="run123",
                phase_id="phase1",
                error_category="test_error",
                builder_attempts=2,
                doctor_response=sample_doctor_response,
            )

    assert mock_session.closed, "Session should be closed even on exception"
    assert mock_session.rolled_back, "Session should be rolled back on exception"
    assert not mock_session.committed, "Session should not be committed on exception"


def test_record_doctor_outcome_skipped_when_telemetry_disabled(
    doctor_integration, sample_doctor_response
):
    """Verify record_doctor_outcome skips DB access when telemetry is disabled."""
    with patch("os.getenv") as mock_getenv:
        mock_getenv.return_value = "false"
        with patch("autopack.database.SessionLocal") as mock_session_local:
            doctor_integration.record_doctor_outcome(
                run_id="run123",
                phase_id="phase1",
                error_category="test_error",
                builder_attempts=2,
                doctor_response=sample_doctor_response,
            )

    mock_session_local.assert_not_called()


def test_update_doctor_outcome_closes_session_on_success(doctor_integration):
    """Verify session is closed after successful update_doctor_outcome."""
    mock_session = MockSession()
    mock_query = MagicMock()
    mock_session.query = Mock(return_value=mock_query)

    # Mock the event
    mock_event = Mock()
    mock_event.phase_succeeded_after_doctor = None
    mock_query.filter.return_value.order_by.return_value.first.return_value = mock_event

    with patch("os.getenv") as mock_getenv:
        mock_getenv.return_value = "true"
        with patch("autopack.database.SessionLocal") as mock_session_local:
            mock_session_local.return_value = mock_session

            doctor_integration.update_doctor_outcome(
                run_id="run123",
                phase_id="phase1",
                phase_succeeded=True,
                final_outcome="COMPLETE",
                attempts_after_doctor=1,
            )

    assert mock_session.closed, "Session should be closed after successful update"
    assert mock_session.committed, "Session should be committed"
    assert not mock_session.rolled_back, "Session should not be rolled back on success"


def test_update_doctor_outcome_closes_session_on_exception(doctor_integration):
    """Verify session is closed even when exception occurs during update_doctor_outcome."""
    mock_session = MockSession()
    mock_session.query = Mock(side_effect=RuntimeError("DB query error"))

    with patch("os.getenv") as mock_getenv:
        mock_getenv.return_value = "true"
        with patch("autopack.database.SessionLocal") as mock_session_local:
            mock_session_local.return_value = mock_session

            doctor_integration.update_doctor_outcome(
                run_id="run123",
                phase_id="phase1",
                phase_succeeded=True,
                final_outcome="COMPLETE",
                attempts_after_doctor=1,
            )

    assert mock_session.closed, "Session should be closed even on exception"
    assert mock_session.rolled_back, "Session should be rolled back on exception"
    assert not mock_session.committed, "Session should not be committed on exception"


def test_update_doctor_outcome_skipped_when_telemetry_disabled(doctor_integration):
    """Verify update_doctor_outcome skips DB access when telemetry is disabled."""
    with patch("os.getenv") as mock_getenv:
        mock_getenv.return_value = "false"
        with patch("autopack.database.SessionLocal") as mock_session_local:
            doctor_integration.update_doctor_outcome(
                run_id="run123",
                phase_id="phase1",
                phase_succeeded=True,
                final_outcome="COMPLETE",
                attempts_after_doctor=1,
            )

    mock_session_local.assert_not_called()


def test_session_close_called_before_logging_in_record(doctor_integration, sample_doctor_response):
    """Verify that logging errors don't prevent session close in record_doctor_outcome."""
    mock_session = MockSession()
    close_order = []

    # Track call order
    original_close = mock_session.close
    mock_session.close = Mock(side_effect=lambda: (close_order.append("close"), original_close()))

    with patch("os.getenv") as mock_getenv:
        mock_getenv.return_value = "true"
        with patch("autopack.database.SessionLocal") as mock_session_local:
            mock_session_local.return_value = mock_session
            with patch("autopack.executor.doctor_integration.logger") as mock_logger:
                # Make logger.warning raise an exception
                mock_logger.warning = Mock(side_effect=Exception("Logger error"))

                # Should not raise even though logger raises
                doctor_integration.record_doctor_outcome(
                    run_id="run123",
                    phase_id="phase1",
                    error_category="test_error",
                    builder_attempts=2,
                    doctor_response=sample_doctor_response,
                )

    assert mock_session.closed, "Session should still be closed despite logger error"


def test_connection_exhaustion_prevention(doctor_integration):
    """Verify that connection pool is not exhausted by repeated failed calls."""
    mock_sessions = []
    for _ in range(5):
        mock_sessions.append(MockSession())

    session_index = [0]

    def get_mock_session():
        session = mock_sessions[session_index[0]]
        session_index[0] += 1
        return session

    with patch("os.getenv") as mock_getenv:
        mock_getenv.return_value = "true"
        with patch("autopack.database.SessionLocal") as mock_session_local:
            mock_session_local.side_effect = get_mock_session

            response = DoctorResponse(
                action="retry",
                rationale="Test",
                confidence=0.5,
            )

            # Make 5 failed calls
            for i in range(5):
                doctor_integration.record_doctor_outcome(
                    run_id=f"run{i}",
                    phase_id=f"phase{i}",
                    error_category="test_error",
                    builder_attempts=1,
                    doctor_response=response,
                )

    # Verify all sessions were properly closed
    for i, session in enumerate(mock_sessions):
        assert session.closed, f"Session {i} should be closed to prevent connection exhaustion"
