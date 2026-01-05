"""BUILD-144 P0.1/P1: Integration test for dashboard NULL token handling

Verifies that /dashboard/usage endpoint correctly handles LlmUsageEvent records
with NULL prompt_tokens and completion_tokens (from total-only recording).

BUILD-144 P1: Uses in-memory SQLite with StaticPool for parallel-safe testing.
"""

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import Session, sessionmaker

from autopack.main import app, get_db
from autopack.database import Base
from autopack.usage_recorder import LlmUsageEvent


@pytest.fixture(scope="function")
def test_db():
    """
    Create in-memory SQLite database for isolated testing.

    BUILD-144 P1: Uses StaticPool to ensure the in-memory database persists
    for the duration of the test function, enabling parallel-safe testing.
    """
    # Create in-memory SQLite engine with StaticPool
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # Critical for in-memory testing
    )

    # Create all tables
    Base.metadata.create_all(bind=engine)

    # Create session
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()

    yield db

    # Cleanup
    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def client(test_db):
    """Create test client with overridden database dependency"""

    def override_get_db():
        try:
            yield test_db
        finally:
            pass  # Don't close in override

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


class TestDashboardNullTokens:
    """Test dashboard NULL token handling"""

    def test_dashboard_usage_with_null_tokens(self, test_db: Session, client: TestClient):
        """
        Test /dashboard/usage handles NULL token splits without crashing.

        BUILD-144 P0.4: Dashboard now uses total_tokens field for totals,
        so total-only events report correct totals even with NULL splits.
        """
        # Clean up any existing events
        test_db.query(LlmUsageEvent).delete()
        test_db.commit()

        # Insert LlmUsageEvent with NULL token splits (total-only recording)
        null_event = LlmUsageEvent(
            provider="openai",
            model="gpt-4o",
            role="builder",
            total_tokens=1500,  # Total-only recording
            prompt_tokens=None,  # NULL - total-only recording
            completion_tokens=None,  # NULL - total-only recording
            run_id="test-run",
            phase_id="test-phase",
            created_at=datetime.now(timezone.utc),
        )
        test_db.add(null_event)

        # Insert another event with exact token splits
        exact_event = LlmUsageEvent(
            provider="anthropic",
            model="claude-sonnet-4-5",
            role="auditor",
            total_tokens=800,  # Exact split: 600 + 200
            prompt_tokens=600,
            completion_tokens=200,
            run_id="test-run",
            phase_id="test-phase-2",
            created_at=datetime.now(timezone.utc),
        )
        test_db.add(exact_event)
        test_db.commit()

        # Call /dashboard/usage endpoint
        response = client.get("/dashboard/usage?period=week")

        # Should return 200, not crash
        assert (
            response.status_code == 200
        ), f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert "providers" in data
        assert "models" in data

        # Find provider stats
        openai_stats = next((p for p in data["providers"] if p["provider"] == "openai"), None)
        anthropic_stats = next((p for p in data["providers"] if p["provider"] == "anthropic"), None)

        # BUILD-144 P0.4: OpenAI stats should report correct total_tokens=1500 despite NULL splits
        assert openai_stats is not None
        assert openai_stats["prompt_tokens"] == 0  # NULL → 0 for splits
        assert openai_stats["completion_tokens"] == 0  # NULL → 0 for splits
        assert openai_stats["total_tokens"] == 1500  # Uses total_tokens field (not sum of splits)

        # Anthropic stats should have exact tokens
        assert anthropic_stats is not None
        assert anthropic_stats["prompt_tokens"] == 600
        assert anthropic_stats["completion_tokens"] == 200
        assert anthropic_stats["total_tokens"] == 800

    def test_dashboard_usage_mixed_null_and_exact(self, test_db: Session, client: TestClient):
        """
        Test /dashboard/usage with mixed NULL and exact tokens for same provider.

        BUILD-144 P0.4: Totals should sum total_tokens fields (1200 + 1000 = 2200),
        not sum of splits (0+0 + 400+600 = 1000).
        """
        # Clean up
        test_db.query(LlmUsageEvent).delete()
        test_db.commit()

        # Insert two events for same provider - one NULL, one exact
        null_event = LlmUsageEvent(
            provider="openai",
            model="gpt-4o",
            role="builder",
            total_tokens=1200,  # Total-only recording
            prompt_tokens=None,
            completion_tokens=None,
            run_id="test-run-1",
            phase_id="phase-1",
            created_at=datetime.now(timezone.utc),
        )
        test_db.add(null_event)

        exact_event = LlmUsageEvent(
            provider="openai",
            model="gpt-4o",
            role="builder",
            total_tokens=1000,  # Exact split: 400 + 600
            prompt_tokens=400,
            completion_tokens=600,
            run_id="test-run-2",
            phase_id="phase-2",
            created_at=datetime.now(timezone.utc),
        )
        test_db.add(exact_event)
        test_db.commit()

        # Call endpoint
        response = client.get("/dashboard/usage?period=week")
        assert response.status_code == 200

        data = response.json()
        openai_stats = next((p for p in data["providers"] if p["provider"] == "openai"), None)

        # BUILD-144 P0.4: Should aggregate correctly using total_tokens field
        assert openai_stats is not None
        assert openai_stats["prompt_tokens"] == 400  # 0 + 400 (NULL → 0 for splits)
        assert openai_stats["completion_tokens"] == 600  # 0 + 600 (NULL → 0 for splits)
        assert openai_stats["total_tokens"] == 2200  # 1200 + 1000 (uses total_tokens field)

    def test_dashboard_usage_all_null_tokens(self, test_db: Session, client: TestClient):
        """
        Test /dashboard/usage when all events have NULL tokens.

        BUILD-144 P0.4: Should report correct total_tokens sum (3000),
        not 0 from NULL splits.
        """
        # Clean up
        test_db.query(LlmUsageEvent).delete()
        test_db.commit()

        # Insert multiple events, all with NULL tokens (total-only recording)
        for i in range(3):
            event = LlmUsageEvent(
                provider="google",
                model="gemini-2.5-pro",
                role="builder",
                total_tokens=1000,  # Total-only recording
                prompt_tokens=None,
                completion_tokens=None,
                run_id=f"test-run-{i}",
                phase_id=f"phase-{i}",
                created_at=datetime.now(timezone.utc),
            )
            test_db.add(event)
        test_db.commit()

        # Call endpoint
        response = client.get("/dashboard/usage?period=week")
        assert response.status_code == 200

        data = response.json()
        google_stats = next((p for p in data["providers"] if p["provider"] == "google"), None)

        # BUILD-144 P0.4: All NULL splits, but total_tokens should sum correctly
        assert google_stats is not None
        assert google_stats["prompt_tokens"] == 0  # NULL → 0 for splits
        assert google_stats["completion_tokens"] == 0  # NULL → 0 for splits
        assert google_stats["total_tokens"] == 3000  # 1000 + 1000 + 1000 (uses total_tokens field)

    def test_dashboard_usage_model_stats_with_null(self, test_db: Session, client: TestClient):
        """
        Test /dashboard/usage model stats correctly handle NULL tokens.

        BUILD-144 P0.4: Model aggregation should also use total_tokens field.
        """
        # Clean up
        test_db.query(LlmUsageEvent).delete()
        test_db.commit()

        # Insert events with NULL tokens for different models
        null_event = LlmUsageEvent(
            provider="openai",
            model="gpt-4o-mini",
            role="doctor",
            total_tokens=300,  # Total-only recording
            prompt_tokens=None,
            completion_tokens=None,
            run_id="test-run",
            phase_id="phase-1",
            created_at=datetime.now(timezone.utc),
        )
        test_db.add(null_event)

        exact_event = LlmUsageEvent(
            provider="openai",
            model="gpt-4o",
            role="builder",
            total_tokens=1200,  # Exact split: 500 + 700
            prompt_tokens=500,
            completion_tokens=700,
            run_id="test-run",
            phase_id="phase-2",
            created_at=datetime.now(timezone.utc),
        )
        test_db.add(exact_event)
        test_db.commit()

        # Call endpoint
        response = client.get("/dashboard/usage?period=week")
        assert response.status_code == 200

        data = response.json()

        # Find model stats
        gpt4o_mini_stats = next((m for m in data["models"] if m["model"] == "gpt-4o-mini"), None)
        gpt4o_stats = next((m for m in data["models"] if m["model"] == "gpt-4o"), None)

        # BUILD-144 P0.4: gpt-4o-mini with NULL splits should report total_tokens=300
        assert gpt4o_mini_stats is not None
        assert gpt4o_mini_stats["prompt_tokens"] == 0  # NULL → 0 for splits
        assert gpt4o_mini_stats["completion_tokens"] == 0  # NULL → 0 for splits
        assert gpt4o_mini_stats["total_tokens"] == 300  # Uses total_tokens field

        # gpt-4o with exact should have correct tokens
        assert gpt4o_stats is not None
        assert gpt4o_stats["prompt_tokens"] == 500
        assert gpt4o_stats["completion_tokens"] == 700
        assert gpt4o_stats["total_tokens"] == 1200
