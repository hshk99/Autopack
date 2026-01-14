"""Tests for GET /runs endpoint (GAP-8.10.2 Runs Inbox)

Verifies:
- Returns 200 + list of runs
- Respects limit/offset pagination
- Returns correct summary fields
"""

import pytest
from datetime import datetime, timezone

# Uses shared client fixture from conftest.py


@pytest.fixture
def populated_db(client, db_session):
    """Populate database with test runs."""
    from autopack import models

    # Create test runs
    for i in range(5):
        run = models.Run(
            id=f"test-run-{i:03d}",
            state=models.RunState.DONE_SUCCESS if i < 3 else models.RunState.PHASE_EXECUTION,
            safety_profile="normal",
            run_scope="multi_tier",
            token_cap=1_000_000,
            tokens_used=100_000 * (i + 1),
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(run)

        # Add some phases for the first run
        if i == 0:
            tier = models.Tier(
                tier_id="T1",
                run_id=run.id,
                name="Test Tier",
                tier_index=0,
                state=models.TierState.COMPLETE,
            )
            db_session.add(tier)
            db_session.flush()

            for j in range(3):
                phase = models.Phase(
                    phase_id=f"P{j + 1}",
                    run_id=run.id,
                    tier_id=tier.id,
                    name=f"Phase {j + 1}",
                    phase_index=j,
                    state=(models.PhaseState.COMPLETE if j < 2 else models.PhaseState.QUEUED),
                )
                db_session.add(phase)

    db_session.commit()


class TestRunsList:
    """Tests for GET /runs endpoint."""

    def test_list_runs_empty(self, client):
        """Returns empty list when no runs exist."""
        response = client.get("/runs")
        assert response.status_code == 200

        data = response.json()
        assert data["runs"] == []
        assert data["total"] == 0
        assert data["limit"] == 20
        assert data["offset"] == 0

    def test_list_runs_with_data(self, client, populated_db):
        """Returns list of runs with correct fields."""
        response = client.get("/runs")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 5
        assert len(data["runs"]) == 5

        # Check first run has all expected fields
        run = data["runs"][0]
        assert "id" in run
        assert "state" in run
        assert "created_at" in run
        assert "tokens_used" in run
        assert "phases_total" in run
        assert "phases_completed" in run

    def test_list_runs_pagination_limit(self, client, populated_db):
        """Respects limit parameter."""
        response = client.get("/runs?limit=2")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 5
        assert len(data["runs"]) == 2
        assert data["limit"] == 2

    def test_list_runs_pagination_offset(self, client, populated_db):
        """Respects offset parameter."""
        response = client.get("/runs?limit=2&offset=2")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 5
        assert len(data["runs"]) == 2
        assert data["offset"] == 2

    def test_list_runs_limit_clamping(self, client, populated_db):
        """Clamps limit to reasonable bounds."""
        # Test max clamping
        response = client.get("/runs?limit=200")
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 100  # Max is 100

        # Test min clamping
        response = client.get("/runs?limit=0")
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 1  # Min is 1

    def test_list_runs_phase_counts(self, client, populated_db):
        """Returns correct phase counts for runs with phases."""
        response = client.get("/runs")
        assert response.status_code == 200

        data = response.json()
        # Find the run with phases (test-run-000)
        run_with_phases = next((r for r in data["runs"] if r["id"] == "test-run-000"), None)
        assert run_with_phases is not None
        assert run_with_phases["phases_total"] == 3
        # PhaseState.COMPLETE maps to "COMPLETE" in the response
        assert run_with_phases["phases_completed"] == 2
