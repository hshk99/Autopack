"""Integration tests for dashboard API endpoints"""

import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.autopack.database import Base, get_db
from src.autopack.main import app
from src.autopack import models
from src.autopack.usage_recorder import LlmUsageEvent


# Test database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_dashboard.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def test_db():
    """Create a fresh test database for each test"""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(test_db):
    """Create a test client with test database"""

    def override_get_db():
        try:
            db = TestingSessionLocal()
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def sample_run(client):
    """Create a sample run for testing"""
    response = client.post(
        "/runs/start",
        json={
            "run": {
                "run_id": "test_run_123",
                "safety_profile": "normal",
                "run_scope": "multi_tier",
                "token_cap": 1000000,
            },
            "tiers": [
                {
                    "tier_id": "T1",
                    "tier_index": 0,
                    "name": "Test Tier",
                    "description": "Test tier for dashboard",
                }
            ],
            "phases": [
                {
                    "phase_id": "F1.1",
                    "phase_index": 0,
                    "tier_id": "T1",
                    "name": "Test Phase",
                    "description": "Test phase",
                    "task_category": "general",
                    "complexity": "medium",
                    "builder_mode": "default",
                }
            ],
        },
    )
    assert response.status_code == 201
    return response.json()


def test_dashboard_run_status(client, sample_run):
    """Test GET /dashboard/runs/{run_id}/status endpoint"""
    run_id = sample_run["id"]

    response = client.get(f"/dashboard/runs/{run_id}/status")
    assert response.status_code == 200

    data = response.json()
    assert data["run_id"] == run_id
    assert data["state"] == "RUN_CREATED"
    assert data["total_tiers"] == 1
    assert data["total_phases"] == 1
    assert data["percent_complete"] == 0.0
    assert data["tokens_used"] == 0
    assert data["token_cap"] == 1000000


def test_dashboard_run_status_not_found(client):
    """Test 404 for non-existent run"""
    response = client.get("/dashboard/runs/nonexistent_run/status")
    assert response.status_code == 404


def test_dashboard_usage_empty(client):
    """Test GET /dashboard/usage with no usage data"""
    response = client.get("/dashboard/usage?period=week")
    assert response.status_code == 200

    data = response.json()
    assert data["providers"] == []
    assert data["models"] == []


def test_dashboard_usage_with_data(client):
    """Test GET /dashboard/usage with usage data"""
    # Add some usage events directly to database
    db = TestingSessionLocal()
    try:
        usage1 = LlmUsageEvent(
            provider="openai",
            model="gpt-4o",
            role="builder",
            prompt_tokens=1000,
            completion_tokens=2000,
            run_id="test_run_123",
            phase_id="F1.1",
            created_at=datetime.utcnow(),
        )
        usage2 = LlmUsageEvent(
            provider="openai",
            model="gpt-4o-mini",
            role="auditor",
            prompt_tokens=500,
            completion_tokens=300,
            run_id="test_run_123",
            phase_id="F1.1",
            created_at=datetime.utcnow(),
        )
        db.add_all([usage1, usage2])
        db.commit()
    finally:
        db.close()

    response = client.get("/dashboard/usage?period=week")
    assert response.status_code == 200

    data = response.json()
    assert len(data["providers"]) > 0
    assert len(data["models"]) > 0

    # Check provider data
    openai_provider = next((p for p in data["providers"] if p["provider"] == "openai"), None)
    assert openai_provider is not None
    assert openai_provider["total_tokens"] == 3800  # 1000+2000+500+300


def test_dashboard_human_notes(client, sample_run):
    """Test POST /dashboard/human-notes endpoint"""
    run_id = sample_run["id"]

    response = client.post(
        "/dashboard/human-notes",
        json={"run_id": run_id, "note": "This is a test note from integration test"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["message"] == "Note added successfully"
    assert "timestamp" in data
    assert data["notes_file"] == ".autopack/human_notes.md"


def test_dashboard_models_list(client):
    """Test GET /dashboard/models endpoint"""
    response = client.get("/dashboard/models")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0

    # Check structure of first model mapping
    first_mapping = data[0]
    assert "role" in first_mapping
    assert "category" in first_mapping
    assert "complexity" in first_mapping
    assert "model" in first_mapping
    assert "scope" in first_mapping


def test_dashboard_models_override_global(client):
    """Test POST /dashboard/models/override for global scope"""
    response = client.post(
        "/dashboard/models/override",
        json={
            "scope": "global",
            "role": "builder",
            "category": "tests",
            "complexity": "medium",
            "model": "gpt-4o-mini",
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["message"] == "Global model override requires config file update"
    assert data["scope"] == "global"


def test_dashboard_models_override_run(client, sample_run):
    """Test POST /dashboard/models/override for run scope"""
    run_id = sample_run["id"]

    response = client.post(
        "/dashboard/models/override",
        json={
            "scope": "run",
            "run_id": run_id,
            "role": "builder",
            "category": "tests",
            "complexity": "high",
            "model": "gpt-4-turbo-2024-04-09",
        },
    )
    assert response.status_code == 200

    data = response.json()
    # For now, this returns a "feature coming soon" message
    assert "message" in data


def test_dashboard_run_progress_calculation(client):
    """Test run progress percentage calculation"""
    # Create run with multiple phases
    response = client.post(
        "/runs/start",
        json={
            "run": {
                "run_id": "test_progress_run",
                "safety_profile": "normal",
                "run_scope": "multi_tier",
                "token_cap": 1000000,
            },
            "tiers": [{"tier_id": "T1", "tier_index": 0, "name": "Tier 1"}],
            "phases": [
                {
                    "phase_id": "F1.1",
                    "phase_index": 0,
                    "tier_id": "T1",
                    "name": "Phase 1",
                    "task_category": "general",
                    "complexity": "low",
                },
                {
                    "phase_id": "F1.2",
                    "phase_index": 1,
                    "tier_id": "T1",
                    "name": "Phase 2",
                    "task_category": "tests",
                    "complexity": "medium",
                },
                {
                    "phase_id": "F1.3",
                    "phase_index": 2,
                    "tier_id": "T1",
                    "name": "Phase 3",
                    "task_category": "docs",
                    "complexity": "low",
                },
            ],
        },
    )
    assert response.status_code == 201

    # Check initial progress
    status_response = client.get("/dashboard/runs/test_progress_run/status")
    assert status_response.status_code == 200
    data = status_response.json()
    assert data["total_phases"] == 3
    assert data["completed_phases"] == 0
    assert data["percent_complete"] == 0.0

    # TODO: Test progress after marking phases as complete
    # This would require implementing phase completion endpoints
