"""Pytest configuration and fixtures for Autopack tests"""

import os
import sys
from pathlib import Path

import pytest

# Ensure tests do not accidentally require a running Postgres instance.
# Autopack defaults to Postgres for production; for unit tests we prefer in-memory SQLite.
# IMPORTANT: This must run before importing `autopack.database` (which creates an engine at import time).
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

# Ensure src directory is in Python path before any imports
project_root = Path(__file__).resolve().parent.parent
src_path = project_root / "src"
backend_path = src_path / "backend"

for path in (project_root, src_path, backend_path):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


def pytest_configure(config):
    """Configure pytest - runs before test collection in all workers.

    This hook ensures sys.path is set up correctly for pytest-xdist parallel execution.
    Essential for memory module tests that import from src/memory.
    """
    _project_root = Path(__file__).resolve().parent.parent
    _src_path = _project_root / "src"
    _src_path_str = str(_src_path)
    if _src_path_str not in sys.path:
        sys.path.insert(0, _src_path_str)

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from autopack.database import Base, get_db
from autopack.main import app

# Import entire models module to ensure all model classes are registered with SQLAlchemy
import autopack.models  # noqa: F401
from autopack.usage_recorder import LlmUsageEvent  # noqa: F401 - ensure model registered

# Explicitly import PolicyPromotion to ensure it's registered (IMP-ARCH-006)
from autopack.models import PolicyPromotion  # noqa: F401


@pytest.fixture(scope="function", autouse=True)
def clear_diagnosis_cache():
    """Clear Doctor diagnosis cache before each test (IMP-COST-007)

    The cache is global and persists between tests. This fixture ensures
    each test starts with a clean cache to avoid cache hits from previous tests.
    """
    from autopack.error_recovery import clear_diagnosis_cache as _clear_cache

    _clear_cache()
    yield
    _clear_cache()


@pytest.fixture(scope="function")
def db_engine():
    """Create a fresh database engine for each test"""
    # Use in-memory SQLite for tests
    # Using StaticPool ensures all connections share the same in-memory database
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
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
    from autopack.config import settings

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
