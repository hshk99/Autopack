"""Tests for Confidence Score Lifecycle Manager.

IMP-LOOP-034: Tests for ConfidenceManager which manages confidence decay over time
and updates based on task outcomes for the self-improvement feedback loop.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from autopack.memory.confidence_manager import (
    DEFAULT_DECAY_HALF_LIFE_DAYS,
    FAILURE_CONFIDENCE_PENALTY,
    MAX_CONFIDENCE,
    MIN_CONFIDENCE,
    PARTIAL_CONFIDENCE_ADJUSTMENT,
    SUCCESS_CONFIDENCE_BOOST,
    ConfidenceManager,
    ConfidenceState,
)


class TestConfidenceState:
    """Tests for ConfidenceState dataclass."""

    def test_basic_creation(self) -> None:
        """Test creating a ConfidenceState with required fields."""
        state = ConfidenceState(insight_id="test-insight-001")
        assert state.insight_id == "test-insight-001"
        assert state.original_confidence == 1.0
        assert state.outcome_adjustment == 0.0
        assert state.success_count == 0
        assert state.failure_count == 0
        assert state.partial_count == 0

    def test_full_creation(self) -> None:
        """Test creating a ConfidenceState with all fields."""
        created_at = datetime.now(timezone.utc)
        state = ConfidenceState(
            insight_id="test-insight-002",
            original_confidence=0.8,
            created_at=created_at,
            outcome_adjustment=0.1,
            success_count=2,
            failure_count=1,
            partial_count=1,
        )
        assert state.insight_id == "test-insight-002"
        assert state.original_confidence == 0.8
        assert state.created_at == created_at
        assert state.outcome_adjustment == 0.1
        assert state.success_count == 2
        assert state.failure_count == 1
        assert state.partial_count == 1

    def test_to_dict(self) -> None:
        """Test serialization to dictionary."""
        state = ConfidenceState(
            insight_id="test-insight-003",
            original_confidence=0.9,
            success_count=3,
        )
        result = state.to_dict()
        assert result["insight_id"] == "test-insight-003"
        assert result["original_confidence"] == 0.9
        assert result["success_count"] == 3
        assert "created_at" in result
        assert "last_updated" in result

    def test_from_dict(self) -> None:
        """Test deserialization from dictionary."""
        data = {
            "insight_id": "test-insight-004",
            "original_confidence": 0.75,
            "created_at": "2024-01-15T10:30:00+00:00",
            "last_updated": "2024-01-16T11:00:00+00:00",
            "outcome_adjustment": -0.05,
            "success_count": 1,
            "failure_count": 2,
            "partial_count": 0,
        }
        state = ConfidenceState.from_dict(data)
        assert state.insight_id == "test-insight-004"
        assert state.original_confidence == 0.75
        assert state.outcome_adjustment == -0.05
        assert state.success_count == 1
        assert state.failure_count == 2

    def test_from_dict_handles_invalid_timestamps(self) -> None:
        """Test from_dict handles invalid timestamps gracefully."""
        data = {
            "insight_id": "test-insight-005",
            "created_at": "invalid-timestamp",
        }
        state = ConfidenceState.from_dict(data)
        assert state.insight_id == "test-insight-005"
        # Should use current time as fallback
        assert state.created_at is not None


class TestConfidenceManager:
    """Tests for ConfidenceManager class."""

    def test_initialization_with_defaults(self) -> None:
        """Test initialization with default parameters."""
        manager = ConfidenceManager()
        assert manager._half_life == DEFAULT_DECAY_HALF_LIFE_DAYS
        assert manager._min_confidence == MIN_CONFIDENCE
        assert manager._memory_service is None
        assert len(manager._states) == 0

    def test_initialization_with_custom_params(self) -> None:
        """Test initialization with custom parameters."""
        manager = ConfidenceManager(
            decay_half_life_days=14.0,
            min_confidence=0.2,
        )
        assert manager._half_life == 14.0
        assert manager._min_confidence == 0.2

    def test_set_memory_service(self) -> None:
        """Test setting the memory service."""
        manager = ConfidenceManager()
        mock_memory = MagicMock()
        manager.set_memory_service(mock_memory)
        assert manager._memory_service == mock_memory


class TestConfidenceDecay:
    """Tests for confidence decay calculations."""

    def test_no_decay_for_fresh_insight(self) -> None:
        """Test that fresh insights have no decay."""
        manager = ConfidenceManager()
        now = datetime.now(timezone.utc)
        created_at = now  # Just created

        decayed = manager.calculate_decayed_confidence(1.0, created_at, now)
        assert decayed == pytest.approx(1.0, abs=0.001)

    def test_50_percent_decay_at_half_life(self) -> None:
        """Test that confidence is halved after one half-life."""
        manager = ConfidenceManager(decay_half_life_days=7.0)
        now = datetime.now(timezone.utc)
        created_at = now - timedelta(days=7)  # Exactly one half-life ago

        decayed = manager.calculate_decayed_confidence(1.0, created_at, now)
        assert decayed == pytest.approx(0.5, abs=0.001)

    def test_25_percent_decay_at_two_half_lives(self) -> None:
        """Test that confidence is quartered after two half-lives."""
        manager = ConfidenceManager(decay_half_life_days=7.0)
        now = datetime.now(timezone.utc)
        created_at = now - timedelta(days=14)  # Two half-lives ago

        decayed = manager.calculate_decayed_confidence(1.0, created_at, now)
        assert decayed == pytest.approx(0.25, abs=0.001)

    def test_decay_respects_min_confidence(self) -> None:
        """Test that decay never goes below min_confidence."""
        manager = ConfidenceManager(decay_half_life_days=7.0, min_confidence=0.1)
        now = datetime.now(timezone.utc)
        created_at = now - timedelta(days=365)  # Very old

        decayed = manager.calculate_decayed_confidence(1.0, created_at, now)
        assert decayed >= 0.1

    def test_decay_with_partial_confidence(self) -> None:
        """Test decay starting from partial confidence."""
        manager = ConfidenceManager(decay_half_life_days=7.0)
        now = datetime.now(timezone.utc)
        created_at = now - timedelta(days=7)

        decayed = manager.calculate_decayed_confidence(0.8, created_at, now)
        assert decayed == pytest.approx(0.4, abs=0.001)  # 0.8 * 0.5

    def test_decay_handles_future_timestamp(self) -> None:
        """Test that future timestamps return original confidence."""
        manager = ConfidenceManager()
        now = datetime.now(timezone.utc)
        created_at = now + timedelta(days=1)  # Future

        decayed = manager.calculate_decayed_confidence(0.9, created_at, now)
        assert decayed == 0.9

    def test_decay_handles_timezone_naive_datetime(self) -> None:
        """Test that timezone-naive datetimes are handled."""
        manager = ConfidenceManager(decay_half_life_days=7.0)
        now = datetime.now(timezone.utc)
        created_at = datetime.utcnow() - timedelta(days=7)  # Naive datetime

        # Should not raise, should handle timezone conversion
        decayed = manager.calculate_decayed_confidence(1.0, created_at, now)
        assert 0.4 <= decayed <= 0.6  # Approximately 0.5


class TestConfidenceOutcomeUpdates:
    """Tests for confidence updates based on task outcomes."""

    def test_success_increases_confidence(self) -> None:
        """Test that successful task outcomes boost confidence."""
        manager = ConfidenceManager()
        manager.register_insight("insight-001", confidence=0.7)

        new_confidence = manager.update_confidence_from_outcome(
            insight_id="insight-001",
            task_outcome="success",
            persist=False,
        )

        state = manager.get_confidence_state("insight-001")
        assert state.success_count == 1
        assert state.outcome_adjustment == SUCCESS_CONFIDENCE_BOOST
        assert new_confidence > 0.7

    def test_failure_decreases_confidence(self) -> None:
        """Test that failed task outcomes reduce confidence."""
        manager = ConfidenceManager()
        manager.register_insight("insight-002", confidence=0.8)

        new_confidence = manager.update_confidence_from_outcome(
            insight_id="insight-002",
            task_outcome="failure",
            persist=False,
        )

        state = manager.get_confidence_state("insight-002")
        assert state.failure_count == 1
        assert state.outcome_adjustment == -FAILURE_CONFIDENCE_PENALTY
        assert new_confidence < 0.8

    def test_partial_slightly_increases_confidence(self) -> None:
        """Test that partial outcomes slightly boost confidence."""
        manager = ConfidenceManager()
        manager.register_insight("insight-003", confidence=0.6)

        new_confidence = manager.update_confidence_from_outcome(
            insight_id="insight-003",
            task_outcome="partial",
            persist=False,
        )

        state = manager.get_confidence_state("insight-003")
        assert state.partial_count == 1
        assert state.outcome_adjustment == PARTIAL_CONFIDENCE_ADJUSTMENT
        assert new_confidence > 0.6

    def test_unknown_outcome_no_change(self) -> None:
        """Test that unknown outcomes don't change confidence."""
        manager = ConfidenceManager()
        manager.register_insight("insight-004", confidence=0.7)

        original_confidence = manager.get_effective_confidence("insight-004")
        new_confidence = manager.update_confidence_from_outcome(
            insight_id="insight-004",
            task_outcome="unknown_status",
            persist=False,
        )

        assert new_confidence == pytest.approx(original_confidence, abs=0.001)

    def test_multiple_outcomes_accumulate(self) -> None:
        """Test that multiple outcomes accumulate adjustments."""
        manager = ConfidenceManager()
        manager.register_insight("insight-005", confidence=0.7)

        # Two successes
        manager.update_confidence_from_outcome("insight-005", "success", persist=False)
        manager.update_confidence_from_outcome("insight-005", "success", persist=False)

        state = manager.get_confidence_state("insight-005")
        assert state.success_count == 2
        assert state.outcome_adjustment == 2 * SUCCESS_CONFIDENCE_BOOST

    def test_confidence_bounded_at_max(self) -> None:
        """Test that confidence is bounded at MAX_CONFIDENCE."""
        manager = ConfidenceManager()
        manager.register_insight("insight-006", confidence=1.0)

        # Many successes
        for _ in range(10):
            manager.update_confidence_from_outcome("insight-006", "success", persist=False)

        new_confidence = manager.get_effective_confidence("insight-006")
        assert new_confidence <= MAX_CONFIDENCE

    def test_confidence_bounded_at_min(self) -> None:
        """Test that confidence is bounded at MIN_CONFIDENCE."""
        manager = ConfidenceManager()
        manager.register_insight("insight-007", confidence=0.5)

        # Many failures
        for _ in range(10):
            manager.update_confidence_from_outcome("insight-007", "failure", persist=False)

        new_confidence = manager.get_effective_confidence("insight-007")
        assert new_confidence >= MIN_CONFIDENCE


class TestEffectiveConfidence:
    """Tests for combined decay and outcome confidence."""

    def test_effective_confidence_combines_decay_and_adjustment(self) -> None:
        """Test that effective confidence combines time decay and outcome adjustments."""
        manager = ConfidenceManager(decay_half_life_days=7.0)
        now = datetime.now(timezone.utc)
        created_at = now - timedelta(days=7)  # One half-life ago

        manager.register_insight("insight-010", confidence=1.0, created_at=created_at)
        manager.update_confidence_from_outcome("insight-010", "success", persist=False)

        # Effective = (1.0 * 0.5) + 0.15 = 0.65
        effective = manager.get_effective_confidence("insight-010", now=now)
        expected = 0.5 + SUCCESS_CONFIDENCE_BOOST
        assert effective == pytest.approx(expected, abs=0.01)

    def test_effective_confidence_for_untracked_insight(self) -> None:
        """Test effective confidence for an insight not in state cache."""
        manager = ConfidenceManager()
        now = datetime.now(timezone.utc)
        created_at = now - timedelta(days=7)

        effective = manager.get_effective_confidence(
            insight_id="untracked-insight",
            original_confidence=0.8,
            created_at=created_at,
            now=now,
        )

        # Should apply decay to original confidence
        assert effective == pytest.approx(0.4, abs=0.01)


class TestBatchDecayApplication:
    """Tests for applying decay to batches of insights."""

    def test_apply_decay_to_dict_insights(self) -> None:
        """Test applying decay to a list of insight dicts."""
        manager = ConfidenceManager(decay_half_life_days=7.0)
        now = datetime.now(timezone.utc)
        old_timestamp = (now - timedelta(days=7)).isoformat()
        fresh_timestamp = now.isoformat()

        insights = [
            {"id": "insight-a", "confidence": 1.0, "timestamp": old_timestamp},
            {"id": "insight-b", "confidence": 0.8, "timestamp": fresh_timestamp},
        ]

        result = manager.apply_decay_to_insights(
            insights, confidence_field="confidence", created_at_field="timestamp", now=now
        )

        # Old insight should be decayed
        assert result[0]["confidence"] == pytest.approx(0.5, abs=0.01)
        # Fresh insight should be unchanged
        assert result[1]["confidence"] == pytest.approx(0.8, abs=0.01)

    def test_apply_decay_skips_missing_timestamp(self) -> None:
        """Test that insights without timestamps are skipped."""
        manager = ConfidenceManager()

        insights = [
            {"id": "insight-a", "confidence": 1.0},  # No timestamp
        ]

        result = manager.apply_decay_to_insights(insights)
        assert result[0]["confidence"] == 1.0  # Unchanged


class TestPersistence:
    """Tests for confidence persistence to memory service."""

    def test_persist_called_on_outcome_update(self) -> None:
        """Test that persistence is called when updating confidence."""
        mock_memory = MagicMock()
        mock_memory.update_insight_confidence = MagicMock()

        manager = ConfidenceManager(memory_service=mock_memory)
        manager.register_insight("insight-persist-001", confidence=0.8)

        manager.update_confidence_from_outcome(
            insight_id="insight-persist-001",
            task_outcome="success",
            persist=True,
        )

        mock_memory.update_insight_confidence.assert_called_once()

    def test_persist_not_called_when_disabled(self) -> None:
        """Test that persistence is not called when persist=False."""
        mock_memory = MagicMock()
        mock_memory.update_insight_confidence = MagicMock()

        manager = ConfidenceManager(memory_service=mock_memory)
        manager.register_insight("insight-persist-002", confidence=0.8)

        manager.update_confidence_from_outcome(
            insight_id="insight-persist-002",
            task_outcome="success",
            persist=False,
        )

        mock_memory.update_insight_confidence.assert_not_called()


class TestStateManagement:
    """Tests for state management methods."""

    def test_register_insight(self) -> None:
        """Test registering an insight for tracking."""
        manager = ConfidenceManager()
        state = manager.register_insight("insight-reg-001", confidence=0.9)

        assert state.insight_id == "insight-reg-001"
        assert state.original_confidence == 0.9
        assert "insight-reg-001" in manager._states

    def test_get_confidence_state(self) -> None:
        """Test retrieving confidence state."""
        manager = ConfidenceManager()
        manager.register_insight("insight-get-001", confidence=0.75)

        state = manager.get_confidence_state("insight-get-001")
        assert state is not None
        assert state.insight_id == "insight-get-001"

        missing_state = manager.get_confidence_state("nonexistent")
        assert missing_state is None

    def test_reset_state(self) -> None:
        """Test resetting state for an insight."""
        manager = ConfidenceManager()
        manager.register_insight("insight-reset-001")

        result = manager.reset_state("insight-reset-001")
        assert result is True
        assert manager.get_confidence_state("insight-reset-001") is None

        # Resetting nonexistent returns False
        result = manager.reset_state("nonexistent")
        assert result is False

    def test_clear_all_states(self) -> None:
        """Test clearing all tracked states."""
        manager = ConfidenceManager()
        manager.register_insight("insight-clear-001")
        manager.register_insight("insight-clear-002")
        manager.register_insight("insight-clear-003")

        count = manager.clear_all_states()
        assert count == 3
        assert len(manager._states) == 0

    def test_get_statistics(self) -> None:
        """Test getting tracking statistics."""
        manager = ConfidenceManager(decay_half_life_days=7.0, min_confidence=0.1)
        manager.register_insight("insight-stats-001", confidence=0.8)
        manager.register_insight("insight-stats-002", confidence=0.6)

        manager.update_confidence_from_outcome("insight-stats-001", "success", persist=False)
        manager.update_confidence_from_outcome("insight-stats-002", "failure", persist=False)

        stats = manager.get_statistics()
        assert stats["tracked_insights"] == 2
        assert stats["total_successes"] == 1
        assert stats["total_failures"] == 1
        assert stats["half_life_days"] == 7.0
        assert stats["min_confidence"] == 0.1
        assert stats["avg_original_confidence"] == pytest.approx(0.7, abs=0.01)
