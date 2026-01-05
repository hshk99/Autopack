"""
Tests for phase proof writer helper.

BUILD-161 Phase A: Intention-first loop integration.
"""

import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from autopack.config import settings
from autopack.phase_proof_writer import write_minimal_phase_proof
from autopack.phase_proof import PhaseProofStorage


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


def test_write_minimal_phase_proof_success(temp_run_dir):
    """Test writing a successful phase proof."""
    run_id = "test-run-success"
    project_id = "test-project"
    phase_id = "phase1"

    created_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    completed_at = datetime(2026, 1, 1, 12, 5, 30, tzinfo=timezone.utc)

    write_minimal_phase_proof(
        run_id=run_id,
        project_id=project_id,
        phase_id=phase_id,
        success=True,
        created_at=created_at,
        completed_at=completed_at,
        error_summary=None,
    )

    # Verify proof was written
    proof = PhaseProofStorage.load_proof(run_id, phase_id)
    assert proof is not None
    assert proof.run_id == run_id
    assert proof.phase_id == phase_id
    assert proof.success is True
    assert proof.duration_seconds == pytest.approx(330.0)  # 5 minutes 30 seconds
    assert proof.error_summary is None

    # Verify minimal placeholder values
    assert proof.changes.files_created == 0
    assert proof.changes.files_modified == 0
    assert proof.verification.tests_passed == 0


def test_write_minimal_phase_proof_failure(temp_run_dir):
    """Test writing a failed phase proof with error summary."""
    run_id = "test-run-failure"
    project_id = "test-project"
    phase_id = "phase2"

    created_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    completed_at = datetime(2026, 1, 1, 12, 2, 15, tzinfo=timezone.utc)

    write_minimal_phase_proof(
        run_id=run_id,
        project_id=project_id,
        phase_id=phase_id,
        success=False,
        created_at=created_at,
        completed_at=completed_at,
        error_summary="MAX_ATTEMPTS_EXHAUSTED: Builder failed 3 times",
    )

    # Verify proof was written
    proof = PhaseProofStorage.load_proof(run_id, phase_id)
    assert proof is not None
    assert proof.success is False
    assert proof.duration_seconds == pytest.approx(135.0)  # 2 minutes 15 seconds
    assert proof.error_summary == "MAX_ATTEMPTS_EXHAUSTED: Builder failed 3 times"


def test_write_minimal_phase_proof_truncates_long_error(temp_run_dir):
    """Test that error summaries longer than 500 chars are truncated."""
    run_id = "test-run-truncate"
    project_id = "test-project"
    phase_id = "phase3"

    created_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    completed_at = datetime(2026, 1, 1, 12, 1, 0, tzinfo=timezone.utc)

    long_error = "ERROR: " + "A" * 600  # 606 chars total

    write_minimal_phase_proof(
        run_id=run_id,
        project_id=project_id,
        phase_id=phase_id,
        success=False,
        created_at=created_at,
        completed_at=completed_at,
        error_summary=long_error,
    )

    # Verify error was truncated to 500 chars
    proof = PhaseProofStorage.load_proof(run_id, phase_id)
    assert proof is not None
    assert len(proof.error_summary) == 500
    assert proof.error_summary.startswith("ERROR: AAA")


def test_write_minimal_phase_proof_idempotent(temp_run_dir):
    """Test that writing proof twice overwrites (idempotent)."""
    run_id = "test-run-idempotent"
    project_id = "test-project"
    phase_id = "phase4"

    created_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    completed_at_1 = datetime(2026, 1, 1, 12, 1, 0, tzinfo=timezone.utc)
    completed_at_2 = datetime(2026, 1, 1, 12, 2, 0, tzinfo=timezone.utc)

    # Write proof first time
    write_minimal_phase_proof(
        run_id=run_id,
        project_id=project_id,
        phase_id=phase_id,
        success=False,
        created_at=created_at,
        completed_at=completed_at_1,
        error_summary="First attempt failed",
    )

    # Write proof second time (overwrite)
    write_minimal_phase_proof(
        run_id=run_id,
        project_id=project_id,
        phase_id=phase_id,
        success=True,
        created_at=created_at,
        completed_at=completed_at_2,
        error_summary=None,
    )

    # Verify latest proof is the second one
    proof = PhaseProofStorage.load_proof(run_id, phase_id)
    assert proof is not None
    assert proof.success is True
    assert proof.duration_seconds == pytest.approx(120.0)  # 2 minutes
    assert proof.error_summary is None
