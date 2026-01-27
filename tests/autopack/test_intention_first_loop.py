"""
Tests for intention-first autonomy loop orchestrator.

Verifies orchestrator glue layer for stuck handling, scope reduction,
model escalation, and proof persistence.
"""

import shutil
from datetime import datetime

import pytest

from autopack.autonomous.intention_first_loop import (
    IntentionFirstLoop,
    PhaseLoopState,
    RunLoopState,
)
from autopack.config import settings
from autopack.intention_anchor.models import (
    IntentionAnchor,
    IntentionConstraints,
    IntentionRiskProfile,
)
from autopack.phase_proof import PhaseChange, PhaseProof, PhaseVerification
from autopack.scope_reduction import (
    ScopeReductionDiff,
    ScopeReductionProposal,
    ScopeReductionRationale,
)
from autopack.stuck_handling import (
    StuckHandlingPolicy,
    StuckReason,
    StuckResolutionDecision,
)


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
def sample_anchor():
    """Create sample IntentionAnchor for testing."""
    return IntentionAnchor(
        anchor_id="test-anchor",
        run_id="test-run",
        project_id="test-project",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        version=1,
        north_star="Build a login system",
        success_criteria=["Users can log in", "Passwords are hashed"],
        constraints=IntentionConstraints(
            must=["Use bcrypt for hashing"],
            preferences=["Use JWT tokens"],
            must_not=["Store passwords in plaintext"],
        ),
        risk_profile=IntentionRiskProfile(safety_profile="normal"),
    )


class TestPhaseLoopState:
    """Test PhaseLoopState dataclass."""

    def test_default_initialization(self):
        """PhaseLoopState initializes with zero/false defaults."""
        state = PhaseLoopState()
        assert state.iterations_used == 0
        assert state.consecutive_failures == 0
        assert state.replan_attempted is False
        assert state.escalations_used == 0

    def test_custom_initialization(self):
        """PhaseLoopState accepts custom values."""
        state = PhaseLoopState(
            iterations_used=2, consecutive_failures=1, replan_attempted=True, escalations_used=1
        )
        assert state.iterations_used == 2
        assert state.consecutive_failures == 1
        assert state.replan_attempted is True
        assert state.escalations_used == 1


class TestRunLoopState:
    """Test RunLoopState dataclass."""

    def test_initialization(self, temp_run_dir):
        """RunLoopState holds run identifiers and routing snapshot."""
        loop = IntentionFirstLoop()
        run_state = loop.on_run_start("test-run", "test-project")

        assert isinstance(run_state, RunLoopState)
        assert run_state.run_id == "test-run"
        assert run_state.project_id == "test-project"
        assert run_state.routing_snapshot is not None


class TestIntentionFirstLoop:
    """Test IntentionFirstLoop orchestrator."""

    def test_default_policy(self):
        """Loop uses default StuckHandlingPolicy if none provided."""
        loop = IntentionFirstLoop()
        assert isinstance(loop.policy, StuckHandlingPolicy)

    def test_custom_policy(self):
        """Loop accepts custom policy."""
        custom_policy = StuckHandlingPolicy(max_iterations_per_phase=5)
        loop = IntentionFirstLoop(policy=custom_policy)
        assert loop.policy.max_iterations_per_phase == 5

    def test_on_run_start_creates_run_state(self, temp_run_dir):
        """on_run_start creates RunLoopState with routing snapshot."""
        loop = IntentionFirstLoop()
        run_state = loop.on_run_start("test-run", "test-project")

        assert run_state.run_id == "test-run"
        assert run_state.project_id == "test-project"
        assert run_state.routing_snapshot is not None
        assert run_state.routing_snapshot.run_id == "test-run"

    def test_on_run_start_persists_snapshot(self, temp_run_dir):
        """on_run_start persists routing snapshot to disk."""
        loop = IntentionFirstLoop()
        loop.on_run_start("test-run", "test-project")

        # Verify snapshot file exists
        from autopack.model_routing_snapshot import RoutingSnapshotStorage

        snapshot_path = RoutingSnapshotStorage.get_snapshot_path("test-run")
        assert snapshot_path.exists()

    def test_decide_when_stuck_delegates_to_policy(self):
        """decide_when_stuck calls policy.decide with correct args."""
        loop = IntentionFirstLoop()
        phase_state = PhaseLoopState(iterations_used=1, consecutive_failures=2)

        decision = loop.decide_when_stuck(
            reason=StuckReason.REPEATED_FAILURES,
            phase_state=phase_state,
            budget_remaining=0.5,
        )

        # Should return REPLAN (before escalation, with budget remaining)
        assert decision == StuckResolutionDecision.REPLAN

    def test_escalate_model_increments_escalations_used(self, temp_run_dir):
        """escalate_model increments escalations_used when successful."""
        loop = IntentionFirstLoop()
        run_state = loop.on_run_start("test-run", "test-project")
        phase_state = PhaseLoopState()

        entry = loop.escalate_model(run_state, phase_state, "haiku", "normal")

        assert entry is not None
        assert entry.tier == "sonnet"  # Escalated from haiku
        assert phase_state.escalations_used == 1

    def test_escalate_model_respects_max_escalations(self, temp_run_dir):
        """escalate_model returns None when already at max tier."""
        loop = IntentionFirstLoop()
        run_state = loop.on_run_start("test-run", "test-project")
        phase_state = PhaseLoopState()

        # Escalate from opus (no higher tier)
        entry = loop.escalate_model(run_state, phase_state, "opus", "normal")

        assert entry is None
        assert phase_state.escalations_used == 0  # No increment when no escalation

    def test_build_scope_reduction_prompt(self, sample_anchor):
        """build_scope_reduction_prompt generates prompt grounded in anchor."""
        loop = IntentionFirstLoop()
        current_plan = {
            "deliverables": [
                {"id": "d1", "description": "Login form"},
                {"id": "d2", "description": "Password hashing"},
            ]
        }

        prompt = loop.build_scope_reduction_prompt(sample_anchor, current_plan, 0.3)

        assert "Build a login system" in prompt
        assert "Users can log in" in prompt
        assert "Use bcrypt for hashing" in prompt
        assert "30.0%" in prompt  # Uses .1% format

    def test_validate_scope_reduction_valid_proposal(self, sample_anchor):
        """validate_scope_reduction accepts valid proposal."""
        loop = IntentionFirstLoop()
        proposal = ScopeReductionProposal(
            run_id="test-run",
            phase_id="phase-1",
            anchor_id="test-anchor",
            diff=ScopeReductionDiff(
                original_deliverables=["d1", "d2"],
                kept_deliverables=["d1"],
                dropped_deliverables=["d2"],
                rationale=ScopeReductionRationale(
                    success_criteria_preserved=["Users can log in"],
                    success_criteria_deferred=["Passwords are hashed"],
                    constraints_still_met=["Use bcrypt for hashing"],
                    reason="Dropped password hashing UI to reduce scope",
                ),
            ),
            estimated_budget_savings=0.3,
        )

        is_valid, error = loop.validate_scope_reduction(proposal, sample_anchor)
        assert is_valid
        assert "Valid" in error

    def test_validate_scope_reduction_invalid_proposal(self, sample_anchor):
        """validate_scope_reduction rejects proposal with no criteria preserved."""
        loop = IntentionFirstLoop()
        proposal = ScopeReductionProposal(
            run_id="test-run",
            phase_id="phase-1",
            anchor_id="test-anchor",
            diff=ScopeReductionDiff(
                original_deliverables=["d1", "d2"],
                kept_deliverables=["d1"],
                dropped_deliverables=["d2"],
                rationale=ScopeReductionRationale(
                    success_criteria_preserved=[],  # No criteria preserved
                    success_criteria_deferred=["Users can log in"],
                    constraints_still_met=["Use bcrypt for hashing"],
                    reason="Dropped everything",
                ),
            ),
            estimated_budget_savings=0.3,
        )

        is_valid, error = loop.validate_scope_reduction(proposal, sample_anchor)
        assert not is_valid
        assert "at least one success criterion" in error.lower()

    def test_write_phase_proof_persists_artifact(self, temp_run_dir):
        """write_phase_proof saves proof to run-local artifact."""
        loop = IntentionFirstLoop()
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
                change_summary="Added feature",
            ),
            verification=PhaseVerification(
                tests_passed=5, tests_failed=0, verification_summary="All verified"
            ),
            success=True,
        )

        loop.write_phase_proof(proof)

        # Verify proof file exists
        from autopack.phase_proof import PhaseProofStorage

        proof_path = PhaseProofStorage.get_proof_path("test-run", "phase-1")
        assert proof_path.exists()

    def test_end_to_end_stuck_handling_flow(self, temp_run_dir):
        """End-to-end: run start → stuck decision → escalate → proof."""
        loop = IntentionFirstLoop()

        # 1. Run start
        run_state = loop.on_run_start("test-run", "test-project")
        phase_state = PhaseLoopState()

        # 2. First attempt fails
        phase_state.iterations_used = 1
        phase_state.consecutive_failures = 2  # Need >=2 for REPLAN

        # 3. Decide when stuck (should replan first)
        decision = loop.decide_when_stuck(
            reason=StuckReason.REPEATED_FAILURES,
            phase_state=phase_state,
            budget_remaining=0.8,
        )
        assert decision == StuckResolutionDecision.REPLAN
        phase_state.replan_attempted = True

        # 4. Replan fails, decide again (should escalate now)
        phase_state.iterations_used = 2
        phase_state.consecutive_failures = 2
        decision = loop.decide_when_stuck(
            reason=StuckReason.REPEATED_FAILURES,
            phase_state=phase_state,
            budget_remaining=0.7,
        )
        assert decision == StuckResolutionDecision.ESCALATE_MODEL

        # 5. Escalate model
        entry = loop.escalate_model(run_state, phase_state, "haiku", "normal")
        assert entry is not None
        assert entry.tier == "sonnet"
        assert phase_state.escalations_used == 1

        # 6. Write proof
        now = datetime.now()
        proof = PhaseProof(
            proof_id="proof-1",
            run_id="test-run",
            phase_id="phase-1",
            created_at=now,
            completed_at=now,
            duration_seconds=300.0,
            changes=PhaseChange(
                files_created=2,
                files_modified=3,
                files_deleted=0,
                change_summary="Completed after escalation",
            ),
            verification=PhaseVerification(
                tests_passed=10, tests_failed=0, verification_summary="All passed"
            ),
            success=True,
        )
        loop.write_phase_proof(proof)

        # Verify proof persisted
        from autopack.phase_proof import PhaseProofStorage

        loaded_proof = PhaseProofStorage.load_proof("test-run", "phase-1")
        assert loaded_proof is not None
        assert loaded_proof.success is True
