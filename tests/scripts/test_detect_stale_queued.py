"""Tests for stale QUEUED phase detection and remediation."""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Set DATABASE_URL before any imports
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from autopack.database import SessionLocal, engine
from autopack.models import Base, Phase, PhaseState, Run, Tier
from scripts.detect_stale_queued import (detect_stale_queued_phases,
                                         format_stale_report,
                                         mark_phase_as_failed)


@pytest.fixture(scope="function")
def test_db():
    """Create a temporary test database."""
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()

    # Create required parent objects
    run1 = Run(id="test-run-1")
    run2 = Run(id="test-run-2")
    session.add_all([run1, run2])

    tier1 = Tier(tier_id="T1", run_id="test-run-1", tier_index=0, name="Test", description="Test")
    tier2 = Tier(tier_id="T1", run_id="test-run-2", tier_index=0, name="Test", description="Test")
    session.add_all([tier1, tier2])
    session.commit()

    session.tier1_id = tier1.id
    session.tier2_id = tier2.id

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)


def test_detect_no_stale_phases_when_empty(test_db):
    """Test detection returns empty list when no queued phases exist."""
    stale = detect_stale_queued_phases(test_db, max_age_minutes=30)
    assert len(stale) == 0


def test_detect_no_stale_phases_when_all_fresh(test_db):
    """Test detection returns empty list when all queued phases are fresh."""
    now = datetime.now(timezone.utc)

    # Create fresh queued phase (just created)
    phase = Phase(
        run_id="test-run-1",
        phase_id="fresh-queued",
        name="Fresh Queued",
        tier_id=test_db.tier1_id,
        state=PhaseState.QUEUED,
        phase_index=0,
        created_at=now,
        updated_at=now,
    )
    test_db.add(phase)
    test_db.commit()

    stale = detect_stale_queued_phases(test_db, max_age_minutes=30)
    assert len(stale) == 0


def test_detect_stale_phase_based_on_age(test_db):
    """Test detection finds phase that has been queued too long."""
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(minutes=45)  # 45 minutes ago

    # Create stale queued phase
    phase = Phase(
        run_id="test-run-1",
        phase_id="stale-queued",
        name="Stale Queued",
        tier_id=test_db.tier1_id,
        state=PhaseState.QUEUED,
        phase_index=0,
        created_at=old_time,
        updated_at=old_time,
    )
    test_db.add(phase)
    test_db.commit()

    # Detect with 30 minute threshold - should find the 45-minute-old phase
    stale = detect_stale_queued_phases(test_db, max_age_minutes=30)

    assert len(stale) == 1
    assert stale[0][0].phase_id == "stale-queued"
    assert stale[0][1] == 45  # age in minutes


def test_detect_multiple_stale_phases(test_db):
    """Test detection finds multiple stale phases across runs."""
    now = datetime.now(timezone.utc)

    phases = [
        Phase(
            run_id="test-run-1",
            phase_id="stale-1",
            name="Stale 1",
            tier_id=test_db.tier1_id,
            state=PhaseState.QUEUED,
            phase_index=0,
            created_at=now - timedelta(minutes=60),
            updated_at=now - timedelta(minutes=60),
        ),
        Phase(
            run_id="test-run-1",
            phase_id="stale-2",
            name="Stale 2",
            tier_id=test_db.tier1_id,
            state=PhaseState.QUEUED,
            phase_index=1,
            created_at=now - timedelta(minutes=90),
            updated_at=now - timedelta(minutes=90),
        ),
        Phase(
            run_id="test-run-2",
            phase_id="stale-3",
            name="Stale 3",
            tier_id=test_db.tier2_id,
            state=PhaseState.QUEUED,
            phase_index=0,
            created_at=now - timedelta(minutes=120),
            updated_at=now - timedelta(minutes=120),
        ),
    ]

    test_db.add_all(phases)
    test_db.commit()

    stale = detect_stale_queued_phases(test_db, max_age_minutes=30)

    assert len(stale) == 3

    # Verify ages are correct
    ages = {p[0].phase_id: p[1] for p in stale}
    assert ages["stale-1"] == 60
    assert ages["stale-2"] == 90
    assert ages["stale-3"] == 120


def test_detect_respects_threshold(test_db):
    """Test that detection threshold works correctly."""
    now = datetime.now(timezone.utc)

    phases = [
        Phase(
            run_id="test-run-1",
            phase_id="just-under",
            name="Just Under",
            tier_id=test_db.tier1_id,
            state=PhaseState.QUEUED,
            phase_index=0,
            created_at=now - timedelta(minutes=29),
            updated_at=now - timedelta(minutes=29),
        ),
        Phase(
            run_id="test-run-1",
            phase_id="just-over",
            name="Just Over",
            tier_id=test_db.tier1_id,
            state=PhaseState.QUEUED,
            phase_index=1,
            created_at=now - timedelta(minutes=31),
            updated_at=now - timedelta(minutes=31),
        ),
    ]

    test_db.add_all(phases)
    test_db.commit()

    # 30 minute threshold should only catch the 31-minute-old phase
    stale = detect_stale_queued_phases(test_db, max_age_minutes=30)

    assert len(stale) == 1
    assert stale[0][0].phase_id == "just-over"


def test_detect_ignores_non_queued_phases(test_db):
    """Test that detection only considers QUEUED phases."""
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(minutes=60)

    # Create old phases in various states
    phases = [
        Phase(
            run_id="test-run-1",
            phase_id="old-queued",
            name="Old Queued",
            tier_id=test_db.tier1_id,
            state=PhaseState.QUEUED,
            phase_index=0,
            created_at=old_time,
            updated_at=old_time,
        ),
        Phase(
            run_id="test-run-1",
            phase_id="old-failed",
            name="Old Failed",
            tier_id=test_db.tier1_id,
            state=PhaseState.FAILED,
            phase_index=1,
            created_at=old_time,
            updated_at=old_time,
        ),
        Phase(
            run_id="test-run-1",
            phase_id="old-complete",
            name="Old Complete",
            tier_id=test_db.tier1_id,
            state=PhaseState.COMPLETE,
            phase_index=2,
            created_at=old_time,
            updated_at=old_time,
        ),
    ]

    test_db.add_all(phases)
    test_db.commit()

    stale = detect_stale_queued_phases(test_db, max_age_minutes=30)

    # Only the QUEUED phase should be detected
    assert len(stale) == 1
    assert stale[0][0].phase_id == "old-queued"


def test_mark_phase_as_failed(test_db):
    """Test marking a stale phase as FAILED."""
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(minutes=60)

    phase = Phase(
        run_id="test-run-1",
        phase_id="stale-queued",
        name="Stale Queued",
        tier_id=test_db.tier1_id,
        state=PhaseState.QUEUED,
        phase_index=0,
        created_at=old_time,
        updated_at=old_time,
    )
    test_db.add(phase)
    test_db.commit()

    # Mark as failed
    mark_phase_as_failed(test_db, phase, "Phase queued for 60 minutes with no progress")

    # Verify state changed
    test_db.refresh(phase)
    assert phase.state == PhaseState.FAILED
    assert "[STALE-QUEUED]" in phase.last_failure_reason
    assert "60 minutes" in phase.last_failure_reason


def test_mark_phase_preserves_original_error(test_db):
    """Test that marking as failed preserves original failure reason."""
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(minutes=60)

    original_failure = "API timeout error"

    phase = Phase(
        run_id="test-run-1",
        phase_id="stale-queued",
        name="Stale Queued",
        tier_id=test_db.tier1_id,
        state=PhaseState.QUEUED,
        phase_index=0,
        created_at=old_time,
        updated_at=old_time,
        last_failure_reason=original_failure,
    )
    test_db.add(phase)
    test_db.commit()

    mark_phase_as_failed(test_db, phase, "Phase queued for 60 minutes with no progress")

    test_db.refresh(phase)
    assert "[STALE-QUEUED]" in phase.last_failure_reason
    assert original_failure in phase.last_failure_reason


def test_format_stale_report_empty(test_db):
    """Test report formatting with no stale phases."""
    report = format_stale_report([])
    assert "No stale QUEUED phases detected" in report


def test_format_stale_report_with_phases(test_db):
    """Test report formatting with stale phases."""
    now = datetime.now(timezone.utc)

    phase1 = Phase(
        run_id="test-run-1",
        phase_id="stale-1",
        name="Stale 1",
        tier_id=test_db.tier1_id,
        state=PhaseState.QUEUED,
        phase_index=0,
        created_at=now,
        updated_at=now,
    )
    phase2 = Phase(
        run_id="test-run-2",
        phase_id="stale-2",
        name="Stale 2",
        tier_id=test_db.tier2_id,
        state=PhaseState.QUEUED,
        phase_index=0,
        created_at=now,
        updated_at=now,
    )

    stale_phases = [
        (phase1, 60),  # 1 hour
        (phase2, 150),  # 2 hours 30 minutes
    ]

    report = format_stale_report(stale_phases)

    # Check report contains key information
    assert "STALE QUEUED PHASES DETECTED: 2" in report
    assert "test-run-1" in report
    assert "test-run-2" in report
    assert "stale-1" in report
    assert "stale-2" in report
    assert "1h 0m" in report  # 60 minutes formatted
    assert "2h 30m" in report  # 150 minutes formatted


def test_detect_uses_updated_at_if_available(test_db):
    """Test that detection uses updated_at timestamp when available."""
    now = datetime.now(timezone.utc)

    # Created long ago but updated recently
    phase = Phase(
        run_id="test-run-1",
        phase_id="recently-updated",
        name="Recently Updated",
        tier_id=test_db.tier1_id,
        state=PhaseState.QUEUED,
        phase_index=0,
        created_at=now - timedelta(hours=24),  # Created 24 hours ago
        updated_at=now - timedelta(minutes=10),  # Updated 10 minutes ago
    )
    test_db.add(phase)
    test_db.commit()

    # Should not be detected as stale (updated 10 minutes ago < 30 minute threshold)
    stale = detect_stale_queued_phases(test_db, max_age_minutes=30)
    assert len(stale) == 0


def test_detect_handles_naive_timestamps(test_db):
    """Test that detection handles timezone-naive timestamps correctly."""
    now_utc = datetime.now(timezone.utc)
    old_naive = now_utc.replace(tzinfo=None) - timedelta(minutes=60)  # Naive timestamp, 60 mins ago

    phase = Phase(
        run_id="test-run-1",
        phase_id="naive-timestamp",
        name="Naive Timestamp",
        tier_id=test_db.tier1_id,
        state=PhaseState.QUEUED,
        phase_index=0,
        created_at=old_naive,
        updated_at=old_naive,
    )
    test_db.add(phase)
    test_db.commit()

    # Should handle naive timestamp by assuming UTC
    stale = detect_stale_queued_phases(test_db, max_age_minutes=30)
    assert len(stale) == 1
