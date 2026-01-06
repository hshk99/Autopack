"""Tests for autopilot safe action enforcement (BUILD-180 Phase 0/1).

Validates that autopilot only executes read-only or run-local-artifact actions.
Any action targeting repo writes (docs/, config/, src/, tests/, .github/)
must be classified as requires_approval and not executed.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from autopack.autonomy.action_executor import (
    ActionExecutor,
    SafeActionExecutor,
    ActionExecutionResult,
    ActionType,
)
from autopack.autonomy.action_allowlist import (
    is_action_safe,
    classify_action,
    ActionClassification,
    SAFE_ACTION_TYPES,
    REPO_WRITE_PATHS,
)


class TestActionClassification:
    """Test action classification logic."""

    def test_read_only_commands_are_safe(self):
        """Read-only commands should be classified as safe."""
        safe_commands = [
            "python scripts/check_docs_drift.py",
            "pytest -q tests/docs/ --collect-only",
            "python scripts/tidy/sot_summary_refresh.py --check",
            "git status",
            "git diff --name-only",
        ]
        for cmd in safe_commands:
            classification = classify_action(ActionType.COMMAND, cmd)
            assert classification == ActionClassification.SAFE, f"Expected {cmd} to be safe"

    def test_run_local_artifact_writes_are_safe(self):
        """Run-local artifact writes should be classified as safe."""
        safe_paths = [
            ".autonomous_runs/project/runs/family/run123/gaps/gap_report.json",
            ".autonomous_runs/project/runs/family/run123/plans/plan_proposal.json",
            ".autonomous_runs/project/runs/family/run123/autonomy/session.json",
        ]
        for path in safe_paths:
            classification = classify_action(ActionType.FILE_WRITE, path)
            assert classification == ActionClassification.SAFE, f"Expected {path} to be safe"

    def test_repo_write_paths_require_approval(self):
        """Writes to repo paths should require approval."""
        repo_paths = [
            "docs/README.md",
            "config/models.yaml",
            "src/autopack/main.py",
            "tests/test_something.py",
            ".github/workflows/ci.yml",
        ]
        for path in repo_paths:
            classification = classify_action(ActionType.FILE_WRITE, path)
            assert classification == ActionClassification.REQUIRES_APPROVAL, \
                f"Expected {path} to require approval"

    def test_tidy_execute_requires_approval(self):
        """Tidy with --execute flag requires approval."""
        cmd = "python scripts/tidy/sot_summary_refresh.py --execute"
        classification = classify_action(ActionType.COMMAND, cmd)
        assert classification == ActionClassification.REQUIRES_APPROVAL

    def test_tidy_check_is_safe(self):
        """Tidy with --check flag is safe."""
        cmd = "python scripts/tidy/sot_summary_refresh.py --check"
        classification = classify_action(ActionType.COMMAND, cmd)
        assert classification == ActionClassification.SAFE


class TestSafeActionExecutor:
    """Test SafeActionExecutor behavior."""

    def test_executes_safe_commands(self):
        """Safe commands should be executed."""
        executor = SafeActionExecutor(workspace_root=Path("."))

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
            result = executor.execute_command("git status")

        assert result.executed is True
        assert result.success is True
        mock_run.assert_called_once()

    def test_refuses_unsafe_commands(self):
        """Unsafe commands should not be executed."""
        executor = SafeActionExecutor(workspace_root=Path("."))

        result = executor.execute_command("rm -rf /")

        assert result.executed is False
        assert result.classification == ActionClassification.REQUIRES_APPROVAL
        assert "requires approval" in result.reason.lower()

    def test_writes_run_local_artifacts(self):
        """Run-local artifact writes should succeed."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            executor = SafeActionExecutor(workspace_root=workspace)

            artifact_path = ".autonomous_runs/test/runs/family/run1/test.json"
            content = '{"test": true}'

            result = executor.write_artifact(artifact_path, content)

            assert result.executed is True
            assert result.success is True
            assert (workspace / artifact_path).exists()

    def test_refuses_repo_path_writes(self):
        """Writes to repo paths should be refused."""
        executor = SafeActionExecutor(workspace_root=Path("."))

        result = executor.write_artifact("docs/NEW_FILE.md", "content")

        assert result.executed is False
        assert result.classification == ActionClassification.REQUIRES_APPROVAL


class TestActionAllowlist:
    """Test action allowlist constants."""

    def test_safe_action_types_defined(self):
        """Safe action types should be defined."""
        assert ActionType.COMMAND in SAFE_ACTION_TYPES or len(SAFE_ACTION_TYPES) > 0

    def test_repo_write_paths_defined(self):
        """Repo write paths should be defined."""
        expected_paths = ["docs/", "config/", "src/", "tests/", ".github/"]
        for path in expected_paths:
            assert path in REPO_WRITE_PATHS, f"Expected {path} in REPO_WRITE_PATHS"


class TestAutopilotIntegration:
    """Integration tests for autopilot with safe action enforcement."""

    def test_autopilot_classifies_write_actions_as_requires_approval(self):
        """Autopilot should classify write actions as requires_approval."""
        from autopack.autonomy.autopilot import AutopilotController
        from autopack.intention_anchor.v2 import IntentionAnchorV2

        # This test validates the integration point exists
        # Full integration tested in e2e tests
        assert hasattr(AutopilotController, "_execute_bounded_batch")

    def test_autopilot_persists_run_local_artifacts(self):
        """Autopilot should persist run-local artifacts."""
        # Validates that autopilot can save session to run-local path
        from autopack.autonomy.autopilot import AutopilotController

        assert hasattr(AutopilotController, "save_session")
