"""Integration tests for API split-brain fix (BUILD-146 P11 Ops).

Tests that src/backend/main.py provides all endpoints needed by:
- scripts/run_parallel.py (API mode executor)
- src/autopack/autonomous_executor.py

This ensures the production API (src/backend/main.py) can replace
the Supervisor API (src/autopack/main.py) without breaking existing callers.
"""
import pytest
from fastapi.testclient import TestClient


def test_execute_endpoint_exists(client):
    """Test POST /runs/{run_id}/execute endpoint exists and requires auth."""
    # Missing auth should return 401
    response = client.post("/runs/test-run-001/execute")
    assert response.status_code == 401

    # With valid X-API-Key should work (testing mode auto-passes)
    response = client.post(
        "/runs/test-run-001/execute",
        headers={"X-API-Key": "test-key"}
    )
    # Will return 404 because run doesn't exist, but that proves endpoint exists
    assert response.status_code in [200, 400, 404]


def test_status_endpoint_exists(client):
    """Test GET /runs/{run_id}/status endpoint exists and requires auth."""
    # Missing auth should return 401
    response = client.get("/runs/test-run-001/status")
    assert response.status_code == 401

    # With valid X-API-Key should work (testing mode auto-passes)
    response = client.get(
        "/runs/test-run-001/status",
        headers={"X-API-Key": "test-key"}
    )
    # Will return 404 because run doesn't exist, but that proves endpoint exists
    assert response.status_code == 404


def test_execute_run_full_flow(client, sample_run_request, db_session):
    """Test full execute flow: create run, execute, check status."""
    from autopack.models import Run, RunState, Tier, Phase

    # Create run in database
    run_id = sample_run_request["run"]["run_id"]
    run = Run(
        id=run_id,
        state=RunState.RUN_CREATED,
        safety_profile=sample_run_request["run"]["safety_profile"],
        run_scope=sample_run_request["run"]["run_scope"],
        token_cap=sample_run_request["run"]["token_cap"],
        max_phases=sample_run_request["run"]["max_phases"],
    )
    db_session.add(run)

    # Create tiers
    for tier_data in sample_run_request["tiers"]:
        tier = Tier(
            tier_id=tier_data["tier_id"],
            run_id=run_id,
            tier_index=tier_data["tier_index"],
            name=tier_data["name"],
            description=tier_data["description"],
        )
        db_session.add(tier)
    db_session.flush()

    # Create phases
    for phase_data in sample_run_request["phases"]:
        tier = db_session.query(Tier).filter(
            Tier.run_id == run_id,
            Tier.tier_id == phase_data["tier_id"]
        ).first()

        phase = Phase(
            phase_id=phase_data["phase_id"],
            run_id=run_id,
            tier_id=tier.id,
            phase_index=phase_data["phase_index"],
            name=phase_data["name"],
            task_category=phase_data["task_category"],
            complexity=phase_data["complexity"],
        )
        db_session.add(phase)

    db_session.commit()

    # Test execute endpoint (will fail to actually execute, but should accept the request)
    response = client.post(
        f"/runs/{run_id}/execute",
        headers={"X-API-Key": "test-key"}
    )
    # In testing mode with TESTING=1, background execution is skipped
    # Should return 200 with started status
    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == run_id
    assert data["status"] == "started"
    assert data["state"] == "EXECUTING"

    # Test status endpoint
    response = client.get(
        f"/runs/{run_id}/status",
        headers={"X-API-Key": "test-key"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == run_id
    assert "state" in data
    assert "total_phases" in data
    assert "completed_phases" in data
    assert "percent_complete" in data


def test_dual_auth_x_api_key(client, sample_run_request, db_session):
    """Test X-API-Key authentication (autonomous_executor.py pattern)."""
    from autopack.models import Run, RunState

    # Create run
    run_id = "test-auth-xapikey"
    run = Run(
        id=run_id,
        state=RunState.RUN_CREATED,
        safety_profile="normal",
        run_scope="multi_tier",
    )
    db_session.add(run)
    db_session.commit()

    # X-API-Key should work
    response = client.get(
        f"/runs/{run_id}/status",
        headers={"X-API-Key": "any-key-in-test-mode"}
    )
    assert response.status_code == 200


def test_dual_auth_bearer_token(client, sample_run_request, db_session):
    """Test Bearer token authentication (run_parallel.py pattern)."""
    from autopack.models import Run, RunState

    # Create run
    run_id = "test-auth-bearer"
    run = Run(
        id=run_id,
        state=RunState.RUN_CREATED,
        safety_profile="normal",
        run_scope="multi_tier",
    )
    db_session.add(run)
    db_session.commit()

    # Bearer token should work
    response = client.get(
        f"/runs/{run_id}/status",
        headers={"Authorization": "Bearer test-token-123"}
    )
    assert response.status_code == 200


def test_execute_run_already_executing(client, sample_run_request, db_session):
    """Test execute endpoint rejects runs that are already executing."""
    from autopack.models import Run, RunState

    # Create run in PHASE_EXECUTION state (equivalent to executing)
    run_id = "test-already-executing"
    run = Run(
        id=run_id,
        state=RunState.PHASE_EXECUTION,
        safety_profile="normal",
        run_scope="multi_tier",
    )
    db_session.add(run)
    db_session.commit()

    # Try to execute - should fail
    response = client.post(
        f"/runs/{run_id}/execute",
        headers={"X-API-Key": "test-key"}
    )
    assert response.status_code == 400
    assert "already in state" in response.json()["detail"]


def test_execute_run_not_found(client):
    """Test execute endpoint returns 404 for non-existent run."""
    response = client.post(
        "/runs/nonexistent-run/execute",
        headers={"X-API-Key": "test-key"}
    )
    assert response.status_code == 404


def test_status_run_not_found(client):
    """Test status endpoint returns 404 for non-existent run."""
    response = client.get(
        "/runs/nonexistent-run/status",
        headers={"X-API-Key": "test-key"}
    )
    assert response.status_code == 404


def test_status_endpoint_phase_counting(client, sample_run_request, db_session):
    """Test status endpoint correctly counts phase states."""
    from autopack.models import Run, RunState, Tier, Phase, PhaseState

    # Create run with mixed phase states
    run_id = "test-phase-counting"
    run = Run(
        id=run_id,
        state=RunState.PHASE_EXECUTION,
        safety_profile="normal",
        run_scope="multi_tier",
        tokens_used=1500,
        token_cap=5000,
    )
    db_session.add(run)

    tier = Tier(
        tier_id="T1",
        run_id=run_id,
        tier_index=0,
        name="Test Tier",
    )
    db_session.add(tier)
    db_session.flush()

    # Add phases with different states
    phases_data = [
        ("P1", PhaseState.COMPLETE),
        ("P2", PhaseState.COMPLETE),
        ("P3", PhaseState.EXECUTING),
        ("P4", PhaseState.FAILED),
        ("P5", PhaseState.QUEUED),
    ]

    for i, (phase_id, state) in enumerate(phases_data):
        phase = Phase(
            phase_id=phase_id,
            run_id=run_id,
            tier_id=tier.id,
            phase_index=i,
            name=f"Phase {i+1}",
            state=state,
        )
        db_session.add(phase)

    db_session.commit()

    # Check status
    response = client.get(
        f"/runs/{run_id}/status",
        headers={"X-API-Key": "test-key"}
    )
    assert response.status_code == 200
    data = response.json()

    assert data["total_phases"] == 5
    assert data["completed_phases"] == 2
    assert data["failed_phases"] == 1
    assert data["executing_phases"] == 1
    assert data["percent_complete"] == 40.0  # 2/5 * 100
    assert data["tokens_used"] == 1500
    assert data["token_cap"] == 5000
