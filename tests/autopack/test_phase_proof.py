"""
Tests for proof-carrying phase outputs.

Verifies phase proof persistence, bounded fields, and rendering.
"""

import shutil
from datetime import datetime
from pathlib import Path

import pytest

from autopack.phase_proof import (
    PhaseChange,
    PhaseProof,
    PhaseProofStorage,
    PhaseVerification,
    render_proof_as_markdown,
)


@pytest.fixture
def temp_run_dir(tmp_path):
    """Create temporary run directory."""
    run_dir = tmp_path / ".autonomous_runs" / "test-run"
    run_dir.mkdir(parents=True, exist_ok=True)
    yield run_dir
    # Cleanup
    shutil.rmtree(tmp_path / ".autonomous_runs", ignore_errors=True)


class TestPhaseVerification:
    """Test phase verification schema."""

    def test_verification_schema_validation(self):
        """Verification accepts valid data."""
        verification = PhaseVerification(
            tests_passed=5,
            tests_failed=0,
            probes_executed=["probe1", "probe2"],
            contracts_verified=["contract1"],
            verification_summary="All tests passed, contracts verified",
        )
        assert verification.tests_passed == 5
        assert len(verification.probes_executed) == 2

    def test_verification_summary_bounded(self):
        """Verification summary is bounded to 500 chars."""
        long_summary = "x" * 600
        with pytest.raises(ValueError):
            PhaseVerification(
                tests_passed=0,
                tests_failed=0,
                verification_summary=long_summary,
            )

    def test_verification_probes_bounded(self):
        """Probes list is bounded to 20 items."""
        too_many_probes = [f"probe{i}" for i in range(25)]
        with pytest.raises(ValueError):
            PhaseVerification(
                tests_passed=0,
                tests_failed=0,
                probes_executed=too_many_probes,
                verification_summary="Test",
            )

    def test_verification_contracts_bounded(self):
        """Contracts list is bounded to 20 items."""
        too_many_contracts = [f"contract{i}" for i in range(25)]
        with pytest.raises(ValueError):
            PhaseVerification(
                tests_passed=0,
                tests_failed=0,
                contracts_verified=too_many_contracts,
                verification_summary="Test",
            )


class TestPhaseChange:
    """Test phase change schema."""

    def test_change_schema_validation(self):
        """Change accepts valid data."""
        change = PhaseChange(
            files_created=3,
            files_modified=5,
            files_deleted=1,
            key_changes=["Added login feature", "Fixed bug in auth"],
            change_summary="Implemented authentication system",
        )
        assert change.files_created == 3
        assert len(change.key_changes) == 2

    def test_change_summary_bounded(self):
        """Change summary is bounded to 500 chars."""
        long_summary = "x" * 600
        with pytest.raises(ValueError):
            PhaseChange(
                files_created=0,
                files_modified=0,
                files_deleted=0,
                change_summary=long_summary,
            )

    def test_change_key_changes_bounded(self):
        """Key changes list is bounded to 10 items."""
        too_many_changes = [f"change{i}" for i in range(15)]
        with pytest.raises(ValueError):
            PhaseChange(
                files_created=0,
                files_modified=0,
                files_deleted=0,
                key_changes=too_many_changes,
                change_summary="Test",
            )


class TestPhaseProof:
    """Test phase proof schema."""

    def test_proof_schema_validation_success(self):
        """Proof accepts valid data for successful phase."""
        now = datetime.now()
        proof = PhaseProof(
            proof_id="proof-1",
            run_id="test-run",
            phase_id="phase-1",
            created_at=now,
            completed_at=now,
            duration_seconds=120.5,
            changes=PhaseChange(
                files_created=2,
                files_modified=3,
                files_deleted=0,
                change_summary="Added auth features",
            ),
            verification=PhaseVerification(
                tests_passed=10,
                tests_failed=0,
                verification_summary="All tests passed",
            ),
            success=True,
        )
        assert proof.success
        assert proof.error_summary is None

    def test_proof_schema_validation_failure(self):
        """Proof accepts valid data for failed phase."""
        now = datetime.now()
        proof = PhaseProof(
            proof_id="proof-1",
            run_id="test-run",
            phase_id="phase-1",
            created_at=now,
            completed_at=now,
            duration_seconds=60.0,
            changes=PhaseChange(
                files_created=0,
                files_modified=0,
                files_deleted=0,
                change_summary="No changes (phase failed)",
            ),
            verification=PhaseVerification(
                tests_passed=0,
                tests_failed=5,
                verification_summary="Tests failed",
            ),
            success=False,
            error_summary="Build errors encountered",
        )
        assert not proof.success
        assert proof.error_summary == "Build errors encountered"

    def test_proof_error_summary_bounded(self):
        """Error summary is bounded to 500 chars."""
        now = datetime.now()
        long_error = "x" * 600
        with pytest.raises(ValueError):
            PhaseProof(
                proof_id="proof-1",
                run_id="test-run",
                phase_id="phase-1",
                created_at=now,
                completed_at=now,
                duration_seconds=0,
                changes=PhaseChange(
                    files_created=0,
                    files_modified=0,
                    files_deleted=0,
                    change_summary="Test",
                ),
                verification=PhaseVerification(
                    tests_passed=0,
                    tests_failed=0,
                    verification_summary="Test",
                ),
                success=False,
                error_summary=long_error,
            )


class TestPhaseProofStorage:
    """Test phase proof persistence."""

    def test_save_and_load_proof(self, temp_run_dir, monkeypatch):
        """Roundtrip: save → load preserves all fields."""
        monkeypatch.chdir(temp_run_dir.parent.parent)

        now = datetime.now()
        proof = PhaseProof(
            proof_id="proof-1",
            run_id="test-run",
            phase_id="phase-1",
            created_at=now,
            completed_at=now,
            duration_seconds=100.0,
            changes=PhaseChange(
                files_created=1,
                files_modified=2,
                files_deleted=0,
                key_changes=["Added feature"],
                change_summary="Implemented feature",
            ),
            verification=PhaseVerification(
                tests_passed=5,
                tests_failed=0,
                probes_executed=["probe1"],
                contracts_verified=["contract1"],
                verification_summary="All verified",
            ),
            success=True,
        )

        PhaseProofStorage.save_proof(proof)
        loaded = PhaseProofStorage.load_proof("test-run", "phase-1")

        assert loaded is not None
        assert loaded.proof_id == proof.proof_id
        assert loaded.run_id == proof.run_id
        assert loaded.phase_id == proof.phase_id
        assert loaded.success == proof.success
        assert loaded.changes.files_created == 1
        assert loaded.verification.tests_passed == 5

    def test_load_nonexistent_proof(self):
        """Loading nonexistent proof returns None."""
        loaded = PhaseProofStorage.load_proof("nonexistent-run", "phase-1")
        assert loaded is None

    def test_list_proofs(self, temp_run_dir, monkeypatch):
        """List all proofs in a run."""
        monkeypatch.chdir(temp_run_dir.parent.parent)

        now = datetime.now()
        for i in range(3):
            proof = PhaseProof(
                proof_id=f"proof-{i}",
                run_id="test-run",
                phase_id=f"phase-{i}",
                created_at=now,
                completed_at=now,
                duration_seconds=10.0,
                changes=PhaseChange(
                    files_created=0,
                    files_modified=0,
                    files_deleted=0,
                    change_summary="Test",
                ),
                verification=PhaseVerification(
                    tests_passed=0,
                    tests_failed=0,
                    verification_summary="Test",
                ),
                success=True,
            )
            PhaseProofStorage.save_proof(proof)

        phase_ids = PhaseProofStorage.list_proofs("test-run")
        assert len(phase_ids) == 3
        assert "phase-0" in phase_ids
        assert "phase-1" in phase_ids
        assert "phase-2" in phase_ids

    def test_list_proofs_empty_run(self):
        """List proofs for run with no proofs returns empty list."""
        phase_ids = PhaseProofStorage.list_proofs("nonexistent-run")
        assert phase_ids == []


class TestRenderProofAsMarkdown:
    """Test proof markdown rendering."""

    def test_render_success_proof(self):
        """Render successful phase proof."""
        now = datetime.now()
        proof = PhaseProof(
            proof_id="proof-1",
            run_id="test-run",
            phase_id="phase-1",
            created_at=now,
            completed_at=now,
            duration_seconds=150.0,
            changes=PhaseChange(
                files_created=2,
                files_modified=3,
                files_deleted=1,
                key_changes=["Added login", "Fixed bug"],
                change_summary="Implemented authentication",
            ),
            verification=PhaseVerification(
                tests_passed=10,
                tests_failed=0,
                probes_executed=["auth_probe", "security_probe"],
                contracts_verified=["login_contract"],
                verification_summary="All tests and contracts verified",
            ),
            success=True,
        )

        md = render_proof_as_markdown(proof)

        assert "✅ SUCCESS" in md
        assert "phase-1" in md
        assert "150.0s" in md
        assert "Implemented authentication" in md
        assert "Files created: 2" in md
        assert "Added login" in md
        assert "Tests passed: 10" in md
        assert "auth_probe" in md
        assert "login_contract" in md

    def test_render_failure_proof(self):
        """Render failed phase proof."""
        now = datetime.now()
        proof = PhaseProof(
            proof_id="proof-1",
            run_id="test-run",
            phase_id="phase-1",
            created_at=now,
            completed_at=now,
            duration_seconds=30.0,
            changes=PhaseChange(
                files_created=0,
                files_modified=0,
                files_deleted=0,
                change_summary="No changes (failed early)",
            ),
            verification=PhaseVerification(
                tests_passed=0,
                tests_failed=3,
                verification_summary="Build failed",
            ),
            success=False,
            error_summary="Compilation errors in auth.py",
        )

        md = render_proof_as_markdown(proof)

        assert "❌ FAILED" in md
        assert "30.0s" in md
        assert "No changes (failed early)" in md
        assert "Tests failed: 3" in md
        assert "Compilation errors in auth.py" in md
