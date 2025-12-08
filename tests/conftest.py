"""Pytest configuration and fixtures for Autopack tests"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure src directory is in Python path before any imports
project_root = Path(__file__).resolve().parent.parent
src_path = project_root / "src"
backend_path = src_path / "backend"

for path in (project_root, src_path, backend_path):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.autopack import models
from src.autopack.database import Base, get_db
from src.autopack.main import app
from src.autopack.usage_recorder import LlmUsageEvent  # noqa: F401 - ensure model registered


@pytest.fixture(scope="function")
def db_engine():
    """Create a fresh database engine for each test"""
    # Use in-memory SQLite for tests
    # Using StaticPool ensures all connections share the same in-memory database
    from sqlalchemy.pool import StaticPool
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )

    # Create tables
    Base.metadata.create_all(bind=engine)

    yield engine

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine):
    """Create a database session for each test"""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client(db_engine, db_session, tmp_path, monkeypatch):
    """Create a test client with dependency overrides"""
    # Create a sessionmaker bound to the same engine
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

    def override_get_db():
        """Override that creates new sessions from the same engine"""
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    # Set testing environment variable to skip DB init
    os.environ["TESTING"] = "1"

    # Override autonomous_runs_dir at the settings object level
    # This ensures all code using settings.autonomous_runs_dir uses the temp path
    from src.autopack.config import settings
    test_runs_dir = str(tmp_path / ".autonomous_runs")
    monkeypatch.setattr(settings, "autonomous_runs_dir", test_runs_dir)
    os.environ["AUTONOMOUS_RUNS_DIR"] = test_runs_dir

    # Disable rate limiting in tests
    app.state.limiter.enabled = False

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
