"""Unit tests for executor.backlog_maintenance module.

Tests for the BacklogMaintenance class which handles backlog cleanup,
stuck phase detection, and health monitoring during autonomous execution.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from autopack.executor.backlog_maintenance import BacklogMaintenance
from autopack.maintenance_auditor import AuditorDecision


class TestBacklogMaintenanceInit:
    """Tests for BacklogMaintenance initialization."""

    def test_init_stores_executor_reference(self):
        """BacklogMaintenance stores reference to executor."""
        mock_executor = Mock()

        bm = BacklogMaintenance(mock_executor)

        assert bm.executor is mock_executor


class TestRunMaintenanceBasic:
    """Basic tests for run_maintenance method."""

    def test_run_maintenance_handles_missing_plan_file(self, tmp_path: Path, caplog):
        """Missing plan file logs error and returns early."""
        mock_executor = Mock()
        bm = BacklogMaintenance(mock_executor)

        plan_path = tmp_path / "nonexistent.json"

        with caplog.at_level(logging.ERROR):
            bm.run_maintenance(plan_path=plan_path)

        # Should log error about missing file
        assert any("Failed to load plan" in record.message for record in caplog.records)

    def test_run_maintenance_handles_invalid_json(self, tmp_path: Path, caplog):
        """Invalid JSON in plan file logs error and returns early."""
        mock_executor = Mock()
        bm = BacklogMaintenance(mock_executor)

        plan_path = tmp_path / "invalid.json"
        plan_path.write_text("not valid json {{{")

        with caplog.at_level(logging.ERROR):
            bm.run_maintenance(plan_path=plan_path)

        # Should log error about JSON parsing
        assert any("Failed to load plan" in record.message for record in caplog.records)

    @patch("autopack.executor.backlog_maintenance.audit_evaluate")
    def test_run_maintenance_empty_phases(self, mock_audit, tmp_path: Path):
        """Empty phases list processes without error."""
        mock_executor = Mock()
        mock_executor.run_id = "test-run-123"
        mock_executor.workspace = str(tmp_path)
        mock_executor._load_project_learning_context = Mock()

        bm = BacklogMaintenance(mock_executor)

        plan_path = tmp_path / "plan.json"
        plan_path.write_text(json.dumps({"phases": []}))

        # Should not raise
        bm.run_maintenance(plan_path=plan_path, apply=False)

        # Auditor should not be called with no phases
        mock_audit.assert_not_called()


class TestRunMaintenanceWithPhases:
    """Tests for run_maintenance with actual phase processing."""

    @pytest.fixture
    def mock_executor(self, tmp_path: Path):
        """Create a mock executor with required attributes."""
        executor = Mock()
        executor.run_id = "test-run-123"
        executor.workspace = str(tmp_path)
        executor.diagnostics_agent = Mock()
        executor.diagnostics_agent.run_diagnostics = Mock(
            return_value=Mock(ledger_summary="Test diagnostics summary")
        )
        executor._record_decision_entry = Mock()
        executor._load_project_learning_context = Mock()
        return executor

    @pytest.fixture
    def sample_plan(self, tmp_path: Path):
        """Create a sample plan file."""
        plan = {
            "phases": [
                {
                    "id": "backlog-test-item",
                    "description": "Test maintenance item",
                    "scope": {"paths": ["src/"]},
                    "metadata": {"backlog_summary": "Fix a test bug"},
                }
            ]
        }
        plan_path = tmp_path / "plan.json"
        plan_path.write_text(json.dumps(plan))
        return plan_path

    @patch("autopack.executor.backlog_maintenance.audit_evaluate")
    def test_run_maintenance_processes_single_phase(
        self, mock_audit, mock_executor, sample_plan, tmp_path
    ):
        """Single phase is processed through diagnostics and audit."""
        mock_audit.return_value = AuditorDecision(
            verdict="approve", reasons=["All checks passed"]
        )

        bm = BacklogMaintenance(mock_executor)
        bm.run_maintenance(plan_path=sample_plan, apply=False)

        # Verify diagnostics were run
        mock_executor.diagnostics_agent.run_diagnostics.assert_called_once()

        # Verify auditor was called
        mock_audit.assert_called_once()

        # Verify decision was recorded
        mock_executor._record_decision_entry.assert_called_once()

    @patch("autopack.executor.backlog_maintenance.audit_evaluate")
    def test_run_maintenance_records_audit_decision(
        self, mock_audit, mock_executor, sample_plan
    ):
        """Audit decision is recorded via executor."""
        mock_audit.return_value = AuditorDecision(
            verdict="require_human", reasons=["Large change size"]
        )

        bm = BacklogMaintenance(mock_executor)
        bm.run_maintenance(plan_path=sample_plan, apply=False)

        # Check decision entry was recorded with correct values
        call_args = mock_executor._record_decision_entry.call_args
        assert call_args.kwargs["trigger"] == "backlog_maintenance"
        assert "audit:require_human" in call_args.kwargs["choice"]

    @patch("autopack.executor.backlog_maintenance.audit_evaluate")
    @patch("autopack.executor.backlog_maintenance.create_git_checkpoint")
    def test_run_maintenance_creates_checkpoint_when_apply_enabled(
        self, mock_checkpoint, mock_audit, mock_executor, sample_plan
    ):
        """Git checkpoint is created when apply=True and checkpoint=True."""
        mock_checkpoint.return_value = (True, "abc123")
        mock_audit.return_value = AuditorDecision(
            verdict="approve", reasons=["All checks passed"]
        )

        bm = BacklogMaintenance(mock_executor)
        bm.run_maintenance(plan_path=sample_plan, apply=True, checkpoint=True)

        # Verify checkpoint was attempted
        mock_checkpoint.assert_called_once()

    @patch("autopack.executor.backlog_maintenance.audit_evaluate")
    def test_run_maintenance_no_apply_without_patch(
        self, mock_audit, mock_executor, sample_plan, tmp_path
    ):
        """Apply is not attempted when no patch file exists."""
        mock_audit.return_value = AuditorDecision(
            verdict="approve", reasons=["All checks passed"]
        )

        bm = BacklogMaintenance(mock_executor)
        bm.run_maintenance(
            plan_path=sample_plan,
            apply=True,
            patch_dir=tmp_path / "nonexistent_patches",
            checkpoint=False,
        )

        # Verify processing completed (decision was recorded)
        mock_executor._record_decision_entry.assert_called_once()

    @patch("autopack.executor.backlog_maintenance.GovernedApplyPath")
    @patch("autopack.executor.backlog_maintenance.audit_evaluate")
    @patch("autopack.executor.backlog_maintenance.create_git_checkpoint")
    def test_run_maintenance_no_apply_when_rejected(
        self, mock_checkpoint, mock_audit, mock_gap, mock_executor, sample_plan, tmp_path
    ):
        """Apply is not attempted when auditor rejects."""
        mock_audit.return_value = AuditorDecision(
            verdict="reject", reasons=["Unsafe changes detected"]
        )
        mock_checkpoint.return_value = (True, "abc123")

        # Create a patch file
        patch_dir = tmp_path / "patches"
        patch_dir.mkdir()
        patch_file = patch_dir / "backlog-test-item.patch"
        patch_file.write_text("+++ b/file.py\n+new line\n")

        bm = BacklogMaintenance(mock_executor)
        bm.run_maintenance(
            plan_path=sample_plan,
            apply=True,
            patch_dir=patch_dir,
            checkpoint=True,
        )

        # GovernedApplyPath should NOT be instantiated when verdict is reject
        mock_gap.assert_not_called()


class TestRunMaintenanceAutoApplyLowRisk:
    """Tests for auto_apply_low_risk behavior."""

    @pytest.fixture
    def mock_executor(self, tmp_path: Path):
        """Create a mock executor with required attributes."""
        executor = Mock()
        executor.run_id = "test-run-123"
        executor.workspace = str(tmp_path)
        executor.diagnostics_agent = Mock()
        executor.diagnostics_agent.run_diagnostics = Mock(
            return_value=Mock(ledger_summary="Test diagnostics summary")
        )
        executor._record_decision_entry = Mock()
        executor._load_project_learning_context = Mock()
        return executor

    @patch("autopack.executor.backlog_maintenance.GovernedApplyPath")
    @patch("autopack.executor.backlog_maintenance.audit_evaluate")
    @patch("autopack.executor.backlog_maintenance.create_git_checkpoint")
    def test_auto_apply_low_risk_skips_large_patches(
        self, mock_checkpoint, mock_audit, mock_gap, mock_executor, tmp_path
    ):
        """Auto-apply low risk skips patches exceeding size limits."""
        # Setup plan with phase
        plan = {"phases": [{"id": "test-phase", "description": "Test", "scope": {}}]}
        plan_path = tmp_path / "plan.json"
        plan_path.write_text(json.dumps(plan))

        # Create large patch (exceeds max_files)
        patch_dir = tmp_path / "patches"
        patch_dir.mkdir()
        patch_file = patch_dir / "test-phase.patch"
        # Create patch with many files
        lines = []
        for i in range(15):
            lines.append(f"--- a/file{i}.py")
            lines.append(f"+++ b/file{i}.py")
            lines.append("+change")
        patch_file.write_text("\n".join(lines))

        mock_checkpoint.return_value = (True, "abc123")
        mock_audit.return_value = AuditorDecision(verdict="approve", reasons=["OK"])

        bm = BacklogMaintenance(mock_executor)
        bm.run_maintenance(
            plan_path=plan_path,
            apply=True,
            patch_dir=patch_dir,
            checkpoint=True,
            max_files=10,
            auto_apply_low_risk=True,
        )

        # GovernedApplyPath should NOT be instantiated due to size guard
        mock_gap.assert_not_called()


class TestRunMaintenanceSummaryWriting:
    """Tests for summary file writing."""

    @pytest.fixture
    def mock_executor(self, tmp_path: Path):
        """Create a mock executor with required attributes."""
        executor = Mock()
        executor.run_id = "test-run-123"
        executor.workspace = str(tmp_path)
        executor.diagnostics_agent = Mock()
        executor.diagnostics_agent.run_diagnostics = Mock(
            return_value=Mock(ledger_summary="Test diagnostics summary")
        )
        executor._record_decision_entry = Mock()
        executor._load_project_learning_context = Mock()
        return executor

    @patch("autopack.executor.backlog_maintenance.audit_evaluate")
    def test_run_maintenance_completes_without_error(
        self, mock_audit, mock_executor, tmp_path
    ):
        """Summary processing completes without error."""
        plan = {"phases": [{"id": "test-phase", "description": "Test"}]}
        plan_path = tmp_path / "plan.json"
        plan_path.write_text(json.dumps(plan))

        mock_audit.return_value = AuditorDecision(verdict="approve", reasons=["OK"])

        bm = BacklogMaintenance(mock_executor)
        # Should not raise
        bm.run_maintenance(plan_path=plan_path, apply=False)

        # Verify learning context was loaded (called at end of maintenance)
        mock_executor._load_project_learning_context.assert_called_once()


class TestRunMaintenanceMultiplePhases:
    """Tests for processing multiple phases."""

    @pytest.fixture
    def mock_executor(self, tmp_path: Path):
        """Create a mock executor with required attributes."""
        executor = Mock()
        executor.run_id = "test-run-123"
        executor.workspace = str(tmp_path)
        executor.diagnostics_agent = Mock()
        executor.diagnostics_agent.run_diagnostics = Mock(
            return_value=Mock(ledger_summary="Test diagnostics summary")
        )
        executor._record_decision_entry = Mock()
        executor._load_project_learning_context = Mock()
        return executor

    @patch("autopack.executor.backlog_maintenance.audit_evaluate")
    def test_run_maintenance_processes_all_phases(
        self, mock_audit, mock_executor, tmp_path
    ):
        """All phases in plan are processed."""
        plan = {
            "phases": [
                {"id": "phase-1", "description": "First"},
                {"id": "phase-2", "description": "Second"},
                {"id": "phase-3", "description": "Third"},
            ]
        }
        plan_path = tmp_path / "plan.json"
        plan_path.write_text(json.dumps(plan))

        mock_audit.return_value = AuditorDecision(verdict="approve", reasons=["OK"])

        bm = BacklogMaintenance(mock_executor)
        bm.run_maintenance(plan_path=plan_path, apply=False)

        # Verify diagnostics ran for all phases
        assert mock_executor.diagnostics_agent.run_diagnostics.call_count == 3

        # Verify decisions recorded for all phases
        assert mock_executor._record_decision_entry.call_count == 3

        # Verify each phase was processed (by checking decision entry calls)
        decision_calls = mock_executor._record_decision_entry.call_args_list
        phase_ids = [call.kwargs.get("phase_id") for call in decision_calls]
        assert phase_ids == ["phase-1", "phase-2", "phase-3"]


class TestRunMaintenanceDefaultPaths:
    """Tests for default allowed/protected paths behavior."""

    @pytest.fixture
    def mock_executor(self, tmp_path: Path):
        """Create a mock executor with required attributes."""
        executor = Mock()
        executor.run_id = "test-run-123"
        executor.workspace = str(tmp_path)
        executor.diagnostics_agent = Mock()
        executor.diagnostics_agent.run_diagnostics = Mock(
            return_value=Mock(ledger_summary="Test diagnostics summary")
        )
        executor._record_decision_entry = Mock()
        executor._load_project_learning_context = Mock()
        return executor

    @patch("autopack.executor.backlog_maintenance.audit_evaluate")
    def test_default_allowed_paths_used(self, mock_audit, mock_executor, tmp_path):
        """Default allowed paths are used when none specified."""
        plan = {"phases": [{"id": "test", "description": "Test"}]}
        plan_path = tmp_path / "plan.json"
        plan_path.write_text(json.dumps(plan))

        mock_audit.return_value = AuditorDecision(verdict="approve", reasons=["OK"])

        bm = BacklogMaintenance(mock_executor)
        bm.run_maintenance(plan_path=plan_path, apply=False)

        # Check auditor was called with default paths
        call_args = mock_audit.call_args
        auditor_input = call_args[0][0]
        assert "src/autopack/" in auditor_input.allowed_paths

    @patch("autopack.executor.backlog_maintenance.audit_evaluate")
    def test_custom_allowed_paths_override_defaults(
        self, mock_audit, mock_executor, tmp_path
    ):
        """Custom allowed paths override defaults."""
        plan = {"phases": [{"id": "test", "description": "Test"}]}
        plan_path = tmp_path / "plan.json"
        plan_path.write_text(json.dumps(plan))

        mock_audit.return_value = AuditorDecision(verdict="approve", reasons=["OK"])

        bm = BacklogMaintenance(mock_executor)
        bm.run_maintenance(
            plan_path=plan_path,
            apply=False,
            allowed_paths=["custom/path/", "another/path/"],
        )

        # Check auditor was called with custom paths
        call_args = mock_audit.call_args
        auditor_input = call_args[0][0]
        assert "custom/path/" in auditor_input.allowed_paths
        assert "another/path/" in auditor_input.allowed_paths
