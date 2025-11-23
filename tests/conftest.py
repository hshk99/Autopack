"""Pytest configuration and fixtures for Autopack tests"""

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.autopack import models
from src.autopack.database import Base, get_db
from src.autopack.main import app


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database for each test"""
    # Use in-memory SQLite for tests
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Create tables
    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session, tmp_path):
    """Create a test client with dependency overrides"""

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    # Set testing environment variable to skip DB init
    os.environ["TESTING"] = "1"

    # Override autonomous_runs_dir
    os.environ["AUTONOMOUS_RUNS_DIR"] = str(tmp_path / ".autonomous_runs")

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    del os.environ["TESTING"]


@pytest.fixture
def sample_run_request():
    """Sample run start request"""
    return {
        "run": {
            "run_id": "test-run-001",
            "safety_profile": "normal",
            "run_scope": "multi_tier",
            "token_cap": 5000000,
            "max_phases": 25,
        },
        "tiers": [
            {"tier_id": "T1", "tier_index": 0, "name": "Foundation", "description": "Core setup"},
            {"tier_id": "T2", "tier_index": 1, "name": "Features", "description": "Feature work"},
        ],
        "phases": [
            {
                "phase_id": "F1.1",
                "phase_index": 0,
                "tier_id": "T1",
                "name": "Setup DB",
                "task_category": "schema_change",
                "complexity": "medium",
            },
            {
                "phase_id": "F2.1",
                "phase_index": 1,
                "tier_id": "T2",
                "name": "Add feature",
                "task_category": "feature_scaffolding",
                "complexity": "low",
            },
        ],
    }
