"""Contract tests for approval flow module.

These tests verify the approval_flow module behavior contract for PR-EXE-2.
"""

import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass
from enum import Enum

from autopack.executor.approval_flow import (
    ApprovalResult,
    DeletionInfo,
    Build113DecisionInfo,
    extract_deletion_info,
    derive_context_from_report,
    request_human_approval,
    request_build113_approval,
    request_build113_clarification,
    create_build113_decision_info,
)
from autopack.supervisor.api_client import (
    SupervisorApiClient,
    ApiResult,
    ApprovalStatus,
    ClarificationStatus,
)


class TestDeletionInfo:
    """Contract tests for DeletionInfo dataclass."""

    def test_to_dict_returns_all_fields(self):
        """Contract: to_dict returns all required fields."""
        info = DeletionInfo(
            net_deletion=50,
            loc_removed=100,
            loc_added=50,
            files=["a.py", "b.py"],
            risk_level="high",
            risk_score=0.8,
        )

        result = info.to_dict()

        assert result["net_deletion"] == 50
        assert result["loc_removed"] == 100
        assert result["loc_added"] == 50
        assert result["files"] == ["a.py", "b.py"]
        assert result["risk_level"] == "high"
        assert result["risk_score"] == 0.8


class TestBuild113DecisionInfo:
    """Contract tests for Build113DecisionInfo dataclass."""

    def test_to_approval_dict_limits_files(self):
        """Contract: to_approval_dict limits files to first 5."""
        info = Build113DecisionInfo(
            decision_type="RISKY",
            risk_level="high",
            confidence=0.75,
            rationale="Complex refactoring",
            files_modified=["a.py", "b.py", "c.py", "d.py", "e.py", "f.py", "g.py"],
            deliverables_met=True,
            net_deletion=100,
            questions_for_human=["Is this correct?"],
        )

        result = info.to_approval_dict()

        assert len(result["files_modified"]) == 5
        assert result["files_count"] == 7

    def test_to_approval_dict_formats_confidence(self):
        """Contract: to_approval_dict formats confidence as percentage."""
        info = Build113DecisionInfo(
            decision_type="RISKY",
            risk_level="medium",
            confidence=0.85,
            rationale="Test",
            files_modified=[],
            deliverables_met=True,
            net_deletion=0,
            questions_for_human=[],
        )

        result = info.to_approval_dict()

        assert result["confidence"] == "85%"

    def test_to_clarification_dict_includes_alternatives(self):
        """Contract: to_clarification_dict includes alternatives if present."""
        info = Build113DecisionInfo(
            decision_type="AMBIGUOUS",
            risk_level="low",
            confidence=0.5,
            rationale="Unclear",
            files_modified=[],
            deliverables_met=False,
            net_deletion=0,
            questions_for_human=["Which approach?"],
            alternatives_considered=["Option A", "Option B"],
        )

        result = info.to_clarification_dict()

        assert result["alternatives"] == ["Option A", "Option B"]
        assert result["questions"] == ["Which approach?"]


class TestExtractDeletionInfo:
    """Contract tests for extract_deletion_info function."""

    def test_returns_default_when_no_risk_assessment(self):
        """Contract: Returns defaults when quality_report has no risk_assessment."""
        quality_report = MagicMock(spec=[])  # No risk_assessment attribute

        result = extract_deletion_info(quality_report)

        assert result.net_deletion == 0
        assert result.risk_level == "unknown"
        assert result.risk_score == 0
        assert result.files == []

    def test_extracts_from_metadata(self):
        """Contract: Extracts deletion info from risk_assessment metadata."""
        quality_report = MagicMock()
        quality_report.risk_assessment = {
            "risk_level": "high",
            "risk_score": 0.9,
            "metadata": {
                "loc_removed": 200,
                "loc_added": 50,
                "files_changed": ["a.py", "b.py"],
            },
        }

        result = extract_deletion_info(quality_report)

        assert result.net_deletion == 150  # 200 - 50
        assert result.loc_removed == 200
        assert result.loc_added == 50
        assert result.files == ["a.py", "b.py"]
        assert result.risk_level == "high"
        assert result.risk_score == 0.9

    def test_uses_fallback_files(self):
        """Contract: Uses fallback_files when not in metadata."""
        quality_report = MagicMock()
        quality_report.risk_assessment = {
            "risk_level": "medium",
            "risk_score": 0.5,
            "metadata": {},
        }

        result = extract_deletion_info(quality_report, fallback_files=["x.py", "y.py"])

        assert result.files == ["x.py", "y.py"]

    def test_limits_files_to_10(self):
        """Contract: Limits files to 10 for display."""
        quality_report = MagicMock()
        quality_report.risk_assessment = {
            "risk_level": "low",
            "risk_score": 0.1,
            "metadata": {
                "files_changed": [f"file{i}.py" for i in range(20)],
            },
        }

        result = extract_deletion_info(quality_report)

        assert len(result.files) == 10


class TestDeriveContextFromReport:
    """Contract tests for derive_context_from_report function."""

    def test_uses_phase_category_if_present(self):
        """Contract: Uses phase_category attribute if present."""
        quality_report = MagicMock()
        quality_report.phase_category = "refactoring"

        result = derive_context_from_report(quality_report)

        assert result == "refactoring"

    def test_uses_task_category_from_metadata(self):
        """Contract: Uses task_category from risk_assessment metadata."""
        quality_report = MagicMock(spec=[])  # No phase_category
        quality_report.risk_assessment = {
            "metadata": {
                "task_category": "feature",
            },
        }

        result = derive_context_from_report(quality_report)

        assert result == "feature"

    def test_defaults_to_general(self):
        """Contract: Defaults to 'general' when no context available."""
        quality_report = MagicMock(spec=[])  # No phase_category

        result = derive_context_from_report(quality_report)

        assert result == "general"


class TestRequestHumanApproval:
    """Contract tests for request_human_approval function."""

    def test_returns_false_on_request_failure(self):
        """Contract: Returns False when approval request fails."""
        client = MagicMock(spec=SupervisorApiClient)
        client.request_approval.return_value = ApiResult(
            success=False,
            error="Connection refused",
        )

        quality_report = MagicMock(spec=[])

        result = request_human_approval(
            client=client,
            run_id="run-123",
            phase_id="phase-1",
            quality_report=quality_report,
        )

        assert result is False

    def test_returns_false_on_immediate_rejection(self):
        """Contract: Returns False when immediately rejected."""
        client = MagicMock(spec=SupervisorApiClient)
        client.request_approval.return_value = ApiResult(
            success=True,
            data={"status": "rejected", "reason": "Not allowed"},
        )

        quality_report = MagicMock(spec=[])

        result = request_human_approval(
            client=client,
            run_id="run-123",
            phase_id="phase-1",
            quality_report=quality_report,
        )

        assert result is False

    def test_returns_true_on_immediate_approval(self):
        """Contract: Returns True when immediately approved (auto-approve)."""
        client = MagicMock(spec=SupervisorApiClient)
        client.request_approval.return_value = ApiResult(
            success=True,
            data={"status": "approved"},
        )

        quality_report = MagicMock(spec=[])

        result = request_human_approval(
            client=client,
            run_id="run-123",
            phase_id="phase-1",
            quality_report=quality_report,
        )

        assert result is True
        # poll_approval_status should NOT be called for immediate approval
        client.poll_approval_status.assert_not_called()

    def test_returns_false_when_no_approval_id(self):
        """Contract: Returns False when no approval_id in response."""
        client = MagicMock(spec=SupervisorApiClient)
        client.request_approval.return_value = ApiResult(
            success=True,
            data={"status": "pending"},  # No approval_id
        )

        quality_report = MagicMock(spec=[])

        result = request_human_approval(
            client=client,
            run_id="run-123",
            phase_id="phase-1",
            quality_report=quality_report,
        )

        assert result is False

    def test_polls_and_returns_true_on_approved(self):
        """Contract: Polls and returns True when user approves."""
        client = MagicMock(spec=SupervisorApiClient)
        client.request_approval.return_value = ApiResult(
            success=True,
            data={"status": "pending", "approval_id": "approval-123"},
        )
        client.poll_approval_status.return_value = ApprovalStatus(
            status="approved",
            approval_id="approval-123",
        )

        quality_report = MagicMock(spec=[])

        result = request_human_approval(
            client=client,
            run_id="run-123",
            phase_id="phase-1",
            quality_report=quality_report,
            timeout_seconds=10,
        )

        assert result is True
        client.poll_approval_status.assert_called_once_with(
            approval_id="approval-123",
            timeout_seconds=10,
            poll_interval=10,
        )

    def test_polls_and_returns_false_on_rejected(self):
        """Contract: Polls and returns False when user rejects."""
        client = MagicMock(spec=SupervisorApiClient)
        client.request_approval.return_value = ApiResult(
            success=True,
            data={"status": "pending", "approval_id": "approval-123"},
        )
        client.poll_approval_status.return_value = ApprovalStatus(
            status="rejected",
            approval_id="approval-123",
            reason="Denied by user",
        )

        quality_report = MagicMock(spec=[])

        result = request_human_approval(
            client=client,
            run_id="run-123",
            phase_id="phase-1",
            quality_report=quality_report,
        )

        assert result is False

    def test_returns_false_on_timeout(self):
        """Contract: Returns False on approval timeout."""
        client = MagicMock(spec=SupervisorApiClient)
        client.request_approval.return_value = ApiResult(
            success=True,
            data={"status": "pending", "approval_id": "approval-123"},
        )
        client.poll_approval_status.return_value = ApprovalStatus(
            status="timeout",
            approval_id="approval-123",
        )

        quality_report = MagicMock(spec=[])

        result = request_human_approval(
            client=client,
            run_id="run-123",
            phase_id="phase-1",
            quality_report=quality_report,
        )

        assert result is False


class TestRequestBuild113Approval:
    """Contract tests for request_build113_approval function."""

    def test_returns_false_on_request_failure(self):
        """Contract: Returns False when approval request fails."""
        client = MagicMock(spec=SupervisorApiClient)
        client.request_approval.return_value = ApiResult(
            success=False,
            error="Connection refused",
        )

        decision_info = Build113DecisionInfo(
            decision_type="RISKY",
            risk_level="high",
            confidence=0.7,
            rationale="Test",
            files_modified=["a.py"],
            deliverables_met=True,
            net_deletion=50,
            questions_for_human=[],
        )

        result = request_build113_approval(
            client=client,
            run_id="run-123",
            phase_id="phase-1",
            decision_info=decision_info,
            patch_content="test patch",
        )

        assert result is False

    def test_includes_patch_preview_in_payload(self):
        """Contract: Includes truncated patch preview in request."""
        client = MagicMock(spec=SupervisorApiClient)
        client.request_approval.return_value = ApiResult(
            success=True,
            data={"status": "approved"},
        )

        decision_info = Build113DecisionInfo(
            decision_type="RISKY",
            risk_level="high",
            confidence=0.7,
            rationale="Test",
            files_modified=["a.py"],
            deliverables_met=True,
            net_deletion=50,
            questions_for_human=[],
        )

        # Long patch content
        patch_content = "x" * 1000

        request_build113_approval(
            client=client,
            run_id="run-123",
            phase_id="phase-1",
            decision_info=decision_info,
            patch_content=patch_content,
        )

        # Check the payload includes truncated preview
        call_args = client.request_approval.call_args
        payload = call_args[1]["payload"]
        assert len(payload["patch_preview"]) == 503  # 500 + "..."
        assert payload["patch_preview"].endswith("...")

    def test_uses_build113_risky_context(self):
        """Contract: Uses 'build113_risky_decision' context."""
        client = MagicMock(spec=SupervisorApiClient)
        client.request_approval.return_value = ApiResult(
            success=True,
            data={"status": "approved"},
        )

        decision_info = Build113DecisionInfo(
            decision_type="RISKY",
            risk_level="high",
            confidence=0.7,
            rationale="Test",
            files_modified=[],
            deliverables_met=True,
            net_deletion=0,
            questions_for_human=[],
        )

        request_build113_approval(
            client=client,
            run_id="run-123",
            phase_id="phase-1",
            decision_info=decision_info,
            patch_content="test",
        )

        call_args = client.request_approval.call_args
        assert call_args[1]["context"] == "build113_risky_decision"


class TestRequestBuild113Clarification:
    """Contract tests for request_build113_clarification function."""

    def test_returns_none_on_request_failure(self):
        """Contract: Returns None when clarification request fails."""
        client = MagicMock(spec=SupervisorApiClient)
        client.request_clarification.return_value = ApiResult(
            success=False,
            error="Connection refused",
        )

        decision_info = Build113DecisionInfo(
            decision_type="AMBIGUOUS",
            risk_level="medium",
            confidence=0.5,
            rationale="Unclear",
            files_modified=[],
            deliverables_met=False,
            net_deletion=0,
            questions_for_human=["Which approach?"],
        )

        result = request_build113_clarification(
            client=client,
            run_id="run-123",
            phase_id="phase-1",
            decision_info=decision_info,
        )

        assert result is None

    def test_returns_response_when_answered(self):
        """Contract: Returns response text when user answers."""
        client = MagicMock(spec=SupervisorApiClient)
        client.request_clarification.return_value = ApiResult(
            success=True,
            data={"status": "pending"},
        )
        client.poll_clarification_status.return_value = ClarificationStatus(
            status="answered",
            clarification_id="clarify-123",
            response="Use option A",
        )

        decision_info = Build113DecisionInfo(
            decision_type="AMBIGUOUS",
            risk_level="medium",
            confidence=0.5,
            rationale="Unclear",
            files_modified=[],
            deliverables_met=False,
            net_deletion=0,
            questions_for_human=["Which approach?"],
        )

        result = request_build113_clarification(
            client=client,
            run_id="run-123",
            phase_id="phase-1",
            decision_info=decision_info,
        )

        assert result == "Use option A"

    def test_returns_none_on_rejection(self):
        """Contract: Returns None when user rejects clarification."""
        client = MagicMock(spec=SupervisorApiClient)
        client.request_clarification.return_value = ApiResult(
            success=True,
            data={"status": "pending"},
        )
        client.poll_clarification_status.return_value = ClarificationStatus(
            status="rejected",
            clarification_id="clarify-123",
        )

        decision_info = Build113DecisionInfo(
            decision_type="AMBIGUOUS",
            risk_level="medium",
            confidence=0.5,
            rationale="Unclear",
            files_modified=[],
            deliverables_met=False,
            net_deletion=0,
            questions_for_human=[],
        )

        result = request_build113_clarification(
            client=client,
            run_id="run-123",
            phase_id="phase-1",
            decision_info=decision_info,
        )

        assert result is None

    def test_returns_none_on_timeout(self):
        """Contract: Returns None on clarification timeout."""
        client = MagicMock(spec=SupervisorApiClient)
        client.request_clarification.return_value = ApiResult(
            success=True,
            data={"status": "pending"},
        )
        client.poll_clarification_status.return_value = ClarificationStatus(
            status="timeout",
            clarification_id="clarify-123",
        )

        decision_info = Build113DecisionInfo(
            decision_type="AMBIGUOUS",
            risk_level="medium",
            confidence=0.5,
            rationale="Unclear",
            files_modified=[],
            deliverables_met=False,
            net_deletion=0,
            questions_for_human=[],
        )

        result = request_build113_clarification(
            client=client,
            run_id="run-123",
            phase_id="phase-1",
            decision_info=decision_info,
        )

        assert result is None


class TestCreateBuild113DecisionInfo:
    """Contract tests for create_build113_decision_info function."""

    def test_extracts_all_fields(self):
        """Contract: Extracts all fields from Decision object."""

        class DecisionType(Enum):
            RISKY = "risky"

        decision = MagicMock()
        decision.type = DecisionType.RISKY
        decision.risk_level = "high"
        decision.confidence = 0.85
        decision.rationale = "Test rationale"
        decision.files_modified = ["a.py", "b.py"]
        decision.deliverables_met = True
        decision.net_deletion = 100
        decision.questions_for_human = ["Is this safe?"]
        decision.alternatives_considered = ["Option A", "Option B"]

        result = create_build113_decision_info(decision)

        assert result.decision_type == "risky"
        assert result.risk_level == "high"
        assert result.confidence == 0.85
        assert result.rationale == "Test rationale"
        assert result.files_modified == ["a.py", "b.py"]
        assert result.deliverables_met is True
        assert result.net_deletion == 100
        assert result.questions_for_human == ["Is this safe?"]
        assert result.alternatives_considered == ["Option A", "Option B"]

    def test_handles_string_type(self):
        """Contract: Handles decision type as string."""
        decision = MagicMock()
        decision.type = "RISKY"  # String, not enum
        decision.risk_level = "high"
        decision.confidence = 0.7
        decision.rationale = "Test"
        decision.files_modified = []
        decision.deliverables_met = True
        decision.net_deletion = 0
        decision.questions_for_human = []

        # No alternatives_considered attribute
        del decision.alternatives_considered

        result = create_build113_decision_info(decision)

        assert result.decision_type == "RISKY"
        assert result.alternatives_considered is None
