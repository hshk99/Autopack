"""Tests for embedding usage tracking (IMP-TEL-003)

This module tests that embedding API calls are properly tracked in usage telemetry,
enabling complete cost attribution for retrieval-heavy phases.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.autopack.database import Base
from src.autopack.usage_recorder import (AUDITOR_ROLE, BUILDER_ROLE,
                                         EMBEDDING_ROLE, LlmUsageEvent)


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


class TestEmbeddingUsageRecorded:
    """Tests for embedding usage recording via OpenAI API."""

    def test_embedding_usage_recorded(self, db_session):
        """Test that embedding API usage is recorded when db session provided."""
        # Mock OpenAI response with usage data
        mock_response = MagicMock()
        mock_response.usage.total_tokens = 150
        mock_response.data = [MagicMock(embedding=[0.1] * 1536)]

        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = mock_response

        with (
            patch("src.autopack.memory.embeddings._USE_OPENAI", True),
            patch("src.autopack.memory.embeddings._openai_client", mock_client),
        ):
            from src.autopack.memory.embeddings import sync_embed_text

            # Call with db session to enable usage tracking
            result = sync_embed_text(
                "test text for embedding",
                db=db_session,
                run_id="test-run-1",
                phase_id="phase-1",
            )

            # Verify embedding returned
            assert len(result) == 1536

            # Verify usage was recorded
            event = db_session.query(LlmUsageEvent).first()
            assert event is not None
            assert event.total_tokens == 150
            assert event.role == EMBEDDING_ROLE
            assert event.run_id == "test-run-1"
            assert event.phase_id == "phase-1"
            assert event.provider == "openai"
            assert event.model == "text-embedding-3-small"
            # Embedding usage is total-only (no prompt/completion split)
            assert event.prompt_tokens is None
            assert event.completion_tokens is None

    def test_embedding_batch_usage_recorded(self, db_session):
        """Test that batch embedding API usage is recorded when db session provided."""
        # Mock OpenAI response with usage data for batch
        mock_response = MagicMock()
        mock_response.usage.total_tokens = 450  # 3 texts
        mock_response.data = [
            MagicMock(embedding=[0.1] * 1536),
            MagicMock(embedding=[0.2] * 1536),
            MagicMock(embedding=[0.3] * 1536),
        ]

        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = mock_response

        with (
            patch("src.autopack.memory.embeddings._USE_OPENAI", True),
            patch("src.autopack.memory.embeddings._openai_client", mock_client),
        ):
            from src.autopack.memory.embeddings import sync_embed_texts

            # Call with db session to enable usage tracking
            results = sync_embed_texts(
                ["text 1", "text 2", "text 3"],
                db=db_session,
                run_id="test-run-2",
                phase_id="phase-2",
            )

            # Verify embeddings returned
            assert len(results) == 3

            # Verify usage was recorded
            event = db_session.query(LlmUsageEvent).first()
            assert event is not None
            assert event.total_tokens == 450
            assert event.role == EMBEDDING_ROLE
            assert event.run_id == "test-run-2"


class TestEmbeddingUsageNotRecordedIfNoUsageData:
    """Tests for handling missing usage data in embedding responses."""

    def test_embedding_usage_not_recorded_if_no_usage_data(self, db_session):
        """Test that no usage is recorded when response has no usage attribute."""
        mock_response = MagicMock(spec=["data"])  # No usage attribute
        mock_response.data = [MagicMock(embedding=[0.1] * 1536)]

        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = mock_response

        with (
            patch("src.autopack.memory.embeddings._USE_OPENAI", True),
            patch("src.autopack.memory.embeddings._openai_client", mock_client),
        ):
            from src.autopack.memory.embeddings import sync_embed_text

            result = sync_embed_text(
                "test text",
                db=db_session,
                run_id="test-run-3",
                phase_id="phase-3",
            )

            # Verify embedding returned
            assert len(result) == 1536

            # Verify no usage was recorded
            event = db_session.query(LlmUsageEvent).first()
            assert event is None

    def test_embedding_usage_not_recorded_if_total_tokens_zero(self, db_session):
        """Test that no usage is recorded when total_tokens is 0."""
        mock_response = MagicMock()
        mock_response.usage.total_tokens = 0
        mock_response.data = [MagicMock(embedding=[0.1] * 1536)]

        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = mock_response

        with (
            patch("src.autopack.memory.embeddings._USE_OPENAI", True),
            patch("src.autopack.memory.embeddings._openai_client", mock_client),
        ):
            from src.autopack.memory.embeddings import sync_embed_text

            result = sync_embed_text(
                "test text",
                db=db_session,
                run_id="test-run-4",
                phase_id="phase-4",
            )

            # Verify embedding returned
            assert len(result) == 1536

            # Verify no usage was recorded
            event = db_session.query(LlmUsageEvent).first()
            assert event is None

    def test_embedding_usage_not_recorded_if_no_db_session(self):
        """Test that no usage is recorded when db session is None."""
        mock_response = MagicMock()
        mock_response.usage.total_tokens = 100
        mock_response.data = [MagicMock(embedding=[0.1] * 1536)]

        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = mock_response

        with (
            patch("src.autopack.memory.embeddings._USE_OPENAI", True),
            patch("src.autopack.memory.embeddings._openai_client", mock_client),
        ):
            from src.autopack.memory.embeddings import sync_embed_text

            # Call without db session (default None)
            result = sync_embed_text("test text")

            # Verify embedding returned (no crash)
            assert len(result) == 1536


class TestEmbeddingRoleValidatorAcceptsEmbedding:
    """Tests for role constants and their validity."""

    def test_embedding_role_validator_accepts_embedding(self, db_session):
        """Test that EMBEDDING_ROLE is a valid role for LlmUsageEvent."""
        from datetime import datetime, timezone

        from src.autopack.usage_recorder import LlmUsageEvent

        # Create an event with EMBEDDING_ROLE
        event = LlmUsageEvent(
            provider="openai",
            model="text-embedding-3-small",
            role=EMBEDDING_ROLE,
            total_tokens=100,
            prompt_tokens=None,
            completion_tokens=None,
            run_id="test-run",
            phase_id="test-phase",
            created_at=datetime.now(timezone.utc),
        )

        db_session.add(event)
        db_session.commit()
        db_session.refresh(event)

        # Verify the event was created with embedding role
        assert event.id is not None
        assert event.role == "embedding"

    def test_role_constants_are_distinct(self):
        """Test that role constants have distinct values."""
        assert BUILDER_ROLE != AUDITOR_ROLE
        assert BUILDER_ROLE != EMBEDDING_ROLE
        assert AUDITOR_ROLE != EMBEDDING_ROLE

    def test_role_constants_are_lowercase_strings(self):
        """Test that role constants are lowercase strings for consistency."""
        assert BUILDER_ROLE == "builder"
        assert AUDITOR_ROLE == "auditor"
        assert EMBEDDING_ROLE == "embedding"


class TestLocalEmbeddingNoUsageRecording:
    """Tests that local (fallback) embeddings don't attempt usage recording."""

    def test_local_embedding_no_usage_recorded(self, db_session):
        """Test that local embeddings don't record any usage."""
        with patch("src.autopack.memory.embeddings._USE_OPENAI", False):
            from src.autopack.memory.embeddings import sync_embed_text

            result = sync_embed_text(
                "test text",
                db=db_session,
                run_id="test-run",
                phase_id="test-phase",
            )

            # Verify embedding returned (local fallback)
            assert len(result) == 1536

            # Verify no usage was recorded (local embeddings are free)
            event = db_session.query(LlmUsageEvent).first()
            assert event is None
