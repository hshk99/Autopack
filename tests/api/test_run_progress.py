"""Tests for GET /runs/{run_id}/progress endpoint (GAP-8.10.4)

Verifies:
- Returns phase-by-phase progress
- Correct state counts
- Duration calculation
"""

from datetime import datetime, timedelta, timezone

import pytest

# Uses shared client, db_session fixtures from conftest.py


@pytest.fixture
def run_with_phases(client, db_session):
    """Create a run with phases in various states."""
    from autopack import models

    run_id = "test-run-progress"

    started_at = datetime.now(timezone.utc) - timedelta(hours=1)
    run = models.Run(
        id=run_id,
        state=models.RunState.PHASE_EXECUTION,
        safety_profile="normal",
        run_scope="multi_tier",
        token_cap=500_000,
        tokens_used=150_000,
        created_at=started_at - timedelta(minutes=5),
        started_at=started_at,
    )
    db_session.add(run)
    db_session.flush()

    # Create a tier
    tier = models.Tier(
        tier_id="T1",
        run_id=run.id,
        name="Main Tier",
        tier_index=0,
        state=models.TierState.IN_PROGRESS,
    )
    db_session.add(tier)
    db_session.flush()

    # Create phases in different states
    phases_data = [
        ("P1", "Setup", models.PhaseState.COMPLETE, 50_000, 1),
        ("P2", "Build", models.PhaseState.COMPLETE, 60_000, 2),
        ("P3", "Test", models.PhaseState.EXECUTING, 40_000, 1),
        ("P4", "Deploy", models.PhaseState.QUEUED, None, None),
        ("P5", "Cleanup", models.PhaseState.QUEUED, None, None),
    ]

    for i, (phase_id, name, state, tokens, attempts) in enumerate(phases_data):
        phase = models.Phase(
            phase_id=phase_id,
            run_id=run.id,
            tier_id=tier.id,
            name=name,
            phase_index=i,
            state=state,
            tokens_used=tokens,
            builder_attempts=attempts,
        )
        db_session.add(phase)

    db_session.commit()

    return run_id


class TestRunProgress:
    """Tests for GET /runs/{run_id}/progress endpoint."""

    def test_progress_run_not_found(self, client):
        """Returns 404 for non-existent run."""
        response = client.get("/runs/nonexistent/progress")
        assert response.status_code == 404

    def test_progress_basic_fields(self, client, run_with_phases):
        """Returns correct basic progress fields."""
        response = client.get(f"/runs/{run_with_phases}/progress")
        assert response.status_code == 200

        data = response.json()
        assert data["run_id"] == run_with_phases
        assert data["state"] == "PHASE_EXECUTION"
        assert data["tokens_used"] == 150_000
        assert data["token_cap"] == 500_000

    def test_progress_phase_counts(self, client, run_with_phases):
        """Returns correct phase state counts."""
        response = client.get(f"/runs/{run_with_phases}/progress")
        assert response.status_code == 200

        data = response.json()
        assert data["phases_total"] == 5
        assert data["phases_completed"] == 2
        assert data["phases_in_progress"] == 1
        assert data["phases_pending"] == 2

    def test_progress_phase_details(self, client, run_with_phases):
        """Returns detailed phase information."""
        response = client.get(f"/runs/{run_with_phases}/progress")
        assert response.status_code == 200

        data = response.json()
        assert len(data["phases"]) == 5

        # Check first phase
        p1 = next(p for p in data["phases"] if p["phase_id"] == "P1")
        assert p1["name"] == "Setup"
        assert p1["state"] == "COMPLETE"
        assert p1["tokens_used"] == 50_000
        assert p1["builder_attempts"] == 1
        assert p1["phase_index"] == 0

    def test_progress_elapsed_time(self, client, run_with_phases):
        """Returns elapsed time for running run."""
        response = client.get(f"/runs/{run_with_phases}/progress")
        assert response.status_code == 200

        data = response.json()
        assert data["started_at"] is not None
        assert data["elapsed_seconds"] is not None
        # Should be approximately 1 hour (3600 seconds) give or take
        assert 3500 <= data["elapsed_seconds"] <= 3700

    def test_progress_run_without_phases(self, client, db_session):
        """Returns empty phases list for run without phases."""
        from autopack import models

        run = models.Run(
            id="empty-run",
            state=models.RunState.RUN_CREATED,
            safety_profile="normal",
            run_scope="single_tier",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(run)
        db_session.commit()

        response = client.get("/runs/empty-run/progress")
        assert response.status_code == 200

        data = response.json()
        assert data["phases_total"] == 0
        assert data["phases"] == []
