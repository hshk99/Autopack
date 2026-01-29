"""Tests for IMP-REL-001: Autopilot health-gated task generation.

This module tests the health transition handling and auto-resume functionality
in the AutopilotController.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest


class TestAutopilotHealthTransition:
    """Tests for AutopilotController health transition handling."""

    @pytest.fixture
    def controller(self, tmp_path):
        """Create an AutopilotController instance."""
        from autopack.autonomy.autopilot import AutopilotController

        return AutopilotController(
            workspace_root=tmp_path,
            project_id="test-project",
            run_id="test-run",
            enabled=True,
        )

    @pytest.fixture
    def mock_feedback_loop_health(self):
        """Create a mock FeedbackLoopHealth enum."""
        from autopack.telemetry.meta_metrics import FeedbackLoopHealth

        return FeedbackLoopHealth

    def test_initial_state_not_paused(self, controller):
        """Test that task generation is not paused initially."""
        assert controller.is_task_generation_paused() is False
        assert controller.get_pause_reason() is None

    def test_pause_task_generation(self, controller):
        """Test pausing task generation."""
        controller._pause_task_generation("Test pause reason")

        assert controller.is_task_generation_paused() is True
        assert controller.get_pause_reason() == "Test pause reason"

    def test_pause_idempotent(self, controller):
        """Test that pausing multiple times doesn't change reason."""
        controller._pause_task_generation("First reason")
        controller._pause_task_generation("Second reason")

        assert controller.is_task_generation_paused() is True
        assert controller.get_pause_reason() == "First reason"

    def test_trigger_resume(self, controller):
        """Test triggering task generation resume."""
        # First pause
        controller._pause_task_generation("Test pause")
        assert controller.is_task_generation_paused() is True

        # Then resume
        controller._trigger_task_generation_resume()
        assert controller.is_task_generation_paused() is False
        assert controller.get_pause_reason() is None

    def test_resume_when_not_paused_is_noop(self, controller):
        """Test that resume when not paused doesn't cause issues."""
        assert controller.is_task_generation_paused() is False

        # Resume should be a no-op
        controller._trigger_task_generation_resume()

        assert controller.is_task_generation_paused() is False

    def test_on_health_transition_pause(self, controller, mock_feedback_loop_health):
        """Test on_health_transition pauses on ATTENTION_REQUIRED."""
        controller.on_health_transition(
            mock_feedback_loop_health.HEALTHY,
            mock_feedback_loop_health.ATTENTION_REQUIRED,
        )

        assert controller.is_task_generation_paused() is True
        assert "ATTENTION_REQUIRED" in controller.get_pause_reason()

    def test_on_health_transition_resume(self, controller, mock_feedback_loop_health):
        """Test on_health_transition resumes on recovery to HEALTHY."""
        # First pause
        controller._pause_task_generation("Test pause")
        assert controller.is_task_generation_paused() is True

        # Then recover
        controller.on_health_transition(
            mock_feedback_loop_health.ATTENTION_REQUIRED,
            mock_feedback_loop_health.HEALTHY,
        )

        assert controller.is_task_generation_paused() is False

    def test_on_health_transition_degraded_to_healthy(self, controller, mock_feedback_loop_health):
        """Test transition from DEGRADED to HEALTHY doesn't trigger resume logic."""
        # This is NOT a recovery from ATTENTION_REQUIRED, so special resume logic
        # shouldn't apply
        controller.on_health_transition(
            mock_feedback_loop_health.DEGRADED,
            mock_feedback_loop_health.HEALTHY,
        )

        # Should remain not paused (was never paused)
        assert controller.is_task_generation_paused() is False


class TestResumeCallbacks:
    """Tests for resume callback registration and invocation."""

    @pytest.fixture
    def controller(self, tmp_path):
        """Create an AutopilotController instance."""
        from autopack.autonomy.autopilot import AutopilotController

        return AutopilotController(
            workspace_root=tmp_path,
            project_id="test-project",
            run_id="test-run",
            enabled=True,
        )

    def test_register_resume_callback(self, controller):
        """Test registering a resume callback."""
        callback = MagicMock()

        controller.register_resume_callback(callback)

        assert len(controller._resume_callbacks) == 1

    def test_unregister_resume_callback(self, controller):
        """Test unregistering a resume callback."""
        callback = MagicMock()
        controller.register_resume_callback(callback)

        result = controller.unregister_resume_callback(callback)

        assert result is True
        assert len(controller._resume_callbacks) == 0

    def test_unregister_nonexistent_callback(self, controller):
        """Test unregistering a non-existent callback returns False."""
        callback = MagicMock()

        result = controller.unregister_resume_callback(callback)

        assert result is False

    def test_resume_callbacks_invoked(self, controller):
        """Test that resume callbacks are invoked on resume."""
        callback1 = MagicMock()
        callback2 = MagicMock()

        controller.register_resume_callback(callback1)
        controller.register_resume_callback(callback2)

        # Pause and resume
        controller._pause_task_generation("Test pause")
        controller._trigger_task_generation_resume()

        callback1.assert_called_once()
        callback2.assert_called_once()

    def test_resume_callback_exception_does_not_break_others(self, controller):
        """Test that exception in one callback doesn't prevent others."""
        failing_callback = MagicMock(side_effect=ValueError("Test error"))
        working_callback = MagicMock()

        controller.register_resume_callback(failing_callback)
        controller.register_resume_callback(working_callback)

        # Pause and resume
        controller._pause_task_generation("Test pause")
        controller._trigger_task_generation_resume()

        # Both should have been called
        failing_callback.assert_called_once()
        working_callback.assert_called_once()


class TestIntegrationWithHealthTransitions:
    """Integration tests for health transitions with callbacks."""

    @pytest.fixture
    def controller(self, tmp_path):
        """Create an AutopilotController instance."""
        from autopack.autonomy.autopilot import AutopilotController

        return AutopilotController(
            workspace_root=tmp_path,
            project_id="test-project",
            run_id="test-run",
            enabled=True,
        )

    @pytest.fixture
    def mock_feedback_loop_health(self):
        """Create a mock FeedbackLoopHealth enum."""
        from autopack.telemetry.meta_metrics import FeedbackLoopHealth

        return FeedbackLoopHealth

    def test_full_pause_resume_cycle_with_callback(self, controller, mock_feedback_loop_health):
        """Test full pause-resume cycle with callback invocation."""
        resume_callback = MagicMock()
        controller.register_resume_callback(resume_callback)

        # Transition to ATTENTION_REQUIRED (pause)
        controller.on_health_transition(
            mock_feedback_loop_health.HEALTHY,
            mock_feedback_loop_health.ATTENTION_REQUIRED,
        )
        assert controller.is_task_generation_paused() is True
        resume_callback.assert_not_called()

        # Transition to HEALTHY (resume)
        controller.on_health_transition(
            mock_feedback_loop_health.ATTENTION_REQUIRED,
            mock_feedback_loop_health.HEALTHY,
        )
        assert controller.is_task_generation_paused() is False
        resume_callback.assert_called_once()

    def test_multiple_pause_resume_cycles(self, controller, mock_feedback_loop_health):
        """Test multiple pause-resume cycles."""
        resume_count = []

        def count_resume():
            resume_count.append(1)

        controller.register_resume_callback(count_resume)

        # First cycle
        controller.on_health_transition(
            mock_feedback_loop_health.HEALTHY,
            mock_feedback_loop_health.ATTENTION_REQUIRED,
        )
        controller.on_health_transition(
            mock_feedback_loop_health.ATTENTION_REQUIRED,
            mock_feedback_loop_health.HEALTHY,
        )

        # Second cycle
        controller.on_health_transition(
            mock_feedback_loop_health.HEALTHY,
            mock_feedback_loop_health.ATTENTION_REQUIRED,
        )
        controller.on_health_transition(
            mock_feedback_loop_health.ATTENTION_REQUIRED,
            mock_feedback_loop_health.HEALTHY,
        )

        # Should have resumed twice
        assert len(resume_count) == 2


class TestControllerDisabled:
    """Tests for controller behavior when disabled."""

    @pytest.fixture
    def disabled_controller(self, tmp_path):
        """Create a disabled AutopilotController instance."""
        from autopack.autonomy.autopilot import AutopilotController

        return AutopilotController(
            workspace_root=tmp_path,
            project_id="test-project",
            run_id="test-run",
            enabled=False,  # Disabled
        )

    def test_health_gating_works_when_disabled(self, disabled_controller):
        """Test that health gating still works even when controller is disabled.

        Health gating is about the task generation pause state, not about
        whether the controller can run sessions.
        """
        from autopack.telemetry.meta_metrics import FeedbackLoopHealth

        disabled_controller.on_health_transition(
            FeedbackLoopHealth.HEALTHY,
            FeedbackLoopHealth.ATTENTION_REQUIRED,
        )

        assert disabled_controller.is_task_generation_paused() is True
