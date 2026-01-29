"""Tests for feedback loop controller."""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from feedback.loop_controller import (FeedbackLoopController, LoopAction,
                                      LoopState)
from feedback.optimization_detector import OptimizationSuggestion


@pytest.fixture
def mock_metrics_db():
    """Create a mock MetricsDatabase instance."""
    return MagicMock()


@pytest.fixture
def mock_failure_analyzer():
    """Create a mock FailureAnalyzer instance."""
    return MagicMock()


@pytest.fixture
def mock_optimization_detector():
    """Create a mock OptimizationDetector instance."""
    return MagicMock()


@pytest.fixture
def mock_event_logger():
    """Create a mock event logger."""
    return MagicMock()


@pytest.fixture
def controller(
    mock_metrics_db,
    mock_failure_analyzer,
    mock_optimization_detector,
    mock_event_logger,
):
    """Create a FeedbackLoopController instance with mock components."""
    return FeedbackLoopController(
        metrics_db=mock_metrics_db,
        failure_analyzer=mock_failure_analyzer,
        optimization_detector=mock_optimization_detector,
        event_logger=mock_event_logger,
    )


class TestLoopAction:
    """Tests for LoopAction dataclass."""

    def test_action_creation_minimal(self):
        """Test that action can be created with minimal fields."""
        action = LoopAction(
            action_type="alert",
            priority="high",
            description="Test alert",
        )

        assert action.action_type == "alert"
        assert action.priority == "high"
        assert action.description == "Test alert"
        assert action.target is None
        assert action.payload == {}
        assert action.executed is False
        assert action.created_at is not None

    def test_action_creation_full(self):
        """Test that action can be created with all fields."""
        action = LoopAction(
            action_type="suggest",
            priority="medium",
            description="Test suggestion",
            target="phase_123",
            payload={"key": "value"},
        )

        assert action.action_type == "suggest"
        assert action.priority == "medium"
        assert action.description == "Test suggestion"
        assert action.target == "phase_123"
        assert action.payload == {"key": "value"}


class TestLoopState:
    """Tests for LoopState enum."""

    def test_loop_states_exist(self):
        """Test that all expected loop states exist."""
        assert LoopState.IDLE.value == "idle"
        assert LoopState.MONITORING.value == "monitoring"
        assert LoopState.ANALYZING.value == "analyzing"
        assert LoopState.ACTING.value == "acting"
        assert LoopState.PAUSED.value == "paused"


class TestFeedbackLoopController:
    """Tests for FeedbackLoopController class."""

    def test_init_stores_components(self, controller, mock_metrics_db):
        """Test that initialization stores component references."""
        assert controller.metrics_db is mock_metrics_db
        assert controller.state == LoopState.IDLE

    def test_init_without_components(self):
        """Test that controller can be created without components."""
        controller = FeedbackLoopController()

        assert controller.metrics_db is None
        assert controller.failure_analyzer is None
        assert controller.optimization_detector is None
        assert controller.event_logger is None

    def test_register_action_handler(self, controller):
        """Test registering an action handler."""
        handler = MagicMock()
        controller.register_action_handler("alert", handler)

        assert controller._action_handlers["alert"] is handler

    def test_run_cycle_returns_to_idle(
        self, controller, mock_metrics_db, mock_failure_analyzer, mock_optimization_detector
    ):
        """Test that run_cycle returns to idle state after completion."""
        mock_metrics_db.get_phase_outcomes.return_value = []
        mock_failure_analyzer.get_failure_statistics.return_value = {"top_patterns": []}
        mock_optimization_detector.detect_all.return_value = []

        controller.run_cycle()

        assert controller.state == LoopState.IDLE

    def test_run_cycle_aggregates_actions(
        self, controller, mock_metrics_db, mock_failure_analyzer, mock_optimization_detector
    ):
        """Test that run_cycle aggregates actions from all checks."""
        # Setup stagnation detection
        stagnant_time = (datetime.now() - timedelta(minutes=45)).isoformat()
        mock_metrics_db.get_phase_outcomes.return_value = [
            {"phase_id": "test_phase", "outcome": "in_progress", "timestamp": stagnant_time}
        ]

        # Setup failure analysis
        mock_failure_analyzer.get_failure_statistics.return_value = {
            "top_patterns": [
                {
                    "pattern_hash": "abc123",
                    "failure_type": "ci_test_failure",
                    "occurrence_count": 5,
                    "resolution": None,
                }
            ]
        }

        # Setup optimization detection
        mock_optimization_detector.detect_all.return_value = [
            OptimizationSuggestion(
                category="slot_utilization",
                severity="high",
                description="Low utilization",
                current_value=0.3,
                threshold=0.7,
                estimated_impact="More throughput",
                implementation_hint="Increase parallel tasks",
            )
        ]

        actions = controller.run_cycle()

        # Should have stagnation alert + failure escalation + optimization suggestion
        assert len(actions) >= 3


class TestStagnationCheck:
    """Tests for stagnation detection."""

    def test_no_stagnation_with_no_metrics_db(self):
        """Test that no stagnation is detected without metrics database."""
        controller = FeedbackLoopController()
        actions = controller._check_stagnation()

        assert actions == []

    def test_stagnation_detected(self, controller, mock_metrics_db):
        """Test that stagnation is detected for in-progress phases."""
        stagnant_time = (datetime.now() - timedelta(minutes=45)).isoformat()
        mock_metrics_db.get_phase_outcomes.return_value = [
            {"phase_id": "test_phase", "outcome": "in_progress", "timestamp": stagnant_time}
        ]

        actions = controller._check_stagnation()

        assert len(actions) == 1
        assert actions[0].action_type == "alert"
        assert actions[0].priority == "high"
        assert "stagnant" in actions[0].description.lower()
        assert actions[0].target == "test_phase"

    def test_no_stagnation_for_completed_phases(self, controller, mock_metrics_db):
        """Test that completed phases don't trigger stagnation alerts."""
        mock_metrics_db.get_phase_outcomes.return_value = [
            {
                "phase_id": "test_phase",
                "outcome": "completed",
                "timestamp": datetime.now().isoformat(),
            }
        ]

        actions = controller._check_stagnation()

        assert actions == []

    def test_no_stagnation_within_threshold(self, controller, mock_metrics_db):
        """Test that phases within threshold don't trigger alerts."""
        recent_time = (datetime.now() - timedelta(minutes=10)).isoformat()
        mock_metrics_db.get_phase_outcomes.return_value = [
            {"phase_id": "test_phase", "outcome": "in_progress", "timestamp": recent_time}
        ]

        actions = controller._check_stagnation()

        assert actions == []


class TestFailureAnalysis:
    """Tests for failure pattern analysis."""

    def test_no_failures_with_no_analyzer(self):
        """Test that no failures are detected without failure analyzer."""
        controller = FeedbackLoopController()
        actions = controller._analyze_failures()

        assert actions == []

    def test_recurring_failure_without_resolution_escalates(
        self, controller, mock_failure_analyzer
    ):
        """Test that recurring failures without resolution get escalated."""
        mock_failure_analyzer.get_failure_statistics.return_value = {
            "top_patterns": [
                {
                    "pattern_hash": "abc123",
                    "failure_type": "ci_test_failure",
                    "occurrence_count": 5,
                    "resolution": None,
                }
            ]
        }

        actions = controller._analyze_failures()

        assert len(actions) == 1
        assert actions[0].action_type == "escalate"
        assert actions[0].priority == "high"
        assert "recurring" in actions[0].description.lower()

    def test_recurring_failure_with_resolution_suggests(self, controller, mock_failure_analyzer):
        """Test that recurring failures with resolution get suggested."""
        mock_failure_analyzer.get_failure_statistics.return_value = {
            "top_patterns": [
                {
                    "pattern_hash": "abc123",
                    "failure_type": "ci_test_failure",
                    "occurrence_count": 5,
                    "resolution": "Run pre-commit hooks",
                }
            ]
        }

        actions = controller._analyze_failures()

        assert len(actions) == 1
        assert actions[0].action_type == "suggest"
        assert actions[0].priority == "medium"
        assert "Run pre-commit hooks" in actions[0].description

    def test_low_occurrence_no_action(self, controller, mock_failure_analyzer):
        """Test that failures below threshold don't trigger actions."""
        mock_failure_analyzer.get_failure_statistics.return_value = {
            "top_patterns": [
                {
                    "pattern_hash": "abc123",
                    "failure_type": "ci_test_failure",
                    "occurrence_count": 2,  # Below threshold of 3
                    "resolution": None,
                }
            ]
        }

        actions = controller._analyze_failures()

        assert actions == []


class TestOptimizationCheck:
    """Tests for optimization opportunity detection."""

    def test_no_optimizations_with_no_detector(self):
        """Test that no optimizations are detected without detector."""
        controller = FeedbackLoopController()
        actions = controller._check_optimizations()

        assert actions == []

    def test_high_severity_optimization_creates_action(
        self, controller, mock_optimization_detector
    ):
        """Test that high severity optimizations create actions."""
        mock_optimization_detector.detect_all.return_value = [
            OptimizationSuggestion(
                category="slot_utilization",
                severity="high",
                description="Low slot utilization",
                current_value=0.3,
                threshold=0.7,
                estimated_impact="More throughput",
                implementation_hint="Increase parallel tasks",
            )
        ]

        actions = controller._check_optimizations()

        assert len(actions) == 1
        assert actions[0].action_type == "suggest"
        assert actions[0].priority == "high"
        assert "slot_utilization" in actions[0].target

    def test_medium_severity_optimization_no_action(self, controller, mock_optimization_detector):
        """Test that medium severity optimizations don't create actions."""
        mock_optimization_detector.detect_all.return_value = [
            OptimizationSuggestion(
                category="pr_merge_time",
                severity="medium",
                description="Slow merge times",
                current_value=5.0,
                threshold=4.0,
                estimated_impact="Faster feedback",
                implementation_hint="Enable auto-merge",
            )
        ]

        actions = controller._check_optimizations()

        assert actions == []

    def test_optimization_rate_limiting(self, controller, mock_optimization_detector):
        """Test that optimization checks are rate-limited."""
        mock_optimization_detector.detect_all.return_value = []

        # First call should work
        controller._check_optimizations()
        assert "optimization" in controller.last_check

        # Second immediate call should be rate-limited
        mock_optimization_detector.detect_all.reset_mock()
        controller._check_optimizations()

        # detect_all should not have been called again
        mock_optimization_detector.detect_all.assert_not_called()


class TestActionExecution:
    """Tests for action execution."""

    def test_execute_action_with_handler(self, controller, mock_event_logger):
        """Test that actions are executed when handler is registered."""
        handler = MagicMock()
        controller.register_action_handler("alert", handler)

        action = LoopAction(
            action_type="alert",
            priority="high",
            description="Test alert",
        )

        controller._execute_action(action)

        handler.assert_called_once_with(action)
        assert action.executed is True
        assert action in controller.action_history

    def test_execute_action_without_handler(self, controller, mock_event_logger):
        """Test that actions without handler are still recorded."""
        action = LoopAction(
            action_type="unknown",
            priority="low",
            description="Test action",
        )

        controller._execute_action(action)

        assert action.executed is False
        assert action in controller.action_history

    def test_execute_action_handler_error(self, controller, mock_event_logger):
        """Test that handler errors are captured."""
        handler = MagicMock(side_effect=RuntimeError("Handler failed"))
        controller.register_action_handler("alert", handler)

        action = LoopAction(
            action_type="alert",
            priority="high",
            description="Test alert",
        )

        controller._execute_action(action)

        assert action.executed is False
        assert "execution_error" in action.payload
        assert "Handler failed" in action.payload["execution_error"]

    def test_execute_action_logs_event(self, controller, mock_event_logger):
        """Test that action execution logs to event logger."""
        action = LoopAction(
            action_type="alert",
            priority="high",
            description="Test alert",
            target="test_target",
        )

        controller._execute_action(action)

        mock_event_logger.log.assert_called_once()
        call_args = mock_event_logger.log.call_args
        assert "feedback_loop_alert" in call_args[0][0]


class TestGetPendingActions:
    """Tests for pending action retrieval."""

    def test_get_all_pending_actions(self, controller):
        """Test getting all pending actions."""
        controller.pending_actions = [
            LoopAction("alert", "high", "Alert 1", executed=False),
            LoopAction("suggest", "medium", "Suggestion 1", executed=False),
            LoopAction("escalate", "high", "Escalation 1", executed=True),
        ]

        pending = controller.get_pending_actions()

        assert len(pending) == 2

    def test_get_pending_actions_by_priority(self, controller):
        """Test filtering pending actions by priority."""
        controller.pending_actions = [
            LoopAction("alert", "high", "Alert 1", executed=False),
            LoopAction("suggest", "medium", "Suggestion 1", executed=False),
            LoopAction("escalate", "high", "Escalation 1", executed=False),
        ]

        high_priority = controller.get_pending_actions(priority="high")

        assert len(high_priority) == 2
        assert all(a.priority == "high" for a in high_priority)


class TestGetSummary:
    """Tests for summary generation."""

    def test_summary_idle_no_actions(self, controller):
        """Test summary when idle with no actions."""
        summary = controller.get_summary()

        assert "idle" in summary.lower()
        assert "Pending Actions: 0" in summary

    def test_summary_with_pending_actions(self, controller):
        """Test summary with pending actions."""
        controller.pending_actions = [
            LoopAction("alert", "high", "Alert 1", executed=False),
            LoopAction("alert", "critical", "Alert 2", executed=False),
            LoopAction("suggest", "medium", "Suggestion", executed=False),
        ]

        summary = controller.get_summary()

        assert "Pending Actions: 3" in summary
        assert "Critical: 1" in summary
        assert "High: 1" in summary
        assert "Medium: 1" in summary

    def test_summary_with_executed_actions(self, controller):
        """Test summary shows executed action count."""
        controller.action_history = [
            LoopAction("alert", "high", "Alert 1", executed=True),
            LoopAction("suggest", "medium", "Suggestion", executed=True),
            LoopAction("escalate", "high", "Escalation", executed=False),
        ]

        summary = controller.get_summary()

        assert "Total Actions Executed: 2" in summary


class TestExportState:
    """Tests for state export."""

    def test_export_state_creates_file(self, controller):
        """Test that export_state creates a JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "state.json"
            controller.export_state(str(output_path))

            assert output_path.exists()

    def test_export_state_content(self, controller):
        """Test that exported state contains expected fields."""
        controller.pending_actions = [LoopAction("alert", "high", "Test alert", target="test")]
        controller.action_history = [LoopAction("suggest", "medium", "Executed", executed=True)]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "state.json"
            controller.export_state(str(output_path))

            with open(output_path) as f:
                state = json.load(f)

            assert state["state"] == "idle"
            assert "last_check" in state
            assert len(state["pending_actions"]) == 1
            assert state["pending_actions"][0]["action_type"] == "alert"
            assert state["action_history_count"] == 1

    def test_export_state_creates_parent_dirs(self, controller):
        """Test that export_state creates parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "dir" / "state.json"
            controller.export_state(str(output_path))

            assert output_path.exists()
