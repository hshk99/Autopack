"""
Integration tests for phase proof writing in autonomous_executor.

BUILD-161 Phase A: Verifies executor wiring for phase proof emission.
BUILD-189: Isolated git metrics to prevent CI workspace pollution.

Tests the actual executor hooks (_mark_phase_complete_in_db, _mark_phase_failed_in_db)
to ensure phase proofs are written correctly when intention-first loop is active.
"""

import shutil
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from autopack.config import settings
from autopack.autonomous_executor import AutonomousExecutor
from autopack.phase_proof import PhaseProofStorage
from autopack.proof_metrics import ProofMetrics


@pytest.fixture
def temp_run_dir(tmp_path):
    """Create temporary autonomous_runs root dir and point Settings at it."""
    runs_root = tmp_path / ".autonomous_runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    old = settings.autonomous_runs_dir
    settings.autonomous_runs_dir = str(runs_root)
    try:
        yield runs_root
    finally:
        settings.autonomous_runs_dir = old
        shutil.rmtree(runs_root, ignore_errors=True)


@pytest.fixture
def mock_clean_git_metrics():
    """Mock git metrics to return clean workspace (no uncommitted changes).

    BUILD-189: Prevents CI workspace pollution from affecting phase proof tests.
    The CI environment may have uncommitted files from doc generation, etc.
    """
    clean_metrics = ProofMetrics(
        files_modified=0,
        changed_file_sample=[],
        metrics_placeholder=True,  # Indicate these are test placeholders
    )
    with patch("autopack.phase_proof_writer.get_proof_metrics", return_value=clean_metrics):
        yield clean_metrics


@pytest.fixture
def mock_executor(tmp_path, temp_run_dir):
    """Create a minimal mock executor for testing phase proof writing."""
    # Create a lightweight mock executor without full initialization
    executor = Mock(spec=AutonomousExecutor)
    # Use properly formatted run_id with project prefix for RunFileLayout auto-detection
    executor.run_id = "test-project-proof-integration"
    executor.project_id = "test-project"
    executor.db_session = Mock()

    # Bind the real methods we're testing (unmock them)
    executor._mark_phase_complete_in_db = AutonomousExecutor._mark_phase_complete_in_db.__get__(
        executor, AutonomousExecutor
    )
    executor._mark_phase_failed_in_db = AutonomousExecutor._mark_phase_failed_in_db.__get__(
        executor, AutonomousExecutor
    )

    # Mock telemetry/notification methods to prevent side effects
    executor._record_token_efficiency_telemetry = Mock()
    executor._send_phase_failure_notification = Mock()

    return executor


def test_phase_proof_written_on_success_when_wiring_active(
    mock_executor, temp_run_dir, mock_clean_git_metrics
):
    """
    SUCCESS PATH: When intention wiring is active and phase completes successfully,
    a phase proof file is written with success=True.
    """
    phase_id = "test-phase-success"

    # Mock database phase object
    mock_phase = Mock()
    mock_phase.phase_id = phase_id
    mock_phase.created_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    mock_phase.completed_at = None  # Will be set by executor

    mock_db = Mock()
    mock_query = mock_db.query.return_value
    mock_filter = mock_query.filter.return_value
    mock_filter.first.return_value = mock_phase

    # Set up intention wiring (active)
    mock_executor._intention_wiring = Mock()
    mock_executor.project_id = "test-project"

    with patch("autopack.database.SessionLocal", return_value=mock_db):
        # Call the method under test
        result = mock_executor._mark_phase_complete_in_db(phase_id)

    assert result is True

    # Verify phase proof was written
    proof = PhaseProofStorage.load_proof(mock_executor.run_id, phase_id)
    assert proof is not None, "Phase proof should be written when intention wiring is active"
    assert proof.run_id == mock_executor.run_id
    assert proof.phase_id == phase_id
    assert proof.success is True
    assert proof.error_summary is None

    # Verify placeholder metrics (mocked clean workspace)
    assert proof.changes.files_created == 0
    assert proof.changes.files_modified == 0
    assert proof.verification.tests_passed == 0


def test_phase_proof_written_on_failure_when_wiring_active(mock_executor, temp_run_dir):
    """
    FAILURE PATH: When intention wiring is active and phase fails,
    a phase proof file is written with success=False and error_summary.
    """
    phase_id = "test-phase-failure"
    failure_reason = "MAX_ATTEMPTS_EXHAUSTED: Builder failed 3 times"

    # Mock database phase object
    mock_phase = Mock()
    mock_phase.phase_id = phase_id
    mock_phase.created_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    mock_phase.completed_at = None  # Will be set by executor
    mock_phase.last_failure_reason = None

    mock_db = Mock()
    mock_query = mock_db.query.return_value
    mock_filter = mock_query.filter.return_value
    mock_filter.first.return_value = mock_phase

    # Set up intention wiring (active)
    mock_executor._intention_wiring = Mock()
    mock_executor.project_id = "test-project"

    with (
        patch("autopack.database.SessionLocal", return_value=mock_db),
        patch.object(mock_executor, "_record_token_efficiency_telemetry"),
        patch.object(mock_executor, "_send_phase_failure_notification"),
    ):
        # Call the method under test
        result = mock_executor._mark_phase_failed_in_db(phase_id, failure_reason)

    assert result is True

    # Verify phase proof was written
    proof = PhaseProofStorage.load_proof(mock_executor.run_id, phase_id)
    assert proof is not None, "Phase proof should be written when intention wiring is active"
    assert proof.run_id == mock_executor.run_id
    assert proof.phase_id == phase_id
    assert proof.success is False
    assert proof.error_summary == failure_reason

    # Verify bounded error (max 500 chars)
    assert len(proof.error_summary) <= 500


def test_no_phase_proof_when_wiring_inactive(mock_executor, temp_run_dir):
    """
    NO-OP PATH: When intention wiring is NOT active, no phase proof is written.
    """
    phase_id = "test-phase-no-wiring"

    # Mock database phase object
    mock_phase = Mock()
    mock_phase.phase_id = phase_id
    mock_phase.created_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    mock_phase.completed_at = None

    mock_db = Mock()
    mock_query = mock_db.query.return_value
    mock_filter = mock_query.filter.return_value
    mock_filter.first.return_value = mock_phase

    # Ensure intention wiring is NOT active
    mock_executor._intention_wiring = None
    mock_executor.project_id = "test-project"

    with patch("autopack.database.SessionLocal", return_value=mock_db):
        # Call the method under test
        result = mock_executor._mark_phase_complete_in_db(phase_id)

    assert result is True

    # Verify NO phase proof was written
    proof = PhaseProofStorage.load_proof(mock_executor.run_id, phase_id)
    assert proof is None, "Phase proof should NOT be written when intention wiring is inactive"


def test_phase_proof_idempotence_on_completion(mock_executor, temp_run_dir):
    """
    IDEMPOTENCE: Calling _mark_phase_complete_in_db twice doesn't corrupt or duplicate.
    The second call should overwrite the first proof (atomic replace).
    """
    phase_id = "test-phase-idempotent"

    # Mock database phase object
    mock_phase = Mock()
    mock_phase.phase_id = phase_id
    mock_phase.created_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    mock_phase.completed_at = None

    mock_db = Mock()
    mock_query = mock_db.query.return_value
    mock_filter = mock_query.filter.return_value
    mock_filter.first.return_value = mock_phase

    # Set up intention wiring (active)
    mock_executor._intention_wiring = Mock()
    mock_executor.project_id = "test-project"

    with patch("autopack.database.SessionLocal", return_value=mock_db):
        # Call the method under test TWICE
        result1 = mock_executor._mark_phase_complete_in_db(phase_id)

        # Reset completed_at for second call (simulating re-mark)
        mock_phase.completed_at = None

        result2 = mock_executor._mark_phase_complete_in_db(phase_id)

    assert result1 is True
    assert result2 is True

    # Verify only ONE phase proof exists (not duplicated)
    # Don't pass explicit project_id - let it auto-detect from run_id (same as save_proof)
    proof_path = PhaseProofStorage.get_proof_path(mock_executor.run_id, phase_id)
    assert proof_path.exists(), "Phase proof should exist"

    # Verify proof is loadable and valid
    proof = PhaseProofStorage.load_proof(mock_executor.run_id, phase_id)
    assert proof is not None
    assert proof.success is True

    # Verify no duplicate files were created
    proof_dir = PhaseProofStorage.get_proof_dir(mock_executor.run_id)
    proof_files = list(proof_dir.glob(f"{phase_id}*.json"))
    assert len(proof_files) == 1, "Should have exactly one proof file (no duplicates)"


def test_phase_proof_failure_is_non_fatal(mock_executor, temp_run_dir, caplog):
    """
    ROBUSTNESS: If phase proof writing fails (e.g., disk full, permission error),
    it should not fail the phase completion. Should log warning instead.
    """
    phase_id = "test-phase-proof-error"

    # Mock database phase object
    mock_phase = Mock()
    mock_phase.phase_id = phase_id
    mock_phase.created_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    mock_phase.completed_at = None

    mock_db = Mock()
    mock_query = mock_db.query.return_value
    mock_filter = mock_query.filter.return_value
    mock_filter.first.return_value = mock_phase

    # Set up intention wiring (active)
    mock_executor._intention_wiring = Mock()
    mock_executor.project_id = "test-project"

    # Patch write_minimal_phase_proof to raise an exception
    with (
        patch("autopack.database.SessionLocal", return_value=mock_db),
        patch(
            "autopack.phase_proof_writer.write_minimal_phase_proof",
            side_effect=Exception("Simulated disk full error"),
        ),
    ):
        # Call the method under test - should NOT raise exception
        result = mock_executor._mark_phase_complete_in_db(phase_id)

    # Phase completion should still succeed
    assert result is True

    # Verify warning was logged
    assert any(
        "Failed to write phase proof (non-fatal)" in record.message for record in caplog.records
    ), "Should log warning when proof writing fails"


def test_phase_proof_error_summary_truncation(mock_executor, temp_run_dir):
    """
    BOUNDED: Error summaries longer than 500 chars are truncated by the writer.
    """
    phase_id = "test-phase-long-error"
    long_error = "ERROR: " + "A" * 600  # 606 chars total

    # Mock database phase object
    mock_phase = Mock()
    mock_phase.phase_id = phase_id
    mock_phase.created_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    mock_phase.completed_at = None
    mock_phase.last_failure_reason = long_error

    mock_db = Mock()
    mock_query = mock_db.query.return_value
    mock_filter = mock_query.filter.return_value
    mock_filter.first.return_value = mock_phase

    # Set up intention wiring (active)
    mock_executor._intention_wiring = Mock()
    mock_executor.project_id = "test-project"

    with (
        patch("autopack.database.SessionLocal", return_value=mock_db),
        patch.object(mock_executor, "_record_token_efficiency_telemetry"),
        patch.object(mock_executor, "_send_phase_failure_notification"),
    ):
        # Call the method under test
        result = mock_executor._mark_phase_failed_in_db(phase_id, long_error)

    assert result is True

    # Verify error was truncated to 500 chars
    proof = PhaseProofStorage.load_proof(mock_executor.run_id, phase_id)
    assert proof is not None
    assert len(proof.error_summary) == 500, "Error summary should be truncated to 500 chars"
    assert proof.error_summary.startswith("ERROR: AAA")
