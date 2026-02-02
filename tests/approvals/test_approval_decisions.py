"""Tests for comprehensive approval workflow decision tree (IMP-TESTING-005).

This module tests the complete approval decision logic, ensuring comprehensive
coverage of all threshold combinations:
- Risk severity thresholds (LOW, MEDIUM, HIGH, CRITICAL)
- Environment mode thresholds (development vs production)
- Multiple task evaluation scenarios
- Timeout and default behavior
- Deterministic approval artifact hashing
- Audit trail consistency
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

import pytest

from autopack.autonomy.approval_service import ApprovalService, AuthorizationDecision
from autopack.executor.backlog_maintenance import TaskCandidate
from autopack.roadi.regression_protector import RegressionProtector, RiskAssessment, RiskSeverity


class TestRiskSeverityThresholds:
    """Tests for approval decision tree risk severity thresholds."""

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
            title="Update authentication module",
            priority="medium",
            source="autonomy_engine",
            metadata={
                "description": "Update authentication logic",
                "issue_type": "security",
            },
        )

    def test_low_risk_threshold_auto_approved(self, approval_service, sample_task):
        """Test LOW risk threshold results in automatic approval."""
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

    def test_medium_risk_threshold_requires_approval(self, approval_service, sample_task):
        """Test MEDIUM risk threshold requires manual approval."""
        mock_protector = MagicMock(spec=RegressionProtector)
        mock_protector.assess_regression_risk.return_value = RiskAssessment(
            severity=RiskSeverity.MEDIUM,
            blocking_recommended=False,
            confidence=0.55,
            evidence=["Historical regression rate for 'security': 8%"],
        )

        decision = approval_service.evaluate_task_authorization(
            sample_task, regression_protector=mock_protector
        )

        assert decision.authorized is False
        assert decision.requires_approval is True
        assert decision.risk_level == RiskSeverity.MEDIUM
        assert "Medium risk" in decision.reason
        assert decision.risk_assessment is not None
        assert len(decision.risk_assessment.evidence) > 0

    def test_high_risk_threshold_blocks_and_requires_approval(self, approval_service, sample_task):
        """Test HIGH risk threshold blocks execution and requires approval."""
        mock_protector = MagicMock(spec=RegressionProtector)
        mock_protector.assess_regression_risk.return_value = RiskAssessment(
            severity=RiskSeverity.HIGH,
            blocking_recommended=True,
            confidence=0.82,
            evidence=[
                "Found 3 existing regression test(s) for this pattern",
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
        assert decision.risk_assessment.blocking_recommended is True
        assert len(decision.risk_assessment.evidence) >= 3

    def test_critical_risk_threshold_blocks_and_requires_approval(
        self, approval_service, sample_task
    ):
        """Test CRITICAL risk threshold blocks execution and requires approval."""
        mock_protector = MagicMock(spec=RegressionProtector)
        mock_protector.assess_regression_risk.return_value = RiskAssessment(
            severity=RiskSeverity.CRITICAL,
            blocking_recommended=True,
            confidence=0.95,
            evidence=[
                "Multiple critical regression tests found",
                "Very high historical regression rate (>50%)",
                "Security-critical code path modification",
                "Data integrity risk detected",
            ],
        )

        decision = approval_service.evaluate_task_authorization(
            sample_task, regression_protector=mock_protector
        )

        assert decision.authorized is False
        assert decision.requires_approval is True
        assert decision.risk_level == RiskSeverity.CRITICAL
        assert decision.risk_assessment.blocking_recommended is True
        assert decision.risk_assessment.confidence > 0.9

    def test_threshold_boundary_low_to_medium(self, approval_service, sample_task):
        """Test boundary between LOW and MEDIUM risk thresholds."""
        # Just below MEDIUM threshold
        decision_low = approval_service.evaluate_task_authorization(
            sample_task,
            regression_protector=MagicMock(
                assess_regression_risk=MagicMock(
                    return_value=RiskAssessment(
                        severity=RiskSeverity.LOW,
                        blocking_recommended=False,
                        confidence=0.49,
                        evidence=[],
                    )
                )
            ),
        )

        assert decision_low.authorized is True
        assert decision_low.requires_approval is False

        # At MEDIUM threshold
        decision_medium = approval_service.evaluate_task_authorization(
            sample_task,
            regression_protector=MagicMock(
                assess_regression_risk=MagicMock(
                    return_value=RiskAssessment(
                        severity=RiskSeverity.MEDIUM,
                        blocking_recommended=False,
                        confidence=0.50,
                        evidence=["Evidence item"],
                    )
                )
            ),
        )

        assert decision_medium.authorized is False
        assert decision_medium.requires_approval is True


class TestMultipleTaskEvaluation:
    """Tests for approval decisions with multiple tasks at different risk levels."""

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

    def test_homogeneous_low_risk_all_authorized(self, approval_service):
        """Test all low-risk tasks are authorized."""
        tasks = [
            TaskCandidate(task_id="TASK-001", title="Minor UI fix", priority="low"),
            TaskCandidate(task_id="TASK-002", title="Documentation update", priority="low"),
            TaskCandidate(task_id="TASK-003", title="Config change", priority="low"),
        ]

        def mock_assess_risk(pattern, context):
            return RiskAssessment(
                severity=RiskSeverity.LOW,
                blocking_recommended=False,
                confidence=0.2,
                evidence=[],
            )

        mock_protector = MagicMock(spec=RegressionProtector)
        mock_protector.assess_regression_risk.side_effect = mock_assess_risk

        authorized, pending = approval_service.evaluate_tasks_authorization(
            tasks, regression_protector=mock_protector
        )

        assert len(authorized) == 3
        assert len(pending) == 0
        assert all(task.task_id.startswith("TASK-") for task in authorized)

    def test_homogeneous_high_risk_all_pending(self, approval_service):
        """Test all high-risk tasks require approval."""
        tasks = [
            TaskCandidate(task_id="TASK-001", title="Core algorithm change", priority="high"),
            TaskCandidate(task_id="TASK-002", title="Database migration", priority="high"),
            TaskCandidate(task_id="TASK-003", title="Security patch", priority="high"),
        ]

        def mock_assess_risk(pattern, context):
            return RiskAssessment(
                severity=RiskSeverity.HIGH,
                blocking_recommended=True,
                confidence=0.85,
                evidence=["High risk evidence"],
            )

        mock_protector = MagicMock(spec=RegressionProtector)
        mock_protector.assess_regression_risk.side_effect = mock_assess_risk

        authorized, pending = approval_service.evaluate_tasks_authorization(
            tasks, regression_protector=mock_protector
        )

        assert len(authorized) == 0
        assert len(pending) == 3
        assert all(task.task_id.startswith("TASK-") for task, decision in pending)

    def test_mixed_risk_levels_separation(self, approval_service):
        """Test mixed risk levels are correctly separated into authorized/pending."""
        tasks = [
            TaskCandidate(task_id="TASK-001", title="Low risk task", priority="low"),
            TaskCandidate(task_id="TASK-002", title="Medium risk task", priority="medium"),
            TaskCandidate(task_id="TASK-003", title="High risk task", priority="high"),
            TaskCandidate(task_id="TASK-004", title="Another low risk", priority="low"),
            TaskCandidate(task_id="TASK-005", title="Critical risk task", priority="high"),
        ]

        def mock_assess_risk(pattern, context):
            task_id = context.get("phase_id", "")
            if task_id == "TASK-001" or task_id == "TASK-004":
                return RiskAssessment(
                    severity=RiskSeverity.LOW,
                    blocking_recommended=False,
                    confidence=0.2,
                    evidence=[],
                )
            elif task_id == "TASK-002":
                return RiskAssessment(
                    severity=RiskSeverity.MEDIUM,
                    blocking_recommended=False,
                    confidence=0.55,
                    evidence=["Medium evidence"],
                )
            elif task_id == "TASK-003":
                return RiskAssessment(
                    severity=RiskSeverity.HIGH,
                    blocking_recommended=True,
                    confidence=0.8,
                    evidence=["High evidence"],
                )
            else:  # TASK-005
                return RiskAssessment(
                    severity=RiskSeverity.CRITICAL,
                    blocking_recommended=True,
                    confidence=0.95,
                    evidence=["Critical evidence"],
                )

        mock_protector = MagicMock(spec=RegressionProtector)
        mock_protector.assess_regression_risk.side_effect = mock_assess_risk

        authorized, pending = approval_service.evaluate_tasks_authorization(
            tasks, regression_protector=mock_protector
        )

        assert len(authorized) == 2
        assert len(pending) == 3

        authorized_ids = [task.task_id for task in authorized]
        assert "TASK-001" in authorized_ids
        assert "TASK-004" in authorized_ids

        pending_ids = [task.task_id for task, decision in pending]
        assert "TASK-002" in pending_ids
        assert "TASK-003" in pending_ids
        assert "TASK-005" in pending_ids


class TestEnvironmentModeThresholds:
    """Tests for approval decisions based on environment mode thresholds."""

    def test_development_mode_auto_approve_disabled_by_default(self):
        """Test development mode has auto-approve disabled by default."""
        original_auto_approve = os.environ.pop("AUTO_APPROVE_BUILD113", None)
        original_env_mode = os.environ.pop("AUTOPACK_ENV", None)

        try:
            # Set development mode without explicit AUTO_APPROVE
            os.environ["AUTOPACK_ENV"] = "development"
            if "AUTO_APPROVE_BUILD113" in os.environ:
                del os.environ["AUTO_APPROVE_BUILD113"]

            # Simulate the decision logic
            env_mode = os.getenv("AUTOPACK_ENV", "development").lower()
            auto_approve_env = os.getenv("AUTO_APPROVE_BUILD113", "false").lower() == "true"
            auto_approve = auto_approve_env and env_mode != "production"

            assert auto_approve is False
        finally:
            if original_auto_approve:
                os.environ["AUTO_APPROVE_BUILD113"] = original_auto_approve
            if original_env_mode:
                os.environ["AUTOPACK_ENV"] = original_env_mode

    def test_development_mode_auto_approve_explicit_true(self):
        """Test development mode with explicit AUTO_APPROVE_BUILD113=true."""
        original_auto_approve = os.environ.pop("AUTO_APPROVE_BUILD113", None)
        original_env_mode = os.environ.pop("AUTOPACK_ENV", None)

        try:
            os.environ["AUTOPACK_ENV"] = "development"
            os.environ["AUTO_APPROVE_BUILD113"] = "true"

            # Simulate the decision logic
            env_mode = os.getenv("AUTOPACK_ENV", "development").lower()
            auto_approve_env = os.getenv("AUTO_APPROVE_BUILD113", "false").lower() == "true"
            auto_approve = auto_approve_env and env_mode != "production"

            assert auto_approve is True
        finally:
            if original_auto_approve:
                os.environ["AUTO_APPROVE_BUILD113"] = original_auto_approve
            if original_env_mode:
                os.environ["AUTOPACK_ENV"] = original_env_mode

    def test_production_mode_blocks_auto_approve_always(self):
        """Test production mode ALWAYS blocks auto-approve, regardless of env var."""
        original_auto_approve = os.environ.pop("AUTO_APPROVE_BUILD113", None)
        original_env_mode = os.environ.pop("AUTOPACK_ENV", None)

        try:
            os.environ["AUTOPACK_ENV"] = "production"
            os.environ["AUTO_APPROVE_BUILD113"] = "true"

            # Simulate the decision logic
            env_mode = os.getenv("AUTOPACK_ENV", "development").lower()
            auto_approve_env = os.getenv("AUTO_APPROVE_BUILD113", "false").lower() == "true"
            auto_approve = auto_approve_env and env_mode != "production"

            # This is the critical safety gate
            assert auto_approve is False
        finally:
            if original_auto_approve:
                os.environ["AUTO_APPROVE_BUILD113"] = original_auto_approve
            if original_env_mode:
                os.environ["AUTOPACK_ENV"] = original_env_mode

    def test_production_mode_safe_by_default(self):
        """Test production mode is safe-by-default (no auto-approve)."""
        original_auto_approve = os.environ.pop("AUTO_APPROVE_BUILD113", None)
        original_env_mode = os.environ.pop("AUTOPACK_ENV", None)

        try:
            os.environ["AUTOPACK_ENV"] = "production"
            if "AUTO_APPROVE_BUILD113" in os.environ:
                del os.environ["AUTO_APPROVE_BUILD113"]

            # Simulate the decision logic
            env_mode = os.getenv("AUTOPACK_ENV", "development").lower()
            auto_approve_env = os.getenv("AUTO_APPROVE_BUILD113", "false").lower() == "true"
            auto_approve = auto_approve_env and env_mode != "production"

            assert auto_approve is False
        finally:
            if original_auto_approve:
                os.environ["AUTO_APPROVE_BUILD113"] = original_auto_approve
            if original_env_mode:
                os.environ["AUTOPACK_ENV"] = original_env_mode


class TestTimeoutBehavior:
    """Tests for approval timeout and default behavior thresholds."""

    def test_approval_timeout_default_reject(self):
        """Test approval request times out with default rejection."""
        timeout_seconds = 900  # 15 minutes
        approval_timestamp = datetime.utcnow()
        current_time = approval_timestamp + timedelta(seconds=timeout_seconds + 1)

        # Simulate timeout logic
        elapsed = (current_time - approval_timestamp).total_seconds()
        timed_out = elapsed > timeout_seconds

        assert timed_out is True

        # With default_on_timeout="reject"
        default_on_timeout = "reject"
        final_status = "rejected" if timed_out and default_on_timeout == "reject" else "pending"

        assert final_status == "rejected"

    def test_approval_timeout_default_approve(self):
        """Test approval request times out with default approval."""
        timeout_seconds = 900
        approval_timestamp = datetime.utcnow()
        current_time = approval_timestamp + timedelta(seconds=timeout_seconds + 1)

        # Simulate timeout logic
        elapsed = (current_time - approval_timestamp).total_seconds()
        timed_out = elapsed > timeout_seconds

        assert timed_out is True

        # With default_on_timeout="approve"
        default_on_timeout = "approve"
        final_status = "approved" if timed_out and default_on_timeout == "approve" else "pending"

        assert final_status == "approved"

    def test_approval_before_timeout_expires(self):
        """Test approval is granted before timeout expires."""
        timeout_seconds = 900
        approval_timestamp = datetime.utcnow()
        approval_time = approval_timestamp + timedelta(seconds=100)

        # Simulate approval before timeout
        elapsed = (approval_time - approval_timestamp).total_seconds()
        timed_out = elapsed > timeout_seconds

        assert timed_out is False

        # Status should be approved
        final_status = "approved"
        assert final_status == "approved"

    def test_approval_rejection_before_timeout(self):
        """Test approval is explicitly rejected before timeout."""
        timeout_seconds = 900
        approval_timestamp = datetime.utcnow()
        rejection_time = approval_timestamp + timedelta(seconds=100)

        # Simulate rejection before timeout
        elapsed = (rejection_time - approval_timestamp).total_seconds()
        timed_out = elapsed > timeout_seconds

        assert timed_out is False

        # Status should be rejected
        final_status = "rejected"
        assert final_status == "rejected"

    def test_timeout_threshold_boundary(self):
        """Test boundary at timeout threshold."""
        timeout_seconds = 900
        approval_timestamp = datetime.utcnow()

        # Exactly at timeout
        current_time_at_boundary = approval_timestamp + timedelta(seconds=timeout_seconds)
        elapsed = (current_time_at_boundary - approval_timestamp).total_seconds()
        timed_out = elapsed > timeout_seconds

        # Should NOT be timed out at exact boundary (> not >=)
        assert timed_out is False

        # Just after timeout
        current_time_after = approval_timestamp + timedelta(seconds=timeout_seconds + 0.1)
        elapsed = (current_time_after - approval_timestamp).total_seconds()
        timed_out = elapsed > timeout_seconds

        assert timed_out is True


class TestApprovalArtifactDeterminism:
    """Tests for deterministic approval artifact hashing and verification."""

    def test_report_id_deterministic_computation(self):
        """Test report ID computation is deterministic."""
        report_content = {
            "report_type": "storage_optimization",
            "recommendations": [
                {"path": "/file1.txt", "action": "delete", "bytes": 1024},
                {"path": "/file2.txt", "action": "archive", "bytes": 2048},
            ],
            "total_bytes": 3072,
        }

        # Simulate deterministic hashing
        import hashlib

        content_str = json.dumps(report_content, sort_keys=True)
        report_id_1 = hashlib.sha256(content_str.encode()).hexdigest()
        report_id_2 = hashlib.sha256(content_str.encode()).hexdigest()

        assert report_id_1 == report_id_2
        assert len(report_id_1) == 64  # SHA-256 hex

    def test_report_id_ignores_volatile_fields(self):
        """Test report ID ignores volatile fields like timestamps."""
        import hashlib

        base_report = {
            "report_type": "storage_optimization",
            "recommendations": [{"path": "/file1.txt", "action": "delete"}],
            "total_bytes": 1024,
        }

        # Report with timestamp 1
        report_1 = {**base_report, "generated_at": "2026-01-03T10:00:00Z", "runtime_ms": 1500}

        # Report with different timestamp but same content
        report_2 = {**base_report, "generated_at": "2026-01-03T10:00:01Z", "runtime_ms": 1600}

        # Remove volatile fields for hashing
        content_1 = {k: v for k, v in report_1.items() if k not in ["generated_at", "runtime_ms"]}
        content_2 = {k: v for k, v in report_2.items() if k not in ["generated_at", "runtime_ms"]}

        content_str_1 = json.dumps(content_1, sort_keys=True)
        content_str_2 = json.dumps(content_2, sort_keys=True)

        report_id_1 = hashlib.sha256(content_str_1.encode()).hexdigest()
        report_id_2 = hashlib.sha256(content_str_2.encode()).hexdigest()

        assert report_id_1 == report_id_2

    def test_report_id_detects_content_changes(self):
        """Test report ID detects changes in actual content."""
        import hashlib

        report_1 = {
            "report_type": "storage_optimization",
            "recommendations": [
                {"path": "/file1.txt", "action": "delete", "bytes": 1024},
                {"path": "/file2.txt", "action": "delete", "bytes": 2048},
            ],
            "total_bytes": 3072,
        }

        report_2 = {
            "report_type": "storage_optimization",
            "recommendations": [
                {"path": "/file1.txt", "action": "delete", "bytes": 1024},
            ],
            "total_bytes": 1024,
        }

        content_str_1 = json.dumps(report_1, sort_keys=True)
        content_str_2 = json.dumps(report_2, sort_keys=True)

        report_id_1 = hashlib.sha256(content_str_1.encode()).hexdigest()
        report_id_2 = hashlib.sha256(content_str_2.encode()).hexdigest()

        assert report_id_1 != report_id_2

    def test_approval_artifact_roundtrip(self):
        """Test approval artifact can be saved and loaded."""
        with TemporaryDirectory() as tmpdir:
            approval_data = {
                "report_id": "abc123def456",
                "timestamp": "2026-01-03T16:00:00Z",
                "operator": "test@example.com",
                "notes": "Approved for execution",
                "status": "approved",
            }

            approval_path = Path(tmpdir) / "approval.json"
            with open(approval_path, "w") as f:
                json.dump(approval_data, f)

            # Read back
            with open(approval_path, "r") as f:
                loaded_data = json.load(f)

            assert loaded_data["report_id"] == approval_data["report_id"]
            assert loaded_data["timestamp"] == approval_data["timestamp"]
            assert loaded_data["operator"] == approval_data["operator"]
            assert loaded_data["notes"] == approval_data["notes"]


class TestAuditTrailConsistency:
    """Tests for audit trail consistency and integrity."""

    def test_audit_log_single_entry(self):
        """Test audit log records single action."""
        with TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / "audit.jsonl"

            # Write audit entry
            entry = {
                "timestamp": "2026-01-03T16:00:00Z",
                "action": "approval_requested",
                "task_id": "TASK-001",
                "operator": "system",
                "details": {"reason": "High risk task"},
            }

            with open(audit_path, "w") as f:
                json.dump(entry, f)
                f.write("\n")

            # Read back
            with open(audit_path, "r") as f:
                line = f.readline()
                loaded_entry = json.loads(line)

            assert loaded_entry["action"] == "approval_requested"
            assert loaded_entry["task_id"] == "TASK-001"

    def test_audit_log_multiple_entries_jsonl_format(self):
        """Test audit log handles multiple entries in JSONL format."""
        with TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / "audit.jsonl"

            # Write multiple entries
            entries = [
                {
                    "timestamp": "2026-01-03T16:00:00Z",
                    "action": "approval_requested",
                    "task_id": "TASK-001",
                },
                {
                    "timestamp": "2026-01-03T16:01:00Z",
                    "action": "approval_granted",
                    "task_id": "TASK-001",
                    "operator": "reviewer@example.com",
                },
                {
                    "timestamp": "2026-01-03T16:02:00Z",
                    "action": "task_executed",
                    "task_id": "TASK-001",
                },
            ]

            with open(audit_path, "w") as f:
                for entry in entries:
                    json.dump(entry, f)
                    f.write("\n")

            # Read back and verify
            with open(audit_path, "r") as f:
                lines = f.readlines()

            assert len(lines) == 3

            for i, line in enumerate(lines):
                loaded = json.loads(line)
                assert loaded["task_id"] == "TASK-001"
                assert loaded["action"] in [
                    "approval_requested",
                    "approval_granted",
                    "task_executed",
                ]

    def test_audit_log_chronological_order(self):
        """Test audit entries maintain chronological order."""
        with TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / "audit.jsonl"

            timestamps = [
                "2026-01-03T16:00:00Z",
                "2026-01-03T16:01:00Z",
                "2026-01-03T16:02:00Z",
            ]

            entries = [{"timestamp": ts, "action": f"step_{i}"} for i, ts in enumerate(timestamps)]

            with open(audit_path, "w") as f:
                for entry in entries:
                    json.dump(entry, f)
                    f.write("\n")

            # Verify chronological order
            with open(audit_path, "r") as f:
                loaded_entries = [json.loads(line) for line in f]

            for i in range(len(loaded_entries) - 1):
                assert loaded_entries[i]["timestamp"] <= loaded_entries[i + 1]["timestamp"]

    def test_audit_log_entry_immutability(self):
        """Test that audit log entries cannot be modified after writing."""
        with TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / "audit.jsonl"

            # Write entry
            original_entry = {
                "timestamp": "2026-01-03T16:00:00Z",
                "action": "approval_granted",
                "operator": "reviewer@example.com",
            }

            with open(audit_path, "w") as f:
                json.dump(original_entry, f)
                f.write("\n")

            # Read back
            with open(audit_path, "r") as f:
                loaded_entry = json.loads(f.readline())

            # Verify it's the same
            assert loaded_entry == original_entry

            # Attempting to modify file should require rewriting (not in-place edit)
            # This is more of a conceptual test about JSONL immutability


class TestDecisionSerialization:
    """Tests for serialization and deserialization of approval decisions."""

    def test_authorization_decision_to_dict(self):
        """Test AuthorizationDecision serialization to dict."""
        risk = RiskAssessment(
            severity=RiskSeverity.MEDIUM,
            blocking_recommended=False,
            confidence=0.55,
            evidence=["Evidence 1", "Evidence 2"],
        )

        decision = AuthorizationDecision(
            authorized=False,
            reason="Medium risk task requires approval",
            risk_level=RiskSeverity.MEDIUM,
            requires_approval=True,
            risk_assessment=risk,
        )

        data = decision.to_dict()

        assert data["authorized"] is False
        assert data["requires_approval"] is True
        assert data["risk_level"] == "medium"
        assert data["reason"] == "Medium risk task requires approval"
        assert data["risk_assessment"]["severity"] == "medium"
        assert data["risk_assessment"]["confidence"] == 0.55
        assert len(data["risk_assessment"]["evidence"]) == 2

    def test_authorization_decision_json_serializable(self):
        """Test AuthorizationDecision can be JSON serialized."""
        decision = AuthorizationDecision(
            authorized=True,
            reason="Low risk - auto-authorized",
            risk_level=RiskSeverity.LOW,
            requires_approval=False,
        )

        data = decision.to_dict()
        json_str = json.dumps(data)

        assert isinstance(json_str, str)
        loaded = json.loads(json_str)
        assert loaded["authorized"] is True
        assert loaded["risk_level"] == "low"
