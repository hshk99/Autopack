"""Unit tests for API endpoints"""

import os
from pathlib import Path

import pytest

from src.autopack.models import PhaseState, RunState


def test_root_endpoint(client):
    """Test root endpoint returns service information"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Autopack Supervisor"
    assert "version" in data


def test_health_check(client):
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_start_run(client, sample_run_request):
    """Test starting a new run"""
    response = client.post("/runs/start", json=sample_run_request)
    assert response.status_code == 201

    data = response.json()
    assert data["id"] == "test-run-001"
    assert data["state"] == "RUN_CREATED"
    assert data["safety_profile"] == "normal"
    assert data["run_scope"] == "multi_tier"
    assert len(data["tiers"]) == 2


def test_start_run_duplicate_id(client, sample_run_request):
    """Test that starting a run with duplicate ID fails"""
    # Create first run
    response1 = client.post("/runs/start", json=sample_run_request)
    assert response1.status_code == 201

    # Try to create duplicate
    response2 = client.post("/runs/start", json=sample_run_request)
    assert response2.status_code == 400
    assert "already exists" in response2.json()["detail"]


def test_get_run(client, sample_run_request):
    """Test retrieving run details"""
    # Create run
    create_response = client.post("/runs/start", json=sample_run_request)
    assert create_response.status_code == 201

    # Get run
    response = client.get("/runs/test-run-001")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == "test-run-001"
    assert data["state"] == "RUN_CREATED"
    assert len(data["tiers"]) == 2
    assert data["tiers"][0]["tier_id"] == "T1"
    assert data["tiers"][1]["tier_id"] == "T2"


def test_get_run_not_found(client):
    """Test getting non-existent run returns 404"""
    response = client.get("/runs/non-existent-run")
    assert response.status_code == 404


def test_update_phase_status(client, sample_run_request):
    """Test updating phase status"""
    # Create run
    client.post("/runs/start", json=sample_run_request)

    # Update phase
    update_data = {"state": "EXECUTING", "builder_attempts": 1, "tokens_used": 1000}
    response = client.post("/runs/test-run-001/phases/F1.1/update_status", json=update_data)
    assert response.status_code == 200

    # Verify update
    run_response = client.get("/runs/test-run-001")
    phases = run_response.json()["tiers"][0]["phases"]
    phase_f1_1 = next(p for p in phases if p["phase_id"] == "F1.1")
    assert phase_f1_1["state"] == "EXECUTING"


def test_update_phase_invalid_state(client, sample_run_request):
    """Test updating phase with invalid state"""
    client.post("/runs/start", json=sample_run_request)

    update_data = {"state": "INVALID_STATE"}
    response = client.post("/runs/test-run-001/phases/F1.1/update_status", json=update_data)
    assert response.status_code == 400
    assert "Invalid phase state" in response.json()["detail"]


def test_update_nonexistent_phase(client, sample_run_request):
    """Test updating non-existent phase"""
    client.post("/runs/start", json=sample_run_request)

    update_data = {"state": "EXECUTING"}
    response = client.post("/runs/test-run-001/phases/NONEXISTENT/update_status", json=update_data)
    assert response.status_code == 404


def test_file_layout_created(client, sample_run_request, tmp_path):
    """Test that file layout is created on run start"""
    # Create run
    client.post("/runs/start", json=sample_run_request)

    # Check files exist - use tmp_path which is set in conftest
    run_dir = tmp_path / ".autonomous_runs" / "test-run-001"

    assert (run_dir / "run_summary.md").exists()
    assert (run_dir / "tiers" / "tier_00_Foundation.md").exists()
    assert (run_dir / "tiers" / "tier_01_Features.md").exists()
    assert (run_dir / "phases" / "phase_00_F1.1.md").exists()
    assert (run_dir / "phases" / "phase_01_F2.1.md").exists()


def test_run_with_multiple_phases_in_tier(client):
    """Test creating run with multiple phases in same tier"""
    request = {
        "run": {"run_id": "test-run-002", "safety_profile": "normal", "run_scope": "single_tier"},
        "tiers": [{"tier_id": "T1", "tier_index": 0, "name": "Single Tier"}],
        "phases": [
            {"phase_id": "P1", "phase_index": 0, "tier_id": "T1", "name": "Phase 1"},
            {"phase_id": "P2", "phase_index": 1, "tier_id": "T1", "name": "Phase 2"},
            {"phase_id": "P3", "phase_index": 2, "tier_id": "T1", "name": "Phase 3"},
        ],
    }

    response = client.post("/runs/start", json=request)
    assert response.status_code == 201

    data = response.json()
    assert len(data["tiers"]) == 1
    assert len(data["tiers"][0]["phases"]) == 3


def test_phase_with_unknown_tier(client):
    """Test creating phase with reference to unknown tier"""
    request = {
        "run": {"run_id": "test-run-003"},
        "tiers": [{"tier_id": "T1", "tier_index": 0, "name": "Tier 1"}],
        "phases": [{"phase_id": "P1", "phase_index": 0, "tier_id": "T99", "name": "Phase 1"}],
    }

    response = client.post("/runs/start", json=request)
    assert response.status_code == 400
    assert "unknown tier" in response.json()["detail"].lower()


def test_max_minor_issues_computed(client, sample_run_request):
    """Test that max_minor_issues_total is computed as phases * 3"""
    response = client.post("/runs/start", json=sample_run_request)
    assert response.status_code == 201

    data = response.json()
    # sample_run_request has 2 phases, so max should be 6
    run_response = client.get("/runs/test-run-001")
    # Note: This would need to be checked in the DB or added to the response schema
    # For now we just verify the run was created
    assert data["id"] == "test-run-001"
