"""Tests for IMP-LOOP-002: Wire generated_task_max_per_run to config property.

This module tests that the autonomous_loop correctly uses the
task_generation_max_tasks_per_run config property instead of a
non-existent generated_task_max_per_run property with getattr fallback.

The bug: autonomous_loop.py was using getattr(settings, 'generated_task_max_per_run', 3)
which always fell back to hardcoded default 3 because the actual config property
is named task_generation_max_tasks_per_run (with default 10).
"""

from unittest.mock import Mock, patch

from autopack.config import settings


class TestMaxTasksConfigPropertyFix:
    """Test that correct config property is used for max tasks per run."""

    def test_task_generation_max_tasks_per_run_exists_in_settings(self):
        """Verify task_generation_max_tasks_per_run is a real config property."""
        assert hasattr(settings, "task_generation_max_tasks_per_run"), (
            "Settings should have task_generation_max_tasks_per_run property. "
            "This is the correct property name for max generated tasks per run."
        )

    def test_generated_task_max_per_run_does_not_exist(self):
        """Verify the incorrectly named property does NOT exist.

        This test documents the bug: code was looking for a property
        that doesn't exist, causing getattr to always return the default (3).
        """
        assert not hasattr(settings, "generated_task_max_per_run"), (
            "Settings should NOT have generated_task_max_per_run property. "
            "This was the incorrectly named property that caused the bug."
        )

    def test_fetch_generated_tasks_respects_configured_limit(self):
        """Verify _fetch_generated_tasks uses task_generation_max_tasks_per_run."""
        from autopack.executor.autonomous_loop import AutonomousLoop

        mock_executor = Mock()
        mock_executor.run_id = "test-run"
        mock_executor.db_session = None

        loop = AutonomousLoop(mock_executor)

        # Create mock tasks
        mock_tasks = []
        for i in range(5):
            task = Mock()
            task.task_id = f"task-{i}"
            task.title = f"Test Improvement {i}"
            task.description = f"Test description {i}"
            task.priority = "high"
            task.source_insights = []
            task.suggested_files = ["src/test.py"]
            task.estimated_effort = "S"
            task.run_id = "prev-run"
            mock_tasks.append(task)

        with patch("autopack.executor.autonomous_loop.settings") as mock_settings:
            mock_settings.task_generation_auto_execute = True
            # Set specific limit - the fix ensures this is used instead of hardcoded 3
            mock_settings.task_generation_max_tasks_per_run = 5

            with patch("autopack.roadc.task_generator.AutonomousTaskGenerator") as MockGenerator:
                mock_generator = MockGenerator.return_value
                mock_generator.get_pending_tasks.return_value = mock_tasks

                result = loop._fetch_generated_tasks()

                # Verify get_pending_tasks was called with configured limit
                mock_generator.get_pending_tasks.assert_called_once_with(status="pending", limit=5)

        assert len(result) == 5, "Should return all tasks up to configured limit"

    def test_no_getattr_fallback_for_max_tasks(self):
        """Verify direct property access works without getattr fallback.

        The fix changes from:
            getattr(settings, 'generated_task_max_per_run', 3)
        To:
            settings.task_generation_max_tasks_per_run

        Direct access is preferred because:
        1. Fails fast if property is missing (catches typos)
        2. Type checkers can validate property exists
        3. Uses configured value (10) instead of hardcoded fallback (3)
        """
        # Direct access should work without raising AttributeError
        value = settings.task_generation_max_tasks_per_run
        assert isinstance(value, int), "Property should be an integer"
        assert value >= 0, "Property should be non-negative"


class TestMaxTasksConfigDefaults:
    """Test default values for max tasks config."""

    def test_task_generation_max_tasks_per_run_default_is_10(self):
        """Verify default is 10 (not the old hardcoded fallback of 3)."""
        from autopack.config import Settings

        fresh_settings = Settings()
        assert fresh_settings.task_generation_max_tasks_per_run == 10, (
            "task_generation_max_tasks_per_run should default to 10. "
            "The old getattr fallback used 3, which was too restrictive."
        )

    def test_max_tasks_can_be_configured_via_env(self):
        """Verify max tasks can be set via environment variable."""
        import os

        with patch.dict(os.environ, {"AUTOPACK_TASK_GENERATION_MAX_TASKS": "15"}):
            from autopack.config import Settings

            fresh_settings = Settings()
            assert fresh_settings.task_generation_max_tasks_per_run == 15, (
                "task_generation_max_tasks_per_run should be configurable "
                "via AUTOPACK_TASK_GENERATION_MAX_TASKS env var"
            )
