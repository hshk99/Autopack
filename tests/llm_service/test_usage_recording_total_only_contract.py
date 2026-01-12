"""Tests for LLM usage recording module

This module tests the usage recording functionality extracted from llm_service.py,
including both full-detail and total-only recording modes.

BUILD-144 P0: Tests ensure correct handling of exact token counts vs total-only mode.
"""

import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.autopack.database import Base
from src.autopack.llm.usage import (
    record_usage,
    record_usage_total_only,
    model_to_provider,
    aggregate_usage_by_run,
    aggregate_usage_by_model,
)
from src.autopack.usage_recorder import LlmUsageEvent


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


class TestRecordUsage:
    """Tests for record_usage function (full detail mode)"""

    def test_record_usage_stores_full_details(self, db_session):
        """Test that record_usage stores complete usage details when enabled."""
        usage = {
            "prompt_tokens": 1000,
            "completion_tokens": 500,
            "total_tokens": 1500,
        }

        record_usage(
            db=db_session,
            run_id="test-run-1",
            phase_id="phase-1",
            model="gpt-4o",
            usage=usage,
            category="builder",
            complexity="medium",
            success=True,
        )

        # Query the recorded event
        event = db_session.query(LlmUsageEvent).first()
        assert event is not None
        assert event.run_id == "test-run-1"
        assert event.phase_id == "phase-1"
        assert event.model == "gpt-4o"
        assert event.provider == "openai"
        assert event.role == "builder"
        assert event.total_tokens == 1500
        assert event.prompt_tokens == 1000
        assert event.completion_tokens == 500

    def test_record_usage_calculates_total_if_missing(self, db_session):
        """Test that record_usage calculates total_tokens from splits if not provided."""
        usage = {
            "prompt_tokens": 800,
            "completion_tokens": 200,
        }

        record_usage(
            db=db_session,
            run_id="test-run-2",
            phase_id="phase-2",
            model="claude-sonnet-4-5",
            usage=usage,
            category="auditor",
            complexity="high",
            success=True,
        )

        event = db_session.query(LlmUsageEvent).first()
        assert event is not None
        assert event.total_tokens == 1000
        assert event.prompt_tokens == 800
        assert event.completion_tokens == 200

    def test_record_usage_handles_missing_db_gracefully(self, db_session):
        """Test that record_usage doesn't crash when DB operation fails."""
        # Close the session to simulate DB failure
        db_session.close()

        usage = {"prompt_tokens": 100, "completion_tokens": 50}

        # Should not raise an exception
        record_usage(
            db=db_session,
            run_id="test-run-3",
            phase_id="phase-3",
            model="gpt-4o",
            usage=usage,
            category="builder",
            complexity="low",
            success=False,
        )

    def test_record_usage_with_optional_fields_none(self, db_session):
        """Test record_usage with None values for optional fields."""
        usage = {"prompt_tokens": 500, "completion_tokens": 250}

        record_usage(
            db=db_session,
            run_id=None,
            phase_id=None,
            model="gemini-1.5-pro",
            usage=usage,
            category="doctor",
            complexity="medium",
            success=True,
        )

        event = db_session.query(LlmUsageEvent).first()
        assert event is not None
        assert event.run_id is None
        assert event.phase_id is None
        assert event.provider == "google"
        assert event.total_tokens == 750


class TestRecordUsageTotalOnly:
    """Tests for record_usage_total_only function (total-only mode)"""

    def test_record_usage_total_only_stores_only_total(self, db_session):
        """Test that record_usage_total_only stores only token counts."""
        record_usage_total_only(
            db=db_session,
            run_id="test-run-4",
            phase_id="phase-4",
            model="gpt-4o",
            total_tokens=2000,
        )

        event = db_session.query(LlmUsageEvent).first()
        assert event is not None
        assert event.run_id == "test-run-4"
        assert event.phase_id == "phase-4"
        assert event.model == "gpt-4o"
        assert event.provider == "openai"
        assert event.total_tokens == 2000
        assert event.prompt_tokens is None
        assert event.completion_tokens is None

    def test_total_only_never_stores_prompt_response_content(self, db_session):
        """Test that total-only mode never stores prompt/response content."""
        record_usage_total_only(
            db=db_session,
            run_id="test-run-5",
            phase_id="phase-5",
            model="claude-opus-4-5",
            total_tokens=3500,
        )

        event = db_session.query(LlmUsageEvent).first()
        assert event is not None
        # Verify no prompt/response token details stored
        assert event.prompt_tokens is None
        assert event.completion_tokens is None
        # But total is recorded
        assert event.total_tokens == 3500

    def test_record_usage_total_only_handles_missing_db_gracefully(self, db_session):
        """Test that record_usage_total_only doesn't crash on DB failure."""
        # Close the session to simulate DB failure
        db_session.close()

        # Should not raise an exception
        record_usage_total_only(
            db=db_session,
            run_id="test-run-6",
            phase_id="phase-6",
            model="gpt-4o",
            total_tokens=1000,
        )


class TestModelToProvider:
    """Tests for model_to_provider mapping function"""

    def test_model_to_provider_claude_anthropic(self):
        """Test that claude-* models map to anthropic."""
        assert model_to_provider("claude-sonnet-4-5") == "anthropic"
        assert model_to_provider("claude-opus-4-5") == "anthropic"
        assert model_to_provider("opus-4-5") == "anthropic"

    def test_model_to_provider_gpt_openai(self):
        """Test that gpt-* and o1-* models map to openai."""
        assert model_to_provider("gpt-4o") == "openai"
        assert model_to_provider("gpt-4-turbo") == "openai"
        assert model_to_provider("o1-preview") == "openai"

    def test_model_to_provider_gemini_google(self):
        """Test that gemini-* models map to google."""
        assert model_to_provider("gemini-1.5-pro") == "google"
        assert model_to_provider("gemini-2.0-flash") == "google"

    def test_model_to_provider_glm_zhipu(self):
        """Test that glm-* models map to zhipu_glm."""
        assert model_to_provider("glm-4-plus") == "zhipu_glm"
        assert model_to_provider("glm-4") == "zhipu_glm"

    def test_model_to_provider_unknown_defaults_openai(self):
        """Test that unknown models default to openai."""
        assert model_to_provider("unknown-model-123") == "openai"
        assert model_to_provider("custom-llm") == "openai"


class TestAggregateUsageByRun:
    """Tests for aggregate_usage_by_run function"""

    def test_aggregate_usage_by_run_sums_correctly(self, db_session):
        """Test that aggregate_usage_by_run sums token counts correctly."""
        # Record multiple usage events for the same run
        usage1 = {"prompt_tokens": 1000, "completion_tokens": 500}
        usage2 = {"prompt_tokens": 800, "completion_tokens": 200}
        usage3 = {"prompt_tokens": 600, "completion_tokens": 400}

        record_usage(
            db=db_session,
            run_id="test-run-7",
            phase_id="phase-1",
            model="gpt-4o",
            usage=usage1,
            category="builder",
            complexity="medium",
            success=True,
        )
        record_usage(
            db=db_session,
            run_id="test-run-7",
            phase_id="phase-2",
            model="claude-sonnet-4-5",
            usage=usage2,
            category="auditor",
            complexity="high",
            success=True,
        )
        record_usage(
            db=db_session,
            run_id="test-run-7",
            phase_id="phase-3",
            model="gpt-4o",
            usage=usage3,
            category="builder",
            complexity="low",
            success=True,
        )

        result = aggregate_usage_by_run(db_session, "test-run-7")

        assert result["run_id"] == "test-run-7"
        assert result["total_tokens"] == 3500  # 1500 + 1000 + 1000
        assert result["total_calls"] == 3

    def test_aggregate_usage_by_run_empty(self, db_session):
        """Test aggregate_usage_by_run returns zeros for non-existent run."""
        result = aggregate_usage_by_run(db_session, "non-existent-run")

        assert result["run_id"] == "non-existent-run"
        assert result["total_tokens"] == 0
        assert result["total_calls"] == 0


class TestAggregateUsageByModel:
    """Tests for aggregate_usage_by_model function"""

    def test_aggregate_usage_by_model_groups_correctly(self, db_session):
        """Test that aggregate_usage_by_model groups by model correctly."""
        # Record usage events with different models
        usage1 = {"prompt_tokens": 1000, "completion_tokens": 500}
        usage2 = {"prompt_tokens": 800, "completion_tokens": 200}
        usage3 = {"prompt_tokens": 600, "completion_tokens": 400}

        record_usage(
            db=db_session,
            run_id="test-run-8",
            phase_id="phase-1",
            model="gpt-4o",
            usage=usage1,
            category="builder",
            complexity="medium",
            success=True,
        )
        record_usage(
            db=db_session,
            run_id="test-run-8",
            phase_id="phase-2",
            model="claude-sonnet-4-5",
            usage=usage2,
            category="auditor",
            complexity="high",
            success=True,
        )
        record_usage(
            db=db_session,
            run_id="test-run-8",
            phase_id="phase-3",
            model="gpt-4o",
            usage=usage3,
            category="builder",
            complexity="low",
            success=True,
        )

        result = aggregate_usage_by_model(db_session, "test-run-8")

        assert "gpt-4o" in result
        assert result["gpt-4o"]["total_tokens"] == 2500  # 1500 + 1000
        assert result["gpt-4o"]["call_count"] == 2
        assert result["gpt-4o"]["provider"] == "openai"

        assert "claude-sonnet-4-5" in result
        assert result["claude-sonnet-4-5"]["total_tokens"] == 1000
        assert result["claude-sonnet-4-5"]["call_count"] == 1
        assert result["claude-sonnet-4-5"]["provider"] == "anthropic"

    def test_aggregate_usage_by_model_empty(self, db_session):
        """Test aggregate_usage_by_model returns empty dict for non-existent run."""
        result = aggregate_usage_by_model(db_session, "non-existent-run")

        assert result == {}


class TestUsageRecordingIntegration:
    """Integration tests combining multiple usage recording functions"""

    def test_mixed_full_and_total_only_recording(self, db_session):
        """Test that mixing full and total-only recording works correctly."""
        # Record with full details
        usage_full = {"prompt_tokens": 1000, "completion_tokens": 500}
        record_usage(
            db=db_session,
            run_id="test-run-9",
            phase_id="phase-1",
            model="gpt-4o",
            usage=usage_full,
            category="builder",
            complexity="medium",
            success=True,
        )

        # Record with total-only
        record_usage_total_only(
            db=db_session,
            run_id="test-run-9",
            phase_id="phase-2",
            model="claude-sonnet-4-5",
            total_tokens=2000,
        )

        # Aggregate should include both
        result = aggregate_usage_by_run(db_session, "test-run-9")
        assert result["total_tokens"] == 3500  # 1500 + 2000
        assert result["total_calls"] == 2

    def test_usage_recording_preserves_timestamps(self, db_session):
        """Test that usage recording preserves creation timestamps."""
        usage = {"prompt_tokens": 100, "completion_tokens": 50}

        record_usage(
            db=db_session,
            run_id="test-run-10",
            phase_id="phase-1",
            model="gpt-4o",
            usage=usage,
            category="builder",
            complexity="low",
            success=True,
        )

        event = db_session.query(LlmUsageEvent).first()

        assert event is not None
        assert event.created_at is not None
        # Verify timestamp is a valid datetime (SQLite may strip timezone)
        assert isinstance(event.created_at, datetime)
