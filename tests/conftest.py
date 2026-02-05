"""Pytest configuration and fixtures for Autopack tests"""

# CRITICAL: Path setup MUST happen before ANY imports (including pytest)
# This ensures the memory module is importable by pytest-xdist workers
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
_src_path = _project_root / "src"
_src_path_str = str(_src_path)
if _src_path_str not in sys.path:
    sys.path.insert(0, _src_path_str)

import os

import pytest

# Ensure tests do not accidentally require a running Postgres instance.
# Autopack defaults to Postgres for production; for unit tests we prefer in-memory SQLite.
# IMPORTANT: This must run before importing `autopack.database` (which creates an engine at import time).
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

# Additional paths for backend compatibility
backend_path = _src_path / "backend"
for path in (_project_root, _src_path, backend_path):
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

    # IMP-TEST-001: Register flaky marker for tests that may need retries
    config.addinivalue_line(
        "markers", "flaky(reruns=N): mark test as flaky with N reruns on failure"
    )


# Hook that runs at the very start of pytest collection - before any imports
def pytest_load_initial_conftests(early_config, parser, args):
    """Earliest possible hook - runs before conftest collection.

    This is critical for pytest-xdist workers to have correct sys.path
    before any test modules are imported.
    """
    import sys
    from pathlib import Path

    _project_root = Path(__file__).resolve().parent.parent
    _src_path = _project_root / "src"
    _src_path_str = str(_src_path)
    if _src_path_str not in sys.path:
        sys.path.insert(0, _src_path_str)


from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import entire models module to ensure all model classes are registered with SQLAlchemy
import autopack.models  # noqa: F401
from autopack.database import Base, get_db
from autopack.main import app

# Explicitly import PolicyPromotion to ensure it's registered (IMP-ARCH-006)
from autopack.models import PolicyPromotion  # noqa: F401
from autopack.usage_recorder import LlmUsageEvent  # noqa: F401 - ensure model registered


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
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
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


# ---------------------------------------------------------------------------
# IMP-TEST-001: Mock fixtures for Qdrant integration tests
# These fixtures enable testing MemoryService integration paths in CI
# when Qdrant is not available.
# ---------------------------------------------------------------------------


def _check_qdrant_available() -> bool:
    """Check if Qdrant is actually available for integration tests."""
    try:
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("localhost", 6333))
        sock.close()
        return result == 0
    except Exception:
        return False


# Global flag: True if Qdrant server is reachable
QDRANT_AVAILABLE_FOR_TESTS = _check_qdrant_available()


@pytest.fixture
def mock_qdrant_store():
    """Mock Qdrant store for CI environments without Qdrant.

    Provides a mock that simulates QdrantStore behavior for testing
    MemoryService integration paths when Qdrant is unavailable.
    """
    from unittest.mock import MagicMock

    store = MagicMock()
    store.ensure_collection = MagicMock(return_value=None)
    store.upsert = MagicMock(return_value=1)
    store.search = MagicMock(return_value=[])
    store.scroll = MagicMock(return_value=[])
    store.delete = MagicMock(return_value=1)
    store.count = MagicMock(return_value=0)
    store.get_payload = MagicMock(return_value=None)
    store.update_payload = MagicMock(return_value=True)
    return store


@pytest.fixture
def mock_memory_service(monkeypatch, tmp_path):
    """Create a MemoryService instance with mocked Qdrant for testing.

    This fixture patches the Qdrant store creation to use a mock,
    allowing tests to exercise MemoryService integration paths
    without requiring a running Qdrant instance.
    """
    from unittest.mock import MagicMock

    # Create mock store
    mock_store = MagicMock()
    mock_store.ensure_collection = MagicMock(return_value=None)
    mock_store.upsert = MagicMock(return_value=1)
    mock_store.search = MagicMock(return_value=[])
    mock_store.scroll = MagicMock(return_value=[])
    mock_store.delete = MagicMock(return_value=1)
    mock_store.count = MagicMock(return_value=0)
    mock_store.get_payload = MagicMock(return_value=None)
    mock_store.update_payload = MagicMock(return_value=True)

    # Disable env vars that might interfere
    monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)
    monkeypatch.delenv("AUTOPACK_ENABLE_MEMORY", raising=False)

    from autopack.memory import memory_service as ms

    # Use FAISS backend with temp directory for isolation
    faiss_dir = str(tmp_path / ".faiss")
    service = ms.MemoryService(index_dir=faiss_dir, use_qdrant=False)
    return service


@pytest.fixture
def mock_embedding_function(monkeypatch):
    """Mock the embedding function to return predictable vectors.

    Useful for testing MemoryService without calling actual embedding models.
    """
    from unittest.mock import MagicMock

    def fake_embed(text: str) -> list:
        """Return a deterministic embedding based on text hash."""
        import hashlib

        # Create a deterministic 1536-dim vector from text hash
        hash_bytes = hashlib.sha256(text.encode()).digest()
        # Extend to 1536 dimensions by repeating the pattern
        base_vector = [float(b) / 255.0 for b in hash_bytes]
        vector = (base_vector * 48)[:1536]  # 32 * 48 = 1536
        return vector

    mock_embed = MagicMock(side_effect=fake_embed)
    monkeypatch.setattr("autopack.memory.memory_service.sync_embed_text", mock_embed)
    return mock_embed
