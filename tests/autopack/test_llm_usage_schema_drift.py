"""BUILD-144 P0.2: Schema drift test for LlmUsageEvent nullable columns

Verifies that prompt_tokens and completion_tokens are nullable in the schema
and that NULL inserts succeed in SQLite.
"""

import pytest
from datetime import datetime, timezone
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from autopack.database import SessionLocal, engine, Base
from autopack.usage_recorder import LlmUsageEvent


@pytest.fixture(scope="module")
def test_db():
    """Create test database"""
    Base.metadata.create_all(bind=engine)
    yield SessionLocal()
    Base.metadata.drop_all(bind=engine)


class TestLlmUsageSchemadrift:
    """Test LlmUsageEvent schema requirements"""

    def test_prompt_tokens_column_is_nullable(self, test_db: Session):
        """Verify prompt_tokens column is defined as nullable=True"""
        # Ensure tables exist by triggering a dummy query
        test_db.execute(text("SELECT 1")).fetchall()

        inspector = inspect(engine)
        columns = inspector.get_columns("llm_usage_events")

        prompt_tokens_col = next((col for col in columns if col["name"] == "prompt_tokens"), None)
        assert prompt_tokens_col is not None, "prompt_tokens column not found"

        # Column should be nullable (True or None means nullable in SQLAlchemy inspector)
        # In SQLite, nullable is returned as True/False
        # In other databases, it might be None for nullable
        assert prompt_tokens_col["nullable"] in (True, None), (
            f"prompt_tokens column must be nullable, got nullable={prompt_tokens_col['nullable']}"
        )

    def test_completion_tokens_column_is_nullable(self, test_db: Session):
        """Verify completion_tokens column is defined as nullable=True"""
        # Ensure tables exist by triggering a dummy query
        test_db.execute(text("SELECT 1")).fetchall()

        inspector = inspect(engine)
        columns = inspector.get_columns("llm_usage_events")

        completion_tokens_col = next((col for col in columns if col["name"] == "completion_tokens"), None)
        assert completion_tokens_col is not None, "completion_tokens column not found"

        assert completion_tokens_col["nullable"] in (True, None), (
            f"completion_tokens column must be nullable, got nullable={completion_tokens_col['nullable']}"
        )

    def test_total_tokens_column_exists_and_not_nullable(self, test_db: Session):
        """BUILD-144 P0.4: Verify total_tokens column exists and is NOT nullable"""
        # Ensure tables exist by triggering a dummy query
        test_db.execute(text("SELECT 1")).fetchall()

        inspector = inspect(engine)
        columns = inspector.get_columns("llm_usage_events")

        total_tokens_col = next((col for col in columns if col["name"] == "total_tokens"), None)
        assert total_tokens_col is not None, "total_tokens column not found"

        # total_tokens should be non-nullable (False means NOT NULL)
        assert total_tokens_col["nullable"] == False, (
            f"total_tokens column must be non-nullable, got nullable={total_tokens_col['nullable']}"
        )

    def test_insert_null_prompt_tokens_succeeds(self, test_db: Session):
        """Test that inserting NULL prompt_tokens succeeds"""
        event = LlmUsageEvent(
            provider="openai",
            model="gpt-4o",
            role="builder",
            total_tokens=600,  # Total must always be set
            prompt_tokens=None,  # NULL
            completion_tokens=600,
            run_id="test-run",
            phase_id="test-phase",
            created_at=datetime.now(timezone.utc),
        )

        try:
            test_db.add(event)
            test_db.commit()
            test_db.refresh(event)

            # Verify NULL was stored and total_tokens is correct
            assert event.total_tokens == 600
            assert event.prompt_tokens is None
            assert event.completion_tokens == 600
        finally:
            # Cleanup
            test_db.delete(event)
            test_db.commit()

    def test_insert_null_completion_tokens_succeeds(self, test_db: Session):
        """Test that inserting NULL completion_tokens succeeds"""
        event = LlmUsageEvent(
            provider="anthropic",
            model="claude-sonnet-4-5",
            role="auditor",
            total_tokens=400,  # Total must always be set
            prompt_tokens=400,
            completion_tokens=None,  # NULL
            run_id="test-run",
            phase_id="test-phase",
            created_at=datetime.now(timezone.utc),
        )

        try:
            test_db.add(event)
            test_db.commit()
            test_db.refresh(event)

            # Verify NULL was stored and total_tokens is correct
            assert event.total_tokens == 400
            assert event.prompt_tokens == 400
            assert event.completion_tokens is None
        finally:
            # Cleanup
            test_db.delete(event)
            test_db.commit()

    def test_insert_both_tokens_null_succeeds(self, test_db: Session):
        """Test that inserting both prompt_tokens and completion_tokens as NULL succeeds"""
        event = LlmUsageEvent(
            provider="google",
            model="gemini-2.5-pro",
            role="builder",
            total_tokens=1000,  # Total must always be set (total-only recording)
            prompt_tokens=None,  # NULL
            completion_tokens=None,  # NULL
            run_id="test-run",
            phase_id="test-phase",
            created_at=datetime.now(timezone.utc),
        )

        try:
            test_db.add(event)
            test_db.commit()
            test_db.refresh(event)

            # Verify NULLs were stored and total_tokens is correct
            assert event.total_tokens == 1000
            assert event.prompt_tokens is None
            assert event.completion_tokens is None
        finally:
            # Cleanup
            test_db.delete(event)
            test_db.commit()

    def test_query_with_null_tokens_succeeds(self, test_db: Session):
        """Test that querying events with NULL tokens works correctly"""
        # Insert event with NULL tokens
        event = LlmUsageEvent(
            provider="openai",
            model="gpt-4o",
            role="doctor",
            total_tokens=800,  # Total must always be set (total-only recording)
            prompt_tokens=None,
            completion_tokens=None,
            run_id="test-run",
            phase_id="test-phase",
            created_at=datetime.now(timezone.utc),
        )

        try:
            test_db.add(event)
            test_db.commit()

            # Query it back
            queried_event = test_db.query(LlmUsageEvent).filter(
                LlmUsageEvent.run_id == "test-run",
                LlmUsageEvent.phase_id == "test-phase"
            ).first()

            assert queried_event is not None
            assert queried_event.total_tokens == 800
            assert queried_event.prompt_tokens is None
            assert queried_event.completion_tokens is None
            assert queried_event.provider == "openai"
            assert queried_event.role == "doctor"
        finally:
            # Cleanup
            test_db.delete(event)
            test_db.commit()

    def test_filter_by_null_tokens(self, test_db: Session):
        """Test filtering events where tokens are NULL"""
        # Insert mix of NULL and exact token events
        null_event = LlmUsageEvent(
            provider="openai",
            model="gpt-4o",
            role="builder",
            total_tokens=1200,  # Total-only recording
            prompt_tokens=None,
            completion_tokens=None,
            run_id="null-test-run",
            phase_id="phase-1",
            created_at=datetime.now(timezone.utc),
        )

        exact_event = LlmUsageEvent(
            provider="openai",
            model="gpt-4o",
            role="builder",
            total_tokens=1000,  # Exact split: 400 + 600
            prompt_tokens=400,
            completion_tokens=600,
            run_id="exact-test-run",
            phase_id="phase-2",
            created_at=datetime.now(timezone.utc),
        )

        try:
            test_db.add(null_event)
            test_db.add(exact_event)
            test_db.commit()

            # Filter for events with NULL prompt_tokens
            null_events = test_db.query(LlmUsageEvent).filter(
                LlmUsageEvent.prompt_tokens.is_(None)
            ).all()

            assert len(null_events) >= 1
            assert any(e.run_id == "null-test-run" for e in null_events)

            # Filter for events with non-NULL prompt_tokens
            exact_events = test_db.query(LlmUsageEvent).filter(
                LlmUsageEvent.prompt_tokens.isnot(None)
            ).all()

            assert len(exact_events) >= 1
            assert any(e.run_id == "exact-test-run" for e in exact_events)
        finally:
            # Cleanup
            test_db.query(LlmUsageEvent).filter(
                LlmUsageEvent.run_id.in_(["null-test-run", "exact-test-run"])
            ).delete(synchronize_session=False)
            test_db.commit()
