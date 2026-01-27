"""
Regression test for BUILD-132: skip_runs_with_queued design flaw fix.

Tests that batch_drain_controller:
1. Does NOT skip entire runs that have queued phases
2. DOES skip individual queued phases
3. CAN drain FAILED phases from runs with QUEUED phases

This prevents the "1 queued blocks 5 failed" scenario.
"""

import os
import sys
from pathlib import Path

import pytest

# Set DATABASE_URL before any imports
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from autopack.database import SessionLocal, engine
from autopack.models import Base, Phase, PhaseState, Run, Tier
from scripts.batch_drain_controller import BatchDrainController


@pytest.fixture(scope="function")
def test_db():
    """Create a temporary test database."""
    # Create all tables
    Base.metadata.create_all(bind=engine)

    # Create session
    session = SessionLocal()

    # Create required parent objects (runs and tiers)
    run1 = Run(id="run1")
    run2 = Run(id="run2")
    run_v3 = Run(id="research-system-v3")
    run_v6 = Run(id="research-system-v6")
    session.add_all([run1, run2, run_v3, run_v6])

    tier1 = Tier(tier_id="T1", run_id="run1", tier_index=0, name="Test Tier", description="Test")
    tier2 = Tier(tier_id="T1", run_id="run2", tier_index=0, name="Test Tier", description="Test")
    tier_v3 = Tier(
        tier_id="T1",
        run_id="research-system-v3",
        tier_index=0,
        name="Test Tier",
        description="Test",
    )
    tier_v6 = Tier(
        tier_id="T1",
        run_id="research-system-v6",
        tier_index=0,
        name="Test Tier",
        description="Test",
    )
    session.add_all([tier1, tier2, tier_v3, tier_v6])
    session.commit()

    # Store tier IDs for tests to use
    session.tier1_id = tier1.id
    session.tier2_id = tier2.id
    session.tier_v3_id = tier_v3.id
    session.tier_v6_id = tier_v6.id

    yield session

    # Cleanup
    session.close()
    Base.metadata.drop_all(bind=engine)


def test_skip_individual_queued_phases_not_entire_runs(test_db, tmp_path):
    """
    Regression test for the skip_runs_with_queued design flaw.

    Scenario:
    - run1 has 1 QUEUED phase and 5 FAILED phases
    - run2 has 3 FAILED phases (no QUEUED)

    OLD BEHAVIOR (bug):
    - Skips all 8 failed phases (entire run1 skipped because it has 1 queued)
    - Only drains run2's 3 failed phases

    NEW BEHAVIOR (fixed):
    - Skips only the 1 specific QUEUED phase
    - Drains run1's 5 FAILED phases + run2's 3 FAILED phases = 8 total
    """
    # Setup: Create test phases
    run1_phases = [
        Phase(
            run_id="run1",
            phase_id="phase-queued",
            name="Queued Phase",
            tier_id=test_db.tier1_id,
            state=PhaseState.QUEUED,
            phase_index=0,
        ),
        Phase(
            run_id="run1",
            phase_id="phase-failed-1",
            name="Failed 1",
            tier_id=test_db.tier1_id,
            state=PhaseState.FAILED,
            phase_index=1,
        ),
        Phase(
            run_id="run1",
            phase_id="phase-failed-2",
            name="Failed 2",
            tier_id=test_db.tier1_id,
            state=PhaseState.FAILED,
            phase_index=2,
        ),
        Phase(
            run_id="run1",
            phase_id="phase-failed-3",
            name="Failed 3",
            tier_id=test_db.tier1_id,
            state=PhaseState.FAILED,
            phase_index=3,
        ),
        Phase(
            run_id="run1",
            phase_id="phase-failed-4",
            name="Failed 4",
            tier_id=test_db.tier1_id,
            state=PhaseState.FAILED,
            phase_index=4,
        ),
        Phase(
            run_id="run1",
            phase_id="phase-failed-5",
            name="Failed 5",
            tier_id=test_db.tier1_id,
            state=PhaseState.FAILED,
            phase_index=5,
        ),
    ]

    run2_phases = [
        Phase(
            run_id="run2",
            phase_id="phase-failed-6",
            name="Failed 6",
            tier_id=test_db.tier2_id,
            state=PhaseState.FAILED,
            phase_index=0,
        ),
        Phase(
            run_id="run2",
            phase_id="phase-failed-7",
            name="Failed 7",
            tier_id=test_db.tier2_id,
            state=PhaseState.FAILED,
            phase_index=1,
        ),
        Phase(
            run_id="run2",
            phase_id="phase-failed-8",
            name="Failed 8",
            tier_id=test_db.tier2_id,
            state=PhaseState.FAILED,
            phase_index=2,
        ),
    ]

    test_db.add_all(run1_phases + run2_phases)
    test_db.commit()

    # Create controller with skip_runs_with_queued=True (default)
    controller = BatchDrainController(
        workspace=tmp_path,
        dry_run=True,
        skip_runs_with_queued=True,  # This is the safety default
    )

    # Pick next failed phase - should work for run1 despite having a queued phase
    phase = controller.pick_next_failed_phase(test_db)

    # Assert: Should get a FAILED phase (from either run), not skip run1 entirely
    assert phase is not None, "Should find a failed phase even though run1 has queued phases"
    assert phase.state == PhaseState.FAILED, "Should pick a FAILED phase"
    assert phase.phase_id != "phase-queued", "Should not pick the QUEUED phase"

    # Note: Controller may pick from run2 first (smart prioritization), that's OK.
    # The key is that run1 phases should be available when we iterate through all picks.

    # Verify we can pick all 8 failed phases (5 from run1 + 3 from run2)
    picked_phases = []
    exclude_keys = []

    for _ in range(10):  # Try to pick up to 10 (more than we have)
        phase = controller.pick_next_failed_phase(test_db, exclude_keys=exclude_keys)
        if phase is None:
            break
        picked_phases.append(phase)
        exclude_keys.append(f"{phase.run_id}:{phase.phase_id}")

    # Assert: Should have picked all 8 FAILED phases
    assert len(picked_phases) == 8, f"Should pick all 8 FAILED phases, got {len(picked_phases)}"

    # Assert: Should have picked 5 from run1 and 3 from run2
    run1_picked = [p for p in picked_phases if p.run_id == "run1"]
    run2_picked = [p for p in picked_phases if p.run_id == "run2"]

    assert len(run1_picked) == 5, f"Should pick 5 FAILED phases from run1, got {len(run1_picked)}"
    assert len(run2_picked) == 3, f"Should pick 3 FAILED phases from run2, got {len(run2_picked)}"

    # Assert: Should NOT have picked the QUEUED phase
    queued_picked = [p for p in picked_phases if p.phase_id == "phase-queued"]
    assert len(queued_picked) == 0, "Should not pick the QUEUED phase"


def test_skip_entire_runs_can_be_disabled(test_db, tmp_path):
    """
    Test that skip_runs_with_queued=False allows draining any FAILED phase.
    """
    # Setup: Same scenario as above
    run1_phases = [
        Phase(
            run_id="run1",
            phase_id="phase-queued",
            name="Queued",
            tier_id=test_db.tier1_id,
            state=PhaseState.QUEUED,
            phase_index=0,
        ),
        Phase(
            run_id="run1",
            phase_id="phase-failed-1",
            name="Failed",
            tier_id=test_db.tier1_id,
            state=PhaseState.FAILED,
            phase_index=1,
        ),
    ]

    test_db.add_all(run1_phases)
    test_db.commit()

    # Create controller with skip_runs_with_queued=False
    controller = BatchDrainController(
        workspace=tmp_path,
        dry_run=True,
        skip_runs_with_queued=False,  # Disabled
    )

    # Should be able to pick FAILED phase even with QUEUED present
    phase = controller.pick_next_failed_phase(test_db)
    assert phase is not None
    assert phase.state == PhaseState.FAILED


def test_old_bug_scenario_exact_reproduction(test_db, tmp_path):
    """
    Exact reproduction of the reported bug:
    - research-system-v3 has 1 QUEUED + 6 FAILED
    - research-system-v6 has 1 QUEUED + 7 FAILED

    OLD BUG: Entire runs skipped, blocking 13 FAILED phases from draining
    NEW FIX: All 13 FAILED phases can be drained
    """
    # Reproduce exact scenario from snapshot
    v3_phases = [
        Phase(
            run_id="research-system-v3",
            phase_id="research-gatherers-social",
            name="Research Gatherers Social",
            tier_id=test_db.tier_v3_id,
            state=PhaseState.QUEUED,
            phase_index=0,
        ),
    ] + [
        Phase(
            run_id="research-system-v3",
            phase_id=f"failed-{i}",
            name=f"Failed {i}",
            tier_id=test_db.tier_v3_id,
            state=PhaseState.FAILED,
            phase_index=i + 1,
        )
        for i in range(6)
    ]

    v6_phases = [
        Phase(
            run_id="research-system-v6",
            phase_id="research-foundation-orchestrator",
            name="Research Foundation Orchestrator",
            tier_id=test_db.tier_v6_id,
            state=PhaseState.QUEUED,
            phase_index=0,
        ),
    ] + [
        Phase(
            run_id="research-system-v6",
            phase_id=f"failed-{i}",
            name=f"Failed {i}",
            tier_id=test_db.tier_v6_id,
            state=PhaseState.FAILED,
            phase_index=i + 1,
        )
        for i in range(7)
    ]

    test_db.add_all(v3_phases + v6_phases)
    test_db.commit()

    controller = BatchDrainController(
        workspace=tmp_path,
        dry_run=True,
        skip_runs_with_queued=True,
    )

    # Try to pick all failed phases
    picked = []
    exclude_keys = []

    for _ in range(20):  # Try to pick up to 20
        phase = controller.pick_next_failed_phase(test_db, exclude_keys=exclude_keys)
        if phase is None:
            break
        picked.append(phase)
        exclude_keys.append(f"{phase.run_id}:{phase.phase_id}")

    # With fix: should pick all 13 FAILED phases (6 from v3 + 7 from v6)
    assert len(picked) == 13, f"Should pick all 13 FAILED phases, got {len(picked)}"

    v3_picked = [p for p in picked if p.run_id == "research-system-v3"]
    v6_picked = [p for p in picked if p.run_id == "research-system-v6"]

    assert len(v3_picked) == 6, f"Should pick 6 from v3, got {len(v3_picked)}"
    assert len(v6_picked) == 7, f"Should pick 7 from v6, got {len(v6_picked)}"
