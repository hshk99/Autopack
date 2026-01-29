"""Tests for task execution authorization criteria (IMP-LOOP-030).

This module tests the risk-based authorization gating for auto-execution
of generated tasks, ensuring that:
- Low risk tasks are authorized for auto-execution
- Medium risk tasks require manual approval
- High/Critical risk tasks are blocked and require approval
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pytest

from autopack.autonomy.approval_service import ApprovalService, AuthorizationDecision
from autopack.executor.backlog_maintenance import BacklogMaintenance, TaskCandidate
from autopack.roadi.regression_protector import RegressionProtector, RiskAssessment, RiskSeverity


class TestAuthorizationDecision:
    """Tests for AuthorizationDecision dataclass."""

    def test_authorized_decision_properties(self):
        """Test authorized decision has correct properties."""
        decision = AuthorizationDecision(
            authorized=True,
            reason="Low risk task - authorized for auto-execution",
            risk_level=RiskSeverity.LOW,
            requires_approval=False,
        )

        assert decision.authorized is True
        assert decision.requires_approval is False
        assert decision.risk_level == RiskSeverity.LOW
        assert "Low risk" in decision.reason

    def test_unauthorized_decision_with_risk_assessment(self):
        """Test unauthorized decision includes risk assessment."""
        risk = RiskAssessment(
            severity=RiskSeverity.HIGH,
            blocking_recommended=True,
            confidence=0.8,
            evidence=["Found existing regression tests", "Pattern matches known issue"],
        )

        decision = AuthorizationDecision(
            authorized=False,
            reason="High risk: matches known regression pattern",
            risk_level=RiskSeverity.HIGH,
            requires_approval=True,
            risk_assessment=risk,
        )

        assert decision.authorized is False
        assert decision.requires_approval is True
        assert decision.risk_assessment is not None
        assert decision.risk_assessment.confidence == 0.8

    def test_to_dict_serialization(self):
        """Test serialization to dictionary."""
        risk = RiskAssessment(
            severity=RiskSeverity.MEDIUM,
            blocking_recommended=False,
            confidence=0.5,
            evidence=["Some evidence"],
        )

        decision = AuthorizationDecision(
            authorized=False,
            reason="Medium risk",
            risk_level=RiskSeverity.MEDIUM,
            requires_approval=True,
            risk_assessment=risk,
        )

        data = decision.to_dict()

        assert data["authorized"] is False
        assert data["risk_level"] == "medium"
        assert data["requires_approval"] is True
        assert data["risk_assessment"]["severity"] == "medium"
        assert data["risk_assessment"]["confidence"] == 0.5


class TestApprovalServiceAuthorization:
    """Tests for ApprovalService.evaluate_task_authorization."""

    @pytest.fixture
    def temp_workspace(self):
        """Create temporary workspace for tests."""
        with TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def approval_service(self, temp_workspace):
        """Create ApprovalService instance for tests."""
        return ApprovalService(
            run_id="test-run-001",
            project_id="test-project",
            workspace_root=temp_workspace,
        )

    @pytest.fixture
    def sample_task(self):
        """Create sample TaskCandidate for tests."""
        return TaskCandidate(
            task_id="TASK-001",
            title="Fix performance issue in data processing",
            priority="medium",
            source="telemetry_insights",
            metadata={
                "description": "Optimize data pipeline to reduce latency",
                "issue_type": "performance",
            },
        )

    def test_low_risk_task_is_authorized(self, approval_service, sample_task):
        """Test that low risk tasks are authorized for auto-execution."""
        # Create a mock protector that returns low risk
        mock_protector = MagicMock(spec=RegressionProtector)
        mock_protector.assess_regression_risk.return_value = RiskAssessment(
            severity=RiskSeverity.LOW,
            blocking_recommended=False,
            confidence=0.2,
            evidence=[],
        )

        decision = approval_service.evaluate_task_authorization(
            sample_task, regression_protector=mock_protector
        )

        assert decision.authorized is True
        assert decision.requires_approval is False
        assert decision.risk_level == RiskSeverity.LOW
        assert "Low risk" in decision.reason

    def test_medium_risk_task_requires_approval(self, approval_service, sample_task):
        """Test that medium risk tasks require approval."""
        mock_protector = MagicMock(spec=RegressionProtector)
        mock_protector.assess_regression_risk.return_value = RiskAssessment(
            severity=RiskSeverity.MEDIUM,
            blocking_recommended=False,
            confidence=0.5,
            evidence=["Historical regression rate for 'performance': 10%"],
        )

        decision = approval_service.evaluate_task_authorization(
            sample_task, regression_protector=mock_protector
        )

        assert decision.authorized is False
        assert decision.requires_approval is True
        assert decision.risk_level == RiskSeverity.MEDIUM
        assert "Medium risk" in decision.reason

    def test_high_risk_task_is_blocked(self, approval_service, sample_task):
        """Test that high risk tasks are blocked and require approval."""
        mock_protector = MagicMock(spec=RegressionProtector)
        mock_protector.assess_regression_risk.return_value = RiskAssessment(
            severity=RiskSeverity.HIGH,
            blocking_recommended=True,
            confidence=0.8,
            evidence=[
                "Found 2 existing regression test(s) for this pattern",
                "Pattern matches known fixed regression",
                "Existing fix verified as still valid",
            ],
        )

        decision = approval_service.evaluate_task_authorization(
            sample_task, regression_protector=mock_protector
        )

        assert decision.authorized is False
        assert decision.requires_approval is True
        assert decision.risk_level == RiskSeverity.HIGH
        assert "High risk" in decision.reason

    def test_critical_risk_task_is_blocked(self, approval_service, sample_task):
        """Test that critical risk tasks are blocked and require approval."""
        mock_protector = MagicMock(spec=RegressionProtector)
        mock_protector.assess_regression_risk.return_value = RiskAssessment(
            severity=RiskSeverity.CRITICAL,
            blocking_recommended=True,
            confidence=0.95,
            evidence=[
                "Multiple regression tests found",
                "High historical regression rate",
            ],
        )

        decision = approval_service.evaluate_task_authorization(
            sample_task, regression_protector=mock_protector
        )

        assert decision.authorized is False
        assert decision.requires_approval is True
        assert decision.risk_level == RiskSeverity.CRITICAL

    def test_evaluate_multiple_tasks(self, approval_service):
        """Test evaluating authorization for multiple tasks."""
        tasks = [
            TaskCandidate(task_id="TASK-001", title="Low risk task", priority="low"),
            TaskCandidate(task_id="TASK-002", title="Medium risk task", priority="medium"),
            TaskCandidate(task_id="TASK-003", title="High risk task", priority="high"),
        ]

        # Create mock protector that returns different risks based on task
        def mock_assess_risk(pattern, context):
            task_id = context.get("phase_id", "")
            if task_id == "TASK-001":
                return RiskAssessment(
                    severity=RiskSeverity.LOW,
                    blocking_recommended=False,
                    confidence=0.1,
                )
            elif task_id == "TASK-002":
                return RiskAssessment(
                    severity=RiskSeverity.MEDIUM,
                    blocking_recommended=False,
                    confidence=0.5,
                    evidence=["Medium risk evidence"],
                )
            else:
                return RiskAssessment(
                    severity=RiskSeverity.HIGH,
                    blocking_recommended=True,
                    confidence=0.8,
                    evidence=["High risk evidence"],
                )

        mock_protector = MagicMock(spec=RegressionProtector)
        mock_protector.assess_regression_risk.side_effect = mock_assess_risk

        authorized, pending = approval_service.evaluate_tasks_authorization(
            tasks, regression_protector=mock_protector
        )

        assert len(authorized) == 1
        assert authorized[0].task_id == "TASK-001"

        assert len(pending) == 2
        pending_ids = [task.task_id for task, decision in pending]
        assert "TASK-002" in pending_ids
        assert "TASK-003" in pending_ids


class TestBacklogMaintenanceAuthorization:
    """Tests for BacklogMaintenance authorization in inject_tasks."""

    @pytest.fixture
    def mock_executor(self):
        """Create mock executor for tests."""
        executor = MagicMock()
        executor.run_id = "test-run-001"
        executor.workspace = "/test/workspace"

        # Set up autonomous_loop with _current_run_phases
        executor.autonomous_loop = MagicMock()
        executor.autonomous_loop._current_run_phases = []

        return executor

    @pytest.fixture
    def backlog_maintenance(self, mock_executor):
        """Create BacklogMaintenance instance for tests."""
        return BacklogMaintenance(mock_executor)

    @pytest.fixture
    def sample_tasks(self):
        """Create sample tasks for injection tests."""
        return [
            TaskCandidate(
                task_id="TASK-001",
                title="Fix bug in login flow",
                priority="high",
                source="autonomous_task_generator",
                metadata={"description": "Fix authentication timeout issue"},
            ),
            TaskCandidate(
                task_id="TASK-002",
                title="Optimize database queries",
                priority="medium",
                source="autonomous_task_generator",
                metadata={"description": "Add indexes to improve query performance"},
            ),
        ]

    def test_inject_tasks_with_skip_authorization(self, backlog_maintenance, sample_tasks):
        """Test injection with authorization skipped (for pre-approved tasks)."""
        result = backlog_maintenance.inject_tasks(sample_tasks, skip_authorization=True)

        assert result.success_count == 2
        assert result.failure_count == 0
        assert "TASK-001" in result.injected_ids
        assert "TASK-002" in result.injected_ids

    def test_inject_tasks_low_risk_authorized(self, backlog_maintenance, sample_tasks):
        """Test that low risk tasks are injected without approval."""
        with patch.object(
            RegressionProtector,
            "assess_regression_risk",
            return_value=RiskAssessment(
                severity=RiskSeverity.LOW,
                blocking_recommended=False,
                confidence=0.1,
            ),
        ):
            result = backlog_maintenance.inject_tasks(sample_tasks)

            assert result.success_count == 2
            assert result.failure_count == 0

    def test_inject_tasks_high_risk_blocked(self, backlog_maintenance, sample_tasks):
        """Test that high risk tasks are not injected."""
        with patch.object(
            RegressionProtector,
            "assess_regression_risk",
            return_value=RiskAssessment(
                severity=RiskSeverity.HIGH,
                blocking_recommended=True,
                confidence=0.8,
                evidence=["High risk pattern detected"],
            ),
        ):
            result = backlog_maintenance.inject_tasks(sample_tasks)

            # All tasks should be blocked (in failed_ids)
            assert result.success_count == 0
            assert result.failure_count == 2

    def test_inject_tasks_mixed_risk_levels(self, backlog_maintenance, sample_tasks):
        """Test injection with mixed risk levels."""

        def mock_assess(pattern, context):
            task_id = context.get("phase_id", "")
            if task_id == "TASK-001":
                return RiskAssessment(
                    severity=RiskSeverity.LOW,
                    blocking_recommended=False,
                    confidence=0.1,
                )
            else:
                return RiskAssessment(
                    severity=RiskSeverity.HIGH,
                    blocking_recommended=True,
                    confidence=0.8,
                    evidence=["High risk"],
                )

        with patch.object(RegressionProtector, "assess_regression_risk", side_effect=mock_assess):
            result = backlog_maintenance.inject_tasks(sample_tasks)

            # Only TASK-001 should be injected
            assert result.success_count == 1
            assert result.failure_count == 1
            assert "TASK-001" in result.injected_ids
            assert "TASK-002" in result.failed_ids

    def test_inject_tasks_queues_pending_approvals(self, backlog_maintenance, sample_tasks):
        """Test that blocked tasks are queued for approval when service provided."""
        with TemporaryDirectory() as tmpdir:
            approval_service = ApprovalService(
                run_id="test-run-001",
                project_id="test-project",
                workspace_root=Path(tmpdir),
            )

            with patch.object(
                RegressionProtector,
                "assess_regression_risk",
                return_value=RiskAssessment(
                    severity=RiskSeverity.MEDIUM,
                    blocking_recommended=False,
                    confidence=0.5,
                    evidence=["Medium risk"],
                ),
            ):
                result = backlog_maintenance.inject_tasks(
                    sample_tasks, approval_service=approval_service
                )

                # Tasks should be in pending approval queue
                assert result.failure_count == 2

                # Check approval queue
                pending = approval_service.get_pending_approvals()
                assert len(pending) == 2

                pending_ids = [p.action_id for p in pending]
                assert "TASK-001" in pending_ids
                assert "TASK-002" in pending_ids


class TestRiskBasedAuthorization:
    """Integration tests for risk-based authorization."""

    @pytest.fixture
    def temp_tests_root(self):
        """Create temporary directory for regression tests."""
        with TemporaryDirectory() as tmpdir:
            tests_root = Path(tmpdir) / "tests" / "regression"
            tests_root.mkdir(parents=True)
            yield tests_root

    def test_task_with_existing_regression_test_blocked(self, temp_tests_root):
        """Test that tasks matching existing regression tests are blocked."""
        # Create a regression test file
        test_file = temp_tests_root / "test_regression_task001.py"
        test_file.write_text('''"""Regression test for authentication timeout issue."""
import pytest

def test_authentication_timeout_does_not_recur():
    """Verify authentication timeout issue does not recur."""
    assert True  # Placeholder
''')

        protector = RegressionProtector(tests_root=temp_tests_root)

        # Create a task that matches the regression test
        task = TaskCandidate(
            task_id="TASK-001",
            title="Fix authentication timeout",
            priority="high",
            metadata={"description": "Authentication timeout issue"},
        )

        # Build pattern and assess risk
        pattern = f"{task.title}: {task.metadata.get('description', '')}"
        risk = protector.assess_regression_risk(pattern, {"phase_id": task.task_id})

        # Should be at least medium risk due to pattern match
        assert risk.severity in (RiskSeverity.MEDIUM, RiskSeverity.HIGH, RiskSeverity.CRITICAL)
        assert len(risk.evidence) > 0

    def test_novel_task_is_low_risk(self):
        """Test that tasks with no matching patterns are low risk."""
        with TemporaryDirectory() as tmpdir:
            tests_root = Path(tmpdir) / "tests" / "regression"
            tests_root.mkdir(parents=True)

            protector = RegressionProtector(tests_root=tests_root)

            # Create a task with no matching patterns
            task = TaskCandidate(
                task_id="TASK-999",
                title="Implement new feature XYZ",
                priority="medium",
                metadata={"description": "Add completely new functionality"},
            )

            pattern = f"{task.title}: {task.metadata.get('description', '')}"
            risk = protector.assess_regression_risk(pattern, {"phase_id": task.task_id})

            # Should be low risk with no matching patterns
            assert risk.severity == RiskSeverity.LOW
            assert risk.confidence < 0.5
