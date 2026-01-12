"""Contract tests for service/usage_recording.py.

These tests verify the usage recording module's behavior independently
of the full LlmService, using mock database sessions.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from autopack.service.usage_recording import (
    estimate_tokens,
    record_usage,
    record_usage_total_only,
    create_usage_event,
    calculate_token_totals,
    UsageRecordingResult,
)


# ============================================================================
# estimate_tokens tests
# ============================================================================


class TestEstimateTokens:
    """Tests for estimate_tokens function."""

    def test_empty_string_returns_one(self) -> None:
        assert estimate_tokens("") == 1

    def test_short_string_estimation(self) -> None:
        # 4 chars = 1 token with default 4.0 chars/token
        assert estimate_tokens("test") == 1

    def test_longer_string_estimation(self) -> None:
        # 40 chars = 10 tokens with default 4.0 chars/token
        text = "a" * 40
        assert estimate_tokens(text) == 10

    def test_custom_chars_per_token(self) -> None:
        # 40 chars = 20 tokens with 2.0 chars/token
        text = "a" * 40
        assert estimate_tokens(text, chars_per_token=2.0) == 20

    def test_minimum_one_token(self) -> None:
        # Even very short text returns at least 1
        assert estimate_tokens("a") == 1
        assert estimate_tokens("ab") == 1

    def test_realistic_text_estimation(self) -> None:
        # ~400 chars should be ~100 tokens
        text = "This is a sample sentence for testing. " * 10
        tokens = estimate_tokens(text)
        assert 90 <= tokens <= 110  # Allow some variance


# ============================================================================
# record_usage tests
# ============================================================================


class TestRecordUsage:
    """Tests for record_usage function."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        db = MagicMock()
        db.add = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()
        db.rollback = MagicMock()
        return db

    def test_successful_recording(self, mock_db: MagicMock) -> None:
        result = record_usage(
            mock_db,
            provider="openai",
            model="gpt-4o",
            role="builder",
            prompt_tokens=100,
            completion_tokens=50,
            run_id="run-123",
            phase_id="phase-1",
        )

        assert result.success is True
        assert result.error is None
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_calculates_total_tokens(self, mock_db: MagicMock) -> None:
        record_usage(
            mock_db,
            provider="anthropic",
            model="claude-sonnet-4-5",
            role="auditor",
            prompt_tokens=200,
            completion_tokens=100,
        )

        # Verify the event was created with correct total
        call_args = mock_db.add.call_args
        event = call_args[0][0]
        assert event.total_tokens == 300
        assert event.prompt_tokens == 200
        assert event.completion_tokens == 100

    def test_records_provider_and_model(self, mock_db: MagicMock) -> None:
        record_usage(
            mock_db,
            provider="google",
            model="gemini-2.5-pro",
            role="builder",
            prompt_tokens=50,
            completion_tokens=25,
        )

        event = mock_db.add.call_args[0][0]
        assert event.provider == "google"
        assert event.model == "gemini-2.5-pro"

    def test_handles_database_error(self, mock_db: MagicMock) -> None:
        mock_db.commit.side_effect = Exception("DB connection lost")

        result = record_usage(
            mock_db,
            provider="openai",
            model="gpt-4o",
            role="builder",
            prompt_tokens=100,
            completion_tokens=50,
        )

        assert result.success is False
        assert result.error is not None
        assert "DB connection lost" in result.error
        mock_db.rollback.assert_called_once()

    def test_optional_run_and_phase_ids(self, mock_db: MagicMock) -> None:
        # Should not fail without optional IDs
        result = record_usage(
            mock_db,
            provider="openai",
            model="gpt-4o",
            role="builder",
            prompt_tokens=100,
            completion_tokens=50,
        )

        assert result.success is True
        event = mock_db.add.call_args[0][0]
        assert event.run_id is None
        assert event.phase_id is None


# ============================================================================
# record_usage_total_only tests
# ============================================================================


class TestRecordUsageTotalOnly:
    """Tests for record_usage_total_only function."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        db = MagicMock()
        db.add = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()
        db.rollback = MagicMock()
        return db

    def test_successful_total_only_recording(self, mock_db: MagicMock) -> None:
        result = record_usage_total_only(
            mock_db,
            provider="anthropic",
            model="claude-sonnet-4-5",
            role="doctor",
            total_tokens=500,
            run_id="run-456",
            phase_id="phase-2",
        )

        assert result.success is True
        assert result.error is None
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_sets_split_tokens_to_none(self, mock_db: MagicMock) -> None:
        record_usage_total_only(
            mock_db,
            provider="openai",
            model="gpt-4o",
            role="scope_reduction",
            total_tokens=1000,
        )

        event = mock_db.add.call_args[0][0]
        assert event.total_tokens == 1000
        assert event.prompt_tokens is None
        assert event.completion_tokens is None

    def test_handles_database_error(self, mock_db: MagicMock) -> None:
        mock_db.commit.side_effect = Exception("Transaction failed")

        result = record_usage_total_only(
            mock_db,
            provider="google",
            model="gemini-2.5-pro",
            role="builder",
            total_tokens=750,
        )

        assert result.success is False
        assert "Transaction failed" in (result.error or "")
        mock_db.rollback.assert_called_once()


# ============================================================================
# create_usage_event tests
# ============================================================================


class TestCreateUsageEvent:
    """Tests for create_usage_event function."""

    def test_creates_event_with_all_fields(self) -> None:
        event = create_usage_event(
            provider="openai",
            model="gpt-4o",
            role="builder",
            total_tokens=150,
            prompt_tokens=100,
            completion_tokens=50,
            run_id="run-789",
            phase_id="phase-3",
        )

        assert event.provider == "openai"
        assert event.model == "gpt-4o"
        assert event.role == "builder"
        assert event.total_tokens == 150
        assert event.prompt_tokens == 100
        assert event.completion_tokens == 50
        assert event.run_id == "run-789"
        assert event.phase_id == "phase-3"

    def test_creates_event_with_minimal_fields(self) -> None:
        event = create_usage_event(
            provider="anthropic",
            model="claude-sonnet-4-5",
            role="auditor",
            total_tokens=200,
        )

        assert event.provider == "anthropic"
        assert event.model == "claude-sonnet-4-5"
        assert event.total_tokens == 200
        assert event.prompt_tokens is None
        assert event.completion_tokens is None
        assert event.run_id is None
        assert event.phase_id is None

    def test_event_has_timestamp(self) -> None:
        event = create_usage_event(
            provider="google",
            model="gemini-2.5-pro",
            role="builder",
            total_tokens=100,
        )

        assert event.created_at is not None


# ============================================================================
# calculate_token_totals tests
# ============================================================================


class TestCalculateTokenTotals:
    """Tests for calculate_token_totals function."""

    def test_both_tokens_available(self) -> None:
        total, has_split = calculate_token_totals(100, 50)
        assert total == 150
        assert has_split is True

    def test_only_prompt_tokens(self) -> None:
        total, has_split = calculate_token_totals(100, None)
        assert total == 100
        assert has_split is False

    def test_only_completion_tokens(self) -> None:
        total, has_split = calculate_token_totals(None, 50)
        assert total == 50
        assert has_split is False

    def test_no_tokens(self) -> None:
        total, has_split = calculate_token_totals(None, None)
        assert total == 0
        assert has_split is False

    def test_zero_tokens(self) -> None:
        total, has_split = calculate_token_totals(0, 0)
        assert total == 0
        assert has_split is True


# ============================================================================
# UsageRecordingResult dataclass tests
# ============================================================================


class TestUsageRecordingResult:
    """Tests for UsageRecordingResult dataclass."""

    def test_frozen_dataclass(self) -> None:
        result = UsageRecordingResult(success=True, event_id=1, error=None)
        with pytest.raises(Exception):  # FrozenInstanceError
            result.success = False  # type: ignore[misc]

    def test_success_result(self) -> None:
        result = UsageRecordingResult(success=True, event_id=42, error=None)
        assert result.success is True
        assert result.event_id == 42
        assert result.error is None

    def test_failure_result(self) -> None:
        result = UsageRecordingResult(success=False, event_id=None, error="Database error")
        assert result.success is False
        assert result.event_id is None
        assert result.error == "Database error"
