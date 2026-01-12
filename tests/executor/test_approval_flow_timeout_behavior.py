"""Test deterministic timeout behavior for approval flow functions.

Tests all three approval flow functions with injectable mock sleep to avoid real waits:
- request_human_approval
- request_build113_approval
- request_build113_clarification

Uses table-driven tests for different timeout scenarios.
"""

import pytest
from unittest.mock import Mock, MagicMock
from autopack.executor.approval_flow import (
    request_human_approval,
    request_build113_approval,
    request_build113_clarification,
)


class MockQualityReport:
    """Mock quality report for testing."""

    def __init__(self, risk_assessment=None, phase_category=None):
        self.risk_assessment = risk_assessment
        if phase_category:
            self.phase_category = phase_category


class MockDecision:
    """Mock BUILD-113 decision for testing."""

    def __init__(
        self,
        decision_type="PROCEED",
        risk_level="high",
        confidence=0.75,
        rationale="Test rationale",
        files_modified=None,
        deliverables_met=True,
        net_deletion=0,
        questions_for_human=None,
        alternatives_considered=None,
    ):
        self.type = Mock(value=decision_type)
        self.risk_level = risk_level
        self.confidence = confidence
        self.rationale = rationale
        self.files_modified = files_modified or ["file1.py", "file2.py"]
        self.deliverables_met = deliverables_met
        self.net_deletion = net_deletion
        self.questions_for_human = questions_for_human or ["Question 1?"]
        self.alternatives_considered = alternatives_considered or ["Alternative 1"]


# Table-driven test cases for timeout scenarios
# Note: polls happen at elapsed=0, 10, 20, ... until elapsed >= timeout_seconds
# So timeout=30 allows polls at 0s, 10s, 20s (3 polls total, not 4)
TIMEOUT_TEST_CASES = [
    # (timeout_seconds, poll_responses, expected_result, expected_poll_count, description)
    (40, ["pending", "pending", "pending", "approved"], True, 4, "approval_after_3_polls"),  # polls at 0, 10, 20, 30
    (30, ["pending", "pending", "rejected"], False, 3, "rejection_after_2_polls"),  # polls at 0, 10, 20
    (35, ["pending"] * 10, False, 4, "timeout_after_35_seconds"),  # polls at 0, 10, 20, 30; timeout before 40
    (20, ["pending", "approved"], True, 2, "quick_approval_within_timeout"),  # polls at 0, 10
    (15, ["pending"], False, 2, "immediate_timeout_after_second_poll"),  # polls at 0, 10; timeout before 20
]


class TestRequestHumanApprovalTimeout:
    """Test request_human_approval with deterministic timeout behavior."""

    @pytest.mark.parametrize(
        "timeout_seconds,poll_responses,expected_result,expected_poll_count,description",
        TIMEOUT_TEST_CASES,
        ids=[case[4] for case in TIMEOUT_TEST_CASES],
    )
    def test_approval_timeout_scenarios(
        self, timeout_seconds, poll_responses, expected_result, expected_poll_count, description
    ):
        """Test various timeout scenarios with mock sleep."""
        # Setup mock API client
        api_client = Mock()
        api_client.request_approval.return_value = {
            "status": "pending",
            "approval_id": "test-approval-123",
        }

        # Setup poll responses
        poll_side_effects = [{"status": status} for status in poll_responses]
        api_client.poll_approval_status.side_effect = poll_side_effects

        # Mock sleep to track elapsed time
        sleep_calls = []

        def mock_sleep(seconds):
            sleep_calls.append(seconds)

        # Execute
        quality_report = MockQualityReport(
            risk_assessment={
                "risk_level": "high",
                "risk_score": 75,
                "metadata": {
                    "loc_removed": 100,
                    "loc_added": 50,
                    "files_changed": ["test.py"],
                },
            }
        )

        result = request_human_approval(
            api_client=api_client,
            phase_id="test-phase",
            quality_report=quality_report,
            run_id="test-run",
            timeout_seconds=timeout_seconds,
            sleep_fn=mock_sleep,
        )

        # Assert
        assert result == expected_result, f"Failed for case: {description}"
        assert (
            api_client.poll_approval_status.call_count == expected_poll_count
        ), f"Expected {expected_poll_count} polls, got {api_client.poll_approval_status.call_count}"

        # Verify sleep was called correctly
        # For timeout cases: all polls return "pending", so sleep_count == poll_count
        # For success cases: last poll returns terminal status, so sleep_count == poll_count - 1
        if expected_result is False and "timeout" in description:
            expected_sleep_calls = expected_poll_count  # All pending responses cause sleep
        else:
            expected_sleep_calls = expected_poll_count - 1  # Last poll returns terminal status, no sleep
        assert len(sleep_calls) == expected_sleep_calls, f"Expected {expected_sleep_calls} sleep calls, got {len(sleep_calls)}"
        assert all(s == 10 for s in sleep_calls), "All sleep calls should be 10 seconds (poll_interval)"

    def test_immediate_approval_no_polling(self):
        """Test auto-approve mode - no polling occurs."""
        api_client = Mock()
        api_client.request_approval.return_value = {
            "status": "approved",  # Immediate approval
        }

        sleep_calls = []

        def mock_sleep(seconds):
            sleep_calls.append(seconds)

        quality_report = MockQualityReport(risk_assessment=None)

        result = request_human_approval(
            api_client=api_client,
            phase_id="test-phase",
            quality_report=quality_report,
            run_id="test-run",
            timeout_seconds=60,
            sleep_fn=mock_sleep,
        )

        assert result is True
        assert api_client.poll_approval_status.call_count == 0, "Should not poll on immediate approval"
        assert len(sleep_calls) == 0, "Should not sleep on immediate approval"

    def test_request_approval_failure(self):
        """Test request_approval API call failure."""
        api_client = Mock()
        api_client.request_approval.side_effect = Exception("API error")

        sleep_calls = []

        def mock_sleep(seconds):
            sleep_calls.append(seconds)

        quality_report = MockQualityReport(risk_assessment=None)

        result = request_human_approval(
            api_client=api_client,
            phase_id="test-phase",
            quality_report=quality_report,
            run_id="test-run",
            timeout_seconds=60,
            sleep_fn=mock_sleep,
        )

        assert result is False, "Should return False on API failure"
        assert len(sleep_calls) == 0, "Should not sleep on API failure"

    def test_missing_approval_id(self):
        """Test missing approval_id in response."""
        api_client = Mock()
        api_client.request_approval.return_value = {
            "status": "pending",
            # Missing approval_id
        }

        sleep_calls = []

        def mock_sleep(seconds):
            sleep_calls.append(seconds)

        quality_report = MockQualityReport(risk_assessment=None)

        result = request_human_approval(
            api_client=api_client,
            phase_id="test-phase",
            quality_report=quality_report,
            run_id="test-run",
            timeout_seconds=60,
            sleep_fn=mock_sleep,
        )

        assert result is False, "Should return False when approval_id missing"
        assert api_client.poll_approval_status.call_count == 0
        assert len(sleep_calls) == 0

    def test_poll_exception_continues_polling(self):
        """Test that polling continues after exceptions."""
        api_client = Mock()
        api_client.request_approval.return_value = {
            "status": "pending",
            "approval_id": "test-approval-123",
        }

        # First poll throws exception, second succeeds
        api_client.poll_approval_status.side_effect = [
            Exception("Network error"),
            {"status": "approved"},
        ]

        sleep_calls = []

        def mock_sleep(seconds):
            sleep_calls.append(seconds)

        quality_report = MockQualityReport(risk_assessment=None)

        result = request_human_approval(
            api_client=api_client,
            phase_id="test-phase",
            quality_report=quality_report,
            run_id="test-run",
            timeout_seconds=30,
            sleep_fn=mock_sleep,
        )

        assert result is True, "Should succeed after exception"
        assert api_client.poll_approval_status.call_count == 2
        # Exception causes sleep, then approved poll (no sleep after terminal status)
        assert len(sleep_calls) == 1, f"Expected 1 sleep call (after exception), got {len(sleep_calls)}"


class TestRequestBuild113ApprovalTimeout:
    """Test request_build113_approval with deterministic timeout behavior."""

    @pytest.mark.parametrize(
        "timeout_seconds,poll_responses,expected_result,expected_poll_count,description",
        TIMEOUT_TEST_CASES,
        ids=[case[4] for case in TIMEOUT_TEST_CASES],
    )
    def test_build113_approval_timeout_scenarios(
        self, timeout_seconds, poll_responses, expected_result, expected_poll_count, description
    ):
        """Test BUILD-113 approval various timeout scenarios."""
        api_client = Mock()
        api_client.request_approval.return_value = {
            "status": "pending",
            "approval_id": "test-approval-123",
        }

        poll_side_effects = [{"status": status} for status in poll_responses]
        api_client.poll_approval_status.side_effect = poll_side_effects

        sleep_calls = []

        def mock_sleep(seconds):
            sleep_calls.append(seconds)

        decision = MockDecision()
        patch_content = "diff --git a/test.py b/test.py\n+print('hello')"

        result = request_build113_approval(
            api_client=api_client,
            phase_id="test-phase",
            decision=decision,
            patch_content=patch_content,
            run_id="test-run",
            timeout_seconds=timeout_seconds,
            sleep_fn=mock_sleep,
        )

        assert result == expected_result, f"Failed for case: {description}"
        assert api_client.poll_approval_status.call_count == expected_poll_count
        # For timeout cases: all polls return "pending", so sleep_count == poll_count
        # For success cases: last poll returns terminal status, so sleep_count == poll_count - 1
        if expected_result is False and "timeout" in description:
            expected_sleep_calls = expected_poll_count
        else:
            expected_sleep_calls = expected_poll_count - 1
        assert len(sleep_calls) == expected_sleep_calls, f"Expected {expected_sleep_calls} sleep calls, got {len(sleep_calls)}"

    def test_build113_immediate_approval(self):
        """Test BUILD-113 auto-approve mode."""
        api_client = Mock()
        api_client.request_approval.return_value = {
            "status": "approved",
        }

        sleep_calls = []

        def mock_sleep(seconds):
            sleep_calls.append(seconds)

        decision = MockDecision()
        patch_content = "test patch"

        result = request_build113_approval(
            api_client=api_client,
            phase_id="test-phase",
            decision=decision,
            patch_content=patch_content,
            run_id="test-run",
            timeout_seconds=60,
            sleep_fn=mock_sleep,
        )

        assert result is True
        assert api_client.poll_approval_status.call_count == 0
        assert len(sleep_calls) == 0

    def test_build113_patch_preview_truncation(self):
        """Test that patch preview is truncated at 500 chars."""
        api_client = Mock()
        api_client.request_approval.return_value = {"status": "approved"}

        decision = MockDecision()
        patch_content = "x" * 1000  # 1000 char patch

        request_build113_approval(
            api_client=api_client,
            phase_id="test-phase",
            decision=decision,
            patch_content=patch_content,
            run_id="test-run",
            timeout_seconds=60,
            sleep_fn=lambda x: None,
        )

        # Verify the patch_preview in the request was truncated
        call_args = api_client.request_approval.call_args[0][0]
        patch_preview = call_args["patch_preview"]
        assert len(patch_preview) == 503, "Should be 500 chars + '...'"
        assert patch_preview.endswith("..."), "Should end with ellipsis"


class TestRequestBuild113ClarificationTimeout:
    """Test request_build113_clarification with deterministic timeout behavior."""

    # Adjusted test cases for clarification (returns string or None)
    # polls happen at elapsed=0, 10, 20, ... until elapsed >= timeout_seconds
    CLARIFICATION_TEST_CASES = [
        (30, ["pending", "pending", "answered"], "Clarification text", 3, "answered_after_2_polls"),  # polls at 0, 10, 20
        (30, ["pending", "rejected"], None, 2, "rejected_after_1_poll"),  # polls at 0, 10
        (35, ["pending"] * 10, None, 4, "timeout_after_35_seconds"),  # polls at 0, 10, 20, 30; timeout before 40
        (20, ["pending", "answered"], "Quick answer", 2, "quick_answer_within_timeout"),  # polls at 0, 10
        (15, ["pending"], None, 2, "immediate_timeout_after_second_poll"),  # polls at 0, 10; timeout before 20
    ]

    @pytest.mark.parametrize(
        "timeout_seconds,poll_responses,expected_result,expected_poll_count,description",
        CLARIFICATION_TEST_CASES,
        ids=[case[4] for case in CLARIFICATION_TEST_CASES],
    )
    def test_clarification_timeout_scenarios(
        self, timeout_seconds, poll_responses, expected_result, expected_poll_count, description
    ):
        """Test BUILD-113 clarification various timeout scenarios."""
        api_client = Mock()
        api_client.request_clarification.return_value = {"status": "pending"}

        # Setup poll responses - include response text for "answered" status
        poll_side_effects = []
        for status in poll_responses:
            if status == "answered":
                poll_side_effects.append({"status": status, "response": expected_result or "Response"})
            else:
                poll_side_effects.append({"status": status})

        api_client.poll_clarification_status.side_effect = poll_side_effects

        sleep_calls = []

        def mock_sleep(seconds):
            sleep_calls.append(seconds)

        decision = MockDecision()

        result = request_build113_clarification(
            api_client=api_client,
            phase_id="test-phase",
            decision=decision,
            run_id="test-run",
            timeout_seconds=timeout_seconds,
            sleep_fn=mock_sleep,
        )

        assert result == expected_result, f"Failed for case: {description}"
        assert api_client.poll_clarification_status.call_count == expected_poll_count
        # For timeout cases: all polls return "pending", so sleep_count == poll_count
        # For success cases: last poll returns terminal status, so sleep_count == poll_count - 1
        if expected_result is None and "timeout" in description:
            expected_sleep_calls = expected_poll_count
        else:
            expected_sleep_calls = expected_poll_count - 1
        assert len(sleep_calls) == expected_sleep_calls, f"Expected {expected_sleep_calls} sleep calls, got {len(sleep_calls)}"

    def test_clarification_request_failure(self):
        """Test clarification request API failure."""
        api_client = Mock()
        api_client.request_clarification.side_effect = Exception("API error")

        sleep_calls = []

        def mock_sleep(seconds):
            sleep_calls.append(seconds)

        decision = MockDecision()

        result = request_build113_clarification(
            api_client=api_client,
            phase_id="test-phase",
            decision=decision,
            run_id="test-run",
            timeout_seconds=60,
            sleep_fn=mock_sleep,
        )

        assert result is None, "Should return None on API failure"
        assert len(sleep_calls) == 0

    def test_clarification_poll_exception_continues(self):
        """Test that clarification polling continues after exceptions."""
        api_client = Mock()
        api_client.request_clarification.return_value = {"status": "pending"}

        # First poll throws exception, second succeeds
        api_client.poll_clarification_status.side_effect = [
            Exception("Network error"),
            {"status": "answered", "response": "Final answer"},
        ]

        sleep_calls = []

        def mock_sleep(seconds):
            sleep_calls.append(seconds)

        decision = MockDecision()

        result = request_build113_clarification(
            api_client=api_client,
            phase_id="test-phase",
            decision=decision,
            run_id="test-run",
            timeout_seconds=30,
            sleep_fn=mock_sleep,
        )

        assert result == "Final answer"
        assert api_client.poll_clarification_status.call_count == 2
        # Exception on first poll causes sleep, then second poll succeeds (no sleep after terminal status)
        assert len(sleep_calls) == 1, f"Expected 1 sleep call (after exception), got {len(sleep_calls)}"


class TestPollingIntervalBehavior:
    """Test that polling intervals are bounded and consistent."""

    def test_polling_interval_is_10_seconds(self):
        """Verify that all approval flows use 10-second polling intervals."""
        api_client = Mock()
        api_client.request_approval.return_value = {
            "status": "pending",
            "approval_id": "test-approval-123",
        }
        api_client.poll_approval_status.side_effect = [
            {"status": "pending"},
            {"status": "pending"},
            {"status": "approved"},
        ]

        sleep_calls = []

        def mock_sleep(seconds):
            sleep_calls.append(seconds)

        quality_report = MockQualityReport(risk_assessment=None)

        request_human_approval(
            api_client=api_client,
            phase_id="test-phase",
            quality_report=quality_report,
            run_id="test-run",
            timeout_seconds=60,
            sleep_fn=mock_sleep,
        )

        # All sleep calls should be exactly 10 seconds (poll_interval)
        assert all(s == 10 for s in sleep_calls), "All polling intervals must be 10 seconds"

    def test_timeout_honored_with_partial_interval(self):
        """Test that timeout is checked before sleeping, not after."""
        api_client = Mock()
        api_client.request_approval.return_value = {
            "status": "pending",
            "approval_id": "test-approval-123",
        }
        # Return pending indefinitely
        api_client.poll_approval_status.return_value = {"status": "pending"}

        sleep_calls = []

        def mock_sleep(seconds):
            sleep_calls.append(seconds)

        quality_report = MockQualityReport(risk_assessment=None)

        result = request_human_approval(
            api_client=api_client,
            phase_id="test-phase",
            quality_report=quality_report,
            run_id="test-run",
            timeout_seconds=25,  # Not evenly divisible by 10
            sleep_fn=mock_sleep,
        )

        assert result is False, "Should timeout"
        # With 25s timeout and 10s interval: poll at 0s, sleep 10s -> elapsed=10s,
        # poll at 10s, sleep 10s -> elapsed=20s, poll at 20s, sleep 10s -> elapsed=30s > 25s timeout
        # So we expect 3 polls (at 0s, 10s, 20s) but timeout before 4th poll at 30s
        assert len(sleep_calls) == 3, f"Expected 3 sleep calls for 25s timeout, got {len(sleep_calls)}"
