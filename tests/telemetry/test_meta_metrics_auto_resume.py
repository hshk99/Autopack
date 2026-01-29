"""Tests for IMP-REL-001: Auto-resume task generation after health recovery.

This module tests the health transition monitoring and auto-resume functionality
added to MetaMetricsTracker.
"""

import pytest

from autopack.telemetry.meta_metrics import (
    FeedbackLoopHealth,
    FeedbackLoopHealthReport,
    MetaMetricsTracker,
)


@pytest.fixture
def tracker():
    """Create MetaMetricsTracker instance."""
    return MetaMetricsTracker()


@pytest.fixture
def healthy_report():
    """Create a health report with HEALTHY status."""
    return FeedbackLoopHealthReport(
        timestamp="2026-01-28T00:00:00Z",
        overall_status=FeedbackLoopHealth.HEALTHY,
        overall_score=0.85,
        component_reports={},
        critical_issues=[],
        warnings=[],
    )


@pytest.fixture
def degraded_report():
    """Create a health report with DEGRADED status."""
    return FeedbackLoopHealthReport(
        timestamp="2026-01-28T00:00:00Z",
        overall_status=FeedbackLoopHealth.DEGRADED,
        overall_score=0.55,
        component_reports={},
        critical_issues=[],
        warnings=["Some component is degrading"],
    )


@pytest.fixture
def attention_required_report():
    """Create a health report with ATTENTION_REQUIRED status."""
    return FeedbackLoopHealthReport(
        timestamp="2026-01-28T00:00:00Z",
        overall_status=FeedbackLoopHealth.ATTENTION_REQUIRED,
        overall_score=0.35,
        component_reports={},
        critical_issues=["Critical issue 1", "Critical issue 2"],
        warnings=[],
    )


class TestHealthTransitionTracking:
    """Tests for health transition tracking in MetaMetricsTracker."""

    def test_initial_health_status_is_none(self, tracker):
        """Test that previous health status is None initially."""
        assert tracker.get_previous_health_status() is None

    def test_previous_health_status_updated_after_check(self, tracker, healthy_report):
        """Test that previous health status is updated after should_pause_task_generation."""
        tracker.should_pause_task_generation(healthy_report)
        assert tracker.get_previous_health_status() == FeedbackLoopHealth.HEALTHY

    def test_task_generation_paused_state_updated(self, tracker, attention_required_report):
        """Test that task generation paused state is updated correctly."""
        assert tracker.is_task_generation_paused() is False
        tracker.should_pause_task_generation(attention_required_report)
        assert tracker.is_task_generation_paused() is True

    def test_task_generation_not_paused_when_healthy(self, tracker, healthy_report):
        """Test that task generation is not paused when health is HEALTHY."""
        tracker.should_pause_task_generation(healthy_report)
        assert tracker.is_task_generation_paused() is False


class TestHealthTransitionCallbacks:
    """Tests for health transition callback registration and invocation."""

    def test_register_callback(self, tracker):
        """Test that callbacks can be registered."""
        callback_invoked = []

        def callback(old_status, new_status):
            callback_invoked.append((old_status, new_status))

        tracker.register_health_transition_callback(callback)
        assert len(tracker._health_transition_callbacks) == 1

    def test_unregister_callback(self, tracker):
        """Test that callbacks can be unregistered."""

        def callback(old_status, new_status):
            pass

        tracker.register_health_transition_callback(callback)
        assert len(tracker._health_transition_callbacks) == 1

        result = tracker.unregister_health_transition_callback(callback)
        assert result is True
        assert len(tracker._health_transition_callbacks) == 0

    def test_unregister_nonexistent_callback(self, tracker):
        """Test that unregistering a non-existent callback returns False."""

        def callback(old_status, new_status):
            pass

        result = tracker.unregister_health_transition_callback(callback)
        assert result is False

    def test_callback_invoked_on_transition(
        self, tracker, healthy_report, attention_required_report
    ):
        """Test that callbacks are invoked when health status changes."""
        transitions = []

        def callback(old_status, new_status):
            transitions.append((old_status, new_status))

        tracker.register_health_transition_callback(callback)

        # First check - no transition (no previous state)
        tracker.should_pause_task_generation(healthy_report)
        assert len(transitions) == 0

        # Second check - transition from HEALTHY to ATTENTION_REQUIRED
        tracker.should_pause_task_generation(attention_required_report)
        assert len(transitions) == 1
        assert transitions[0] == (
            FeedbackLoopHealth.HEALTHY,
            FeedbackLoopHealth.ATTENTION_REQUIRED,
        )

    def test_callback_not_invoked_when_no_change(self, tracker, healthy_report):
        """Test that callbacks are NOT invoked when health status doesn't change."""
        transitions = []

        def callback(old_status, new_status):
            transitions.append((old_status, new_status))

        tracker.register_health_transition_callback(callback)

        # Check multiple times with same status
        tracker.should_pause_task_generation(healthy_report)
        tracker.should_pause_task_generation(healthy_report)
        tracker.should_pause_task_generation(healthy_report)

        # No transitions should be recorded
        assert len(transitions) == 0

    def test_callback_exception_does_not_break_other_callbacks(
        self, tracker, healthy_report, attention_required_report
    ):
        """Test that exception in one callback doesn't prevent others from running."""
        invocations = []

        def failing_callback(old_status, new_status):
            raise ValueError("Test error")

        def working_callback(old_status, new_status):
            invocations.append((old_status, new_status))

        tracker.register_health_transition_callback(failing_callback)
        tracker.register_health_transition_callback(working_callback)

        # Set initial state
        tracker.should_pause_task_generation(healthy_report)

        # Trigger transition - should not raise
        tracker.should_pause_task_generation(attention_required_report)

        # Working callback should have been invoked
        assert len(invocations) == 1


class TestAutoResumeOnHealthRecovery:
    """Tests for auto-resume when health recovers from ATTENTION_REQUIRED to HEALTHY."""

    def test_pause_cleared_on_recovery(self, tracker, healthy_report, attention_required_report):
        """Test that task generation pause is cleared when health recovers."""
        # First, pause task generation
        tracker.should_pause_task_generation(attention_required_report)
        assert tracker.is_task_generation_paused() is True

        # Then, recover to HEALTHY
        tracker.should_pause_task_generation(healthy_report)
        assert tracker.is_task_generation_paused() is False

    def test_callback_invoked_on_recovery(self, tracker, healthy_report, attention_required_report):
        """Test that recovery transition invokes callbacks."""
        recovery_detected = []

        def callback(old_status, new_status):
            if (
                old_status == FeedbackLoopHealth.ATTENTION_REQUIRED
                and new_status == FeedbackLoopHealth.HEALTHY
            ):
                recovery_detected.append(True)

        tracker.register_health_transition_callback(callback)

        # Pause first
        tracker.should_pause_task_generation(attention_required_report)
        assert len(recovery_detected) == 0

        # Then recover
        tracker.should_pause_task_generation(healthy_report)
        assert len(recovery_detected) == 1

    def test_recovery_through_degraded_state(
        self, tracker, healthy_report, degraded_report, attention_required_report
    ):
        """Test recovery path through DEGRADED state."""
        transitions = []

        def callback(old_status, new_status):
            transitions.append((old_status, new_status))

        tracker.register_health_transition_callback(callback)

        # Start with ATTENTION_REQUIRED
        tracker.should_pause_task_generation(attention_required_report)
        assert tracker.is_task_generation_paused() is True

        # Move to DEGRADED (partial recovery)
        tracker.should_pause_task_generation(degraded_report)
        assert tracker.is_task_generation_paused() is False  # Not paused for DEGRADED

        # Move to HEALTHY (full recovery)
        tracker.should_pause_task_generation(healthy_report)
        assert tracker.is_task_generation_paused() is False

        # Should have recorded two transitions
        assert len(transitions) == 2
        assert transitions[0] == (
            FeedbackLoopHealth.ATTENTION_REQUIRED,
            FeedbackLoopHealth.DEGRADED,
        )
        assert transitions[1] == (
            FeedbackLoopHealth.DEGRADED,
            FeedbackLoopHealth.HEALTHY,
        )

    def test_direct_recovery_from_attention_required_to_healthy(
        self, tracker, healthy_report, attention_required_report
    ):
        """Test direct recovery from ATTENTION_REQUIRED to HEALTHY."""
        # Start with ATTENTION_REQUIRED
        tracker.should_pause_task_generation(attention_required_report)
        assert tracker.is_task_generation_paused() is True
        assert tracker.get_previous_health_status() == FeedbackLoopHealth.ATTENTION_REQUIRED

        # Direct recovery to HEALTHY
        tracker.should_pause_task_generation(healthy_report)
        assert tracker.is_task_generation_paused() is False
        assert tracker.get_previous_health_status() == FeedbackLoopHealth.HEALTHY


class TestMultipleTransitions:
    """Tests for multiple health state transitions."""

    def test_oscillating_health_status(self, tracker, healthy_report, attention_required_report):
        """Test repeated transitions between HEALTHY and ATTENTION_REQUIRED."""
        transitions = []

        def callback(old_status, new_status):
            transitions.append((old_status, new_status))

        tracker.register_health_transition_callback(callback)

        # HEALTHY -> ATTENTION_REQUIRED -> HEALTHY -> ATTENTION_REQUIRED
        tracker.should_pause_task_generation(healthy_report)
        tracker.should_pause_task_generation(attention_required_report)
        tracker.should_pause_task_generation(healthy_report)
        tracker.should_pause_task_generation(attention_required_report)

        assert len(transitions) == 3
        assert tracker.is_task_generation_paused() is True

    def test_consecutive_attention_required_no_multiple_callbacks(
        self, tracker, attention_required_report
    ):
        """Test that consecutive ATTENTION_REQUIRED states don't trigger callbacks."""
        callback_count = []

        def callback(old_status, new_status):
            callback_count.append(1)

        tracker.register_health_transition_callback(callback)

        # Multiple consecutive ATTENTION_REQUIRED checks
        tracker.should_pause_task_generation(attention_required_report)
        tracker.should_pause_task_generation(attention_required_report)
        tracker.should_pause_task_generation(attention_required_report)

        # No transitions (first check has no previous state)
        assert len(callback_count) == 0
        assert tracker.is_task_generation_paused() is True
