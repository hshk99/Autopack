"""Tests for IMP-TEL-001: Client attribution in token usage tracking.

This module tests the client_id field on LlmUsageEvent and the
get_client_usage helper function for SaaS cost attribution.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from autopack.database import Base
from autopack.llm.usage import (get_client_usage, record_usage,
                                record_usage_total_only)
from autopack.usage_recorder import LlmUsageEvent


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


class TestRecordUsageWithClientId:
    """Tests for record_usage with client_id parameter."""

    def test_record_usage_with_client_id(self, db_session):
        """Test that record_usage correctly stores client_id."""
        usage = {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
        }

        record_usage(
            db=db_session,
            run_id="run-123",
            phase_id="phase-1",
            model="gpt-4o",
            usage=usage,
            category="builder",
            complexity="medium",
            success=True,
            client_id="client-abc",
        )

        # Verify the record was created with client_id
        event = db_session.query(LlmUsageEvent).first()
        assert event is not None
        assert event.client_id == "client-abc"
        assert event.run_id == "run-123"
        assert event.total_tokens == 150

    def test_record_usage_total_only_with_client_id(self, db_session):
        """Test that record_usage_total_only correctly stores client_id."""
        record_usage_total_only(
            db=db_session,
            run_id="run-456",
            phase_id="phase-2",
            model="claude-sonnet-4-5",
            total_tokens=500,
            role="auditor",
            client_id="client-xyz",
        )

        # Verify the record was created with client_id
        event = db_session.query(LlmUsageEvent).first()
        assert event is not None
        assert event.client_id == "client-xyz"
        assert event.total_tokens == 500
        assert event.prompt_tokens is None
        assert event.completion_tokens is None


class TestClientIdNullableForBackwardCompatibility:
    """Tests for backward compatibility with NULL client_id."""

    def test_record_usage_without_client_id(self, db_session):
        """Test that client_id defaults to None when not provided."""
        usage = {
            "prompt_tokens": 200,
            "completion_tokens": 100,
        }

        record_usage(
            db=db_session,
            run_id="run-789",
            phase_id="phase-3",
            model="gemini-1.5-pro",
            usage=usage,
            category="doctor",
            complexity="high",
            success=True,
            # client_id not provided
        )

        event = db_session.query(LlmUsageEvent).first()
        assert event is not None
        assert event.client_id is None  # Should be None for backward compatibility
        assert event.total_tokens == 300

    def test_record_usage_total_only_without_client_id(self, db_session):
        """Test that record_usage_total_only works without client_id."""
        record_usage_total_only(
            db=db_session,
            run_id="run-000",
            phase_id="phase-0",
            model="gpt-4o",
            total_tokens=1000,
            role="builder",
            # client_id not provided
        )

        event = db_session.query(LlmUsageEvent).first()
        assert event is not None
        assert event.client_id is None

    def test_mixed_client_id_presence(self, db_session):
        """Test database can contain records with and without client_id."""
        # Record without client_id
        record_usage_total_only(
            db=db_session,
            run_id="run-1",
            phase_id="phase-1",
            model="gpt-4o",
            total_tokens=100,
        )

        # Record with client_id
        record_usage_total_only(
            db=db_session,
            run_id="run-2",
            phase_id="phase-2",
            model="gpt-4o",
            total_tokens=200,
            client_id="client-123",
        )

        events = db_session.query(LlmUsageEvent).all()
        assert len(events) == 2

        # One should have client_id, one should not
        client_ids = [e.client_id for e in events]
        assert None in client_ids
        assert "client-123" in client_ids


class TestGetClientUsageAggregatesCorrectly:
    """Tests for get_client_usage aggregation function."""

    def test_get_client_usage_basic_aggregation(self, db_session):
        """Test basic aggregation for a single client."""
        now = datetime.now(timezone.utc)

        # Create multiple usage events for the same client
        for i in range(3):
            event = LlmUsageEvent(
                provider="openai",
                model="gpt-4o",
                role="builder",
                total_tokens=100 * (i + 1),
                prompt_tokens=60 * (i + 1),
                completion_tokens=40 * (i + 1),
                run_id=f"run-{i}",
                client_id="client-test",
                created_at=now - timedelta(hours=i),
            )
            db_session.add(event)
        db_session.commit()

        # Query usage for the client
        result = get_client_usage(
            db=db_session,
            client_id="client-test",
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=1),
        )

        assert result["client_id"] == "client-test"
        assert result["total_tokens"] == 100 + 200 + 300  # 600
        assert result["total_calls"] == 3

    def test_get_client_usage_filters_by_date_range(self, db_session):
        """Test that date range filtering works correctly."""
        now = datetime.now(timezone.utc)

        # Events inside date range
        for i in range(2):
            event = LlmUsageEvent(
                provider="openai",
                model="gpt-4o",
                role="builder",
                total_tokens=100,
                client_id="client-date-test",
                created_at=now - timedelta(hours=i),
            )
            db_session.add(event)

        # Event outside date range (5 days ago)
        old_event = LlmUsageEvent(
            provider="openai",
            model="gpt-4o",
            role="builder",
            total_tokens=999,
            client_id="client-date-test",
            created_at=now - timedelta(days=5),
        )
        db_session.add(old_event)
        db_session.commit()

        # Query for last 1 day only
        result = get_client_usage(
            db=db_session,
            client_id="client-date-test",
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(hours=1),
        )

        # Should only include the 2 recent events, not the old one
        assert result["total_tokens"] == 200  # 2 * 100
        assert result["total_calls"] == 2

    def test_get_client_usage_filters_by_client(self, db_session):
        """Test that only events for the specified client are aggregated."""
        now = datetime.now(timezone.utc)

        # Events for client A
        for i in range(2):
            db_session.add(
                LlmUsageEvent(
                    provider="openai",
                    model="gpt-4o",
                    role="builder",
                    total_tokens=100,
                    client_id="client-A",
                    created_at=now,
                )
            )

        # Events for client B
        db_session.add(
            LlmUsageEvent(
                provider="openai",
                model="gpt-4o",
                role="builder",
                total_tokens=500,
                client_id="client-B",
                created_at=now,
            )
        )
        db_session.commit()

        # Query for client A only
        result = get_client_usage(
            db=db_session,
            client_id="client-A",
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=1),
        )

        assert result["total_tokens"] == 200  # Only client A's tokens
        assert result["total_calls"] == 2

    def test_get_client_usage_by_model_breakdown(self, db_session):
        """Test that usage is broken down by model."""
        now = datetime.now(timezone.utc)

        # GPT-4o events
        db_session.add(
            LlmUsageEvent(
                provider="openai",
                model="gpt-4o",
                role="builder",
                total_tokens=100,
                client_id="client-model-test",
                created_at=now,
            )
        )

        # Claude events
        db_session.add(
            LlmUsageEvent(
                provider="anthropic",
                model="claude-sonnet-4-5",
                role="auditor",
                total_tokens=200,
                client_id="client-model-test",
                created_at=now,
            )
        )
        db_session.commit()

        result = get_client_usage(
            db=db_session,
            client_id="client-model-test",
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=1),
        )

        assert "by_model" in result
        assert result["by_model"]["gpt-4o"]["tokens"] == 100
        assert result["by_model"]["gpt-4o"]["calls"] == 1
        assert result["by_model"]["claude-sonnet-4-5"]["tokens"] == 200
        assert result["by_model"]["claude-sonnet-4-5"]["calls"] == 1

    def test_get_client_usage_by_provider_breakdown(self, db_session):
        """Test that usage is broken down by provider."""
        now = datetime.now(timezone.utc)

        # OpenAI events
        db_session.add(
            LlmUsageEvent(
                provider="openai",
                model="gpt-4o",
                role="builder",
                total_tokens=100,
                client_id="client-provider-test",
                created_at=now,
            )
        )

        # Anthropic events
        db_session.add(
            LlmUsageEvent(
                provider="anthropic",
                model="claude-sonnet-4-5",
                role="auditor",
                total_tokens=300,
                client_id="client-provider-test",
                created_at=now,
            )
        )
        db_session.commit()

        result = get_client_usage(
            db=db_session,
            client_id="client-provider-test",
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=1),
        )

        assert "by_provider" in result
        assert result["by_provider"]["openai"]["tokens"] == 100
        assert result["by_provider"]["anthropic"]["tokens"] == 300

    def test_get_client_usage_empty_result(self, db_session):
        """Test that empty results are handled correctly."""
        now = datetime.now(timezone.utc)

        result = get_client_usage(
            db=db_session,
            client_id="nonexistent-client",
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=1),
        )

        assert result["client_id"] == "nonexistent-client"
        assert result["total_tokens"] == 0
        assert result["total_calls"] == 0
        assert result["by_model"] == {}
        assert result["by_provider"] == {}
