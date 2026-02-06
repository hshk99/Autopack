"""Tests for IMP-LOOP-001: Config property naming mismatch fix.

This module tests that the autonomous_loop correctly uses the
task_generation_auto_execute config property instead of the
non-existent generated_task_execution_enabled property.

The bug: autonomous_loop.py was using getattr(settings, 'generated_task_execution_enabled', False)
which always returned False because the actual config property is task_generation_auto_execute.
"""

from unittest.mock import Mock, patch

from autopack.config import settings


class TestConfigPropertyNamingFix:
    """Test that correct config property is used for task execution."""

    def test_task_generation_auto_execute_exists_in_settings(self):
        """Verify task_generation_auto_execute is a real config property."""
        assert hasattr(settings, "task_generation_auto_execute"), (
            "Settings should have task_generation_auto_execute property. "
            "This is the correct property name for enabling task execution."
        )

    def test_generated_task_execution_enabled_does_not_exist(self):
        """Verify the incorrectly named property does NOT exist.

        This test documents the bug: code was looking for a property
        that doesn't exist, causing getattr to always return the default (False).
        """
        assert not hasattr(settings, "generated_task_execution_enabled"), (
            "Settings should NOT have generated_task_execution_enabled property. "
            "This was the incorrectly named property that caused the bug."
        )

    def test_fetch_generated_tasks_uses_correct_property_when_disabled(self):
        """Verify _fetch_generated_tasks respects task_generation_auto_execute=False."""
        from autopack.executor.autonomous_loop import AutonomousLoop

        mock_executor = Mock()
        mock_executor.run_id = "test-run"

        loop = AutonomousLoop(mock_executor)

        with patch("autopack.executor.autonomous_loop.settings") as mock_settings:
            # Set the CORRECT property to False
            mock_settings.task_generation_auto_execute = False

            result = loop._fetch_generated_tasks()

        assert result == [], "Should return empty list when task execution is disabled"

    def test_fetch_generated_tasks_uses_correct_property_when_enabled(self):
        """Verify _fetch_generated_tasks works when task_generation_auto_execute=True."""
        from autopack.executor.autonomous_loop import AutonomousLoop

        mock_executor = Mock()
        mock_executor.run_id = "test-run"
        mock_executor.db_session = None

        loop = AutonomousLoop(mock_executor)

        mock_task = Mock()
        mock_task.task_id = "task-123"
        mock_task.title = "Test Improvement"
        mock_task.description = "Test description"
        mock_task.priority = "high"
        mock_task.source_insights = []
        mock_task.suggested_files = ["src/test.py"]
        mock_task.estimated_effort = "S"
        mock_task.run_id = "prev-run"

        with patch("autopack.executor.autonomous_loop.settings") as mock_settings:
            # Set the CORRECT property to True
            mock_settings.task_generation_auto_execute = True
            mock_settings.task_generation_max_tasks_per_run = 3

            with patch("autopack.roadc.task_generator.AutonomousTaskGenerator") as MockGenerator:
                mock_generator = MockGenerator.return_value
                mock_generator.get_pending_tasks.return_value = [mock_task]

                result = loop._fetch_generated_tasks()

        assert len(result) == 1, "Should return tasks when execution is enabled"
        assert result[0]["phase_type"] == "generated-task-execution"

    def test_no_getattr_fallback_needed(self):
        """Verify direct property access works without getattr fallback.

        The fix changes from:
            getattr(settings, 'generated_task_execution_enabled', False)
        To:
            settings.task_generation_auto_execute

        Direct access is preferred because:
        1. Fails fast if property is missing (catches typos)
        2. Type checkers can validate property exists
        3. No silent fallback to False
        """
        # Direct access should work without raising AttributeError
        value = settings.task_generation_auto_execute
        assert isinstance(value, bool), "Property should be a boolean"


class TestConfigPropertyDefaults:
    """Test default values for task generation config."""

    def test_task_generation_auto_execute_default_is_true(self):
        """Verify default enables task execution (per IMP-ARCH-018)."""
        # Note: Default was changed to True in IMP-ARCH-018 to enable
        # the self-improvement loop by default
        from autopack.config import Settings

        fresh_settings = Settings()
        assert fresh_settings.task_generation_auto_execute is True, (
            "task_generation_auto_execute should default to True "
            "(per IMP-ARCH-018 self-improvement loop enablement)"
        )

    def test_task_generation_max_tasks_per_run_default(self):
        """Verify max tasks per run has sensible default."""
        from autopack.config import Settings

        fresh_settings = Settings()
        assert (
            fresh_settings.task_generation_max_tasks_per_run == 10
        ), "task_generation_max_tasks_per_run should default to 10"
