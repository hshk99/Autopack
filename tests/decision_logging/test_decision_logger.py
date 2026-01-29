"""Tests for structured decision logger."""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from decision_logging.decision_logger import (Decision, DecisionLog,
                                              DecisionLogger,
                                              get_decision_logger)


@pytest.fixture
def temp_log_file():
    """Create a temporary file for decision logs."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        temp_path = f.name
    yield temp_path
    # Cleanup
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def decision_logger(temp_log_file):
    """Create a DecisionLogger instance with temp file."""
    return DecisionLogger(log_path=temp_log_file)


@pytest.fixture
def sample_decision():
    """Create a sample decision for testing."""
    return Decision(
        timestamp=datetime.now(),
        decision_type="retry",
        context={"operation": "test_op", "attempt": 1},
        options_considered=["retry", "fail", "escalate"],
        chosen_option="retry",
        reasoning="First attempt failed, retrying with backoff",
        outcome=None,
    )


class TestDecision:
    """Tests for Decision dataclass."""

    def test_decision_creation(self, sample_decision):
        """Test that Decision can be created with all fields."""
        assert sample_decision.decision_type == "retry"
        assert sample_decision.chosen_option == "retry"
        assert len(sample_decision.options_considered) == 3
        assert sample_decision.outcome is None

    def test_decision_to_dict(self, sample_decision):
        """Test that Decision can be converted to dictionary."""
        data = sample_decision.to_dict()

        assert data["decision_type"] == "retry"
        assert data["chosen_option"] == "retry"
        assert data["context"]["operation"] == "test_op"
        assert isinstance(data["timestamp"], str)

    def test_decision_from_dict(self, sample_decision):
        """Test that Decision can be created from dictionary."""
        data = sample_decision.to_dict()
        restored = Decision.from_dict(data)

        assert restored.decision_type == sample_decision.decision_type
        assert restored.chosen_option == sample_decision.chosen_option
        assert restored.reasoning == sample_decision.reasoning

    def test_decision_roundtrip(self, sample_decision):
        """Test that Decision survives serialization roundtrip."""
        data = sample_decision.to_dict()
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        restored = Decision.from_dict(parsed)

        assert restored.decision_type == sample_decision.decision_type
        assert restored.context == sample_decision.context
        assert restored.options_considered == sample_decision.options_considered


class TestDecisionLog:
    """Tests for DecisionLog dataclass."""

    def test_empty_decision_log(self):
        """Test creating an empty DecisionLog."""
        log = DecisionLog()

        assert len(log.decisions) == 0
        assert log.version == "1.0.0"

    def test_decision_log_to_dict(self, sample_decision):
        """Test DecisionLog serialization."""
        log = DecisionLog(decisions=[sample_decision])
        data = log.to_dict()

        assert data["version"] == "1.0.0"
        assert len(data["decisions"]) == 1
        assert "created_at" in data

    def test_decision_log_from_dict(self, sample_decision):
        """Test DecisionLog deserialization."""
        log = DecisionLog(decisions=[sample_decision])
        data = log.to_dict()
        restored = DecisionLog.from_dict(data)

        assert len(restored.decisions) == 1
        assert restored.decisions[0].decision_type == "retry"


class TestDecisionLogger:
    """Tests for DecisionLogger class."""

    def test_init_creates_log_directory(self, temp_log_file):
        """Test that initialization creates the log directory."""
        nested_path = Path(temp_log_file).parent / "subdir" / "decisions.json"
        DecisionLogger(log_path=str(nested_path))

        assert nested_path.parent.exists()

    def test_log_decision(self, decision_logger, sample_decision, temp_log_file):
        """Test logging a decision."""
        decision_logger.log_decision(sample_decision)

        # Verify file was created and contains the decision
        assert Path(temp_log_file).exists()
        with open(temp_log_file) as f:
            data = json.load(f)

        assert len(data["decisions"]) == 1
        assert data["decisions"][0]["decision_type"] == "retry"

    def test_create_and_log_decision(self, decision_logger, temp_log_file):
        """Test create_and_log_decision helper method."""
        decision = decision_logger.create_and_log_decision(
            decision_type="escalation",
            context={"pr_number": 123},
            options_considered=["escalate", "ignore"],
            chosen_option="escalate",
            reasoning="CI failures exceeded threshold",
        )

        assert decision.decision_type == "escalation"
        assert decision.chosen_option == "escalate"

        # Verify persisted
        with open(temp_log_file) as f:
            data = json.load(f)
        assert len(data["decisions"]) == 1

    def test_multiple_decisions(self, decision_logger, temp_log_file):
        """Test logging multiple decisions."""
        for i in range(5):
            decision_logger.create_and_log_decision(
                decision_type="retry",
                context={"attempt": i},
                options_considered=["retry", "fail"],
                chosen_option="retry",
                reasoning=f"Attempt {i} retry",
            )

        with open(temp_log_file) as f:
            data = json.load(f)

        assert len(data["decisions"]) == 5

    def test_get_decisions_by_type(self, decision_logger):
        """Test filtering decisions by type."""
        decision_logger.create_and_log_decision(
            decision_type="retry",
            context={},
            options_considered=["a", "b"],
            chosen_option="a",
            reasoning="test",
        )
        decision_logger.create_and_log_decision(
            decision_type="escalation",
            context={},
            options_considered=["a", "b"],
            chosen_option="b",
            reasoning="test",
        )
        decision_logger.create_and_log_decision(
            decision_type="retry",
            context={},
            options_considered=["a", "b"],
            chosen_option="a",
            reasoning="test",
        )

        retries = decision_logger.get_decisions_by_type("retry")
        escalations = decision_logger.get_decisions_by_type("escalation")

        assert len(retries) == 2
        assert len(escalations) == 1

    def test_get_recent_decisions(self, decision_logger):
        """Test getting recent decisions."""
        for i in range(15):
            decision_logger.create_and_log_decision(
                decision_type="retry",
                context={"index": i},
                options_considered=["a"],
                chosen_option="a",
                reasoning=f"decision {i}",
            )

        recent = decision_logger.get_recent_decisions(limit=5)

        assert len(recent) == 5
        # Most recent should be first
        assert recent[0].context["index"] == 14
        assert recent[4].context["index"] == 10

    def test_update_outcome(self, decision_logger):
        """Test updating decision outcome."""
        decision_logger.create_and_log_decision(
            decision_type="retry",
            context={},
            options_considered=["a"],
            chosen_option="a",
            reasoning="test",
        )

        success = decision_logger.update_outcome(0, "success")
        assert success is True

        decisions = decision_logger.get_decisions_by_type("retry")
        assert decisions[0].outcome == "success"

    def test_update_outcome_invalid_index(self, decision_logger):
        """Test update_outcome with invalid index."""
        success = decision_logger.update_outcome(999, "failure")
        assert success is False

    def test_get_decision_count_by_type(self, decision_logger):
        """Test getting decision counts by type."""
        decision_logger.create_and_log_decision(
            decision_type="retry",
            context={},
            options_considered=["a"],
            chosen_option="a",
            reasoning="test",
        )
        decision_logger.create_and_log_decision(
            decision_type="retry",
            context={},
            options_considered=["a"],
            chosen_option="a",
            reasoning="test",
        )
        decision_logger.create_and_log_decision(
            decision_type="escalation",
            context={},
            options_considered=["a"],
            chosen_option="a",
            reasoning="test",
        )

        counts = decision_logger.get_decision_count_by_type()

        assert counts["retry"] == 2
        assert counts["escalation"] == 1

    def test_clear_log(self, decision_logger, temp_log_file):
        """Test clearing the decision log."""
        decision_logger.create_and_log_decision(
            decision_type="retry",
            context={},
            options_considered=["a"],
            chosen_option="a",
            reasoning="test",
        )

        decision_logger.clear_log()

        with open(temp_log_file) as f:
            data = json.load(f)

        assert len(data["decisions"]) == 0

    def test_get_decisions_in_range(self, decision_logger):
        """Test getting decisions within a time range."""
        now = datetime.now()

        # Create decisions with known timestamps
        decision1 = Decision(
            timestamp=now - timedelta(hours=2),
            decision_type="retry",
            context={},
            options_considered=["a"],
            chosen_option="a",
            reasoning="old decision",
        )
        decision2 = Decision(
            timestamp=now - timedelta(minutes=30),
            decision_type="retry",
            context={},
            options_considered=["a"],
            chosen_option="a",
            reasoning="recent decision",
        )

        decision_logger.log_decision(decision1)
        decision_logger.log_decision(decision2)

        # Query for last hour
        start = now - timedelta(hours=1)
        end = now
        results = decision_logger.get_decisions_in_range(start, end)

        assert len(results) == 1
        assert results[0].reasoning == "recent decision"

    def test_persistence_across_instances(self, temp_log_file):
        """Test that decisions persist across logger instances."""
        logger1 = DecisionLogger(log_path=temp_log_file)
        logger1.create_and_log_decision(
            decision_type="retry",
            context={"source": "logger1"},
            options_considered=["a"],
            chosen_option="a",
            reasoning="from first logger",
        )

        # Create new instance pointing to same file
        logger2 = DecisionLogger(log_path=temp_log_file)
        decisions = logger2.get_decisions_by_type("retry")

        assert len(decisions) == 1
        assert decisions[0].context["source"] == "logger1"


class TestGetDecisionLogger:
    """Tests for get_decision_logger singleton function."""

    def test_returns_singleton(self, temp_log_file, monkeypatch):
        """Test that get_decision_logger returns same instance."""
        # Reset the module-level singleton
        import decision_logging.decision_logger as module

        module._decision_logger = None

        monkeypatch.setenv("AUTOPACK_DECISION_LOG", temp_log_file)

        logger1 = get_decision_logger()
        logger2 = get_decision_logger()

        assert logger1 is logger2

    def test_override_with_path(self, temp_log_file):
        """Test that providing path creates new instance."""
        import decision_logging.decision_logger as module

        module._decision_logger = None

        logger1 = get_decision_logger(temp_log_file)
        assert logger1.log_path == Path(temp_log_file)
