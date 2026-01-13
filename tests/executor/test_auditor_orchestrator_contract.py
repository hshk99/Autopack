"""Contract tests for AuditorOrchestrator module.

Validates that AuditorOrchestrator correctly:
1. Invokes Auditor LLM via llm_service with proper parameters
2. Parses Auditor response for recommendation, confidence, suggested patches
3. Posts Auditor results to API with correct schema
4. Handles backwards compatibility for API schema mismatches
5. Computes coverage delta from CI results
6. Includes model overrides in run context
7. Handles API failures gracefully
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional
from unittest.mock import Mock, patch, MagicMock

import pytest

from autopack.executor.auditor_orchestrator import AuditorOrchestrator


def make_auditor_orchestrator(tmp_path: Path) -> AuditorOrchestrator:
    """Create an AuditorOrchestrator with mocked executor."""
    executor = Mock()
    executor.workspace = str(tmp_path)
    executor.run_id = "test-run-123"
    executor.llm_service = Mock()
    executor.api_client = Mock()
    executor._build_run_context = Mock(return_value={})
    return AuditorOrchestrator(executor)


def test_execute_auditor_review_invokes_llm_service(tmp_path: Path):
    """Test that execute_auditor_review invokes llm_service with correct parameters."""
    orchestrator = make_auditor_orchestrator(tmp_path)

    builder_result = Mock()
    builder_result.patch_content = "diff --git a/test.py"

    auditor_result = Mock()
    auditor_result.approved = True
    auditor_result.issues_found = []
    auditor_result.auditor_messages = ["Looks good"]
    auditor_result.tokens_used = 1000

    orchestrator.llm_service.execute_auditor_review.return_value = auditor_result

    with patch.object(orchestrator, 'post_auditor_result'):
        result = orchestrator.execute_auditor_review(
            phase_id="phase-1",
            phase={"description": "Test phase"},
            builder_result=builder_result,
            ci_result=None,
            project_rules=["rule1"],
            run_hints=["hint1"],
            attempt_index=0,
        )

    assert result.approved is True
    assert orchestrator.llm_service.execute_auditor_review.called
    call_kwargs = orchestrator.llm_service.execute_auditor_review.call_args[1]
    assert call_kwargs["patch_content"] == "diff --git a/test.py"
    assert call_kwargs["project_rules"] == ["rule1"]
    assert call_kwargs["run_hints"] == ["hint1"]


def test_execute_auditor_review_computes_coverage_delta(tmp_path: Path):
    """Test that execute_auditor_review computes coverage delta from CI results."""
    orchestrator = make_auditor_orchestrator(tmp_path)

    builder_result = Mock()
    builder_result.patch_content = "diff --git a/test.py"

    ci_result = {
        "coverage": {
            "before": 80.0,
            "after": 85.0
        }
    }

    auditor_result = Mock()
    auditor_result.approved = True
    auditor_result.issues_found = []
    auditor_result.auditor_messages = []
    auditor_result.tokens_used = 1000

    orchestrator.llm_service.execute_auditor_review.return_value = auditor_result

    with patch.object(orchestrator, '_compute_coverage_delta', return_value=5.0) as mock_compute:
        with patch.object(orchestrator, 'post_auditor_result'):
            orchestrator.execute_auditor_review(
                phase_id="phase-1",
                phase={},
                builder_result=builder_result,
                ci_result=ci_result,
                project_rules=[],
                run_hints=[],
            )

    mock_compute.assert_called_once_with(ci_result)


def test_execute_auditor_review_includes_run_context(tmp_path: Path):
    """Test that execute_auditor_review includes run context with model overrides."""
    orchestrator = make_auditor_orchestrator(tmp_path)
    orchestrator._build_run_context = Mock(return_value={"model": "claude-opus-4"})

    builder_result = Mock()
    builder_result.patch_content = "diff"

    auditor_result = Mock()
    auditor_result.approved = True
    auditor_result.issues_found = []
    auditor_result.auditor_messages = []
    auditor_result.tokens_used = 1000

    orchestrator.llm_service.execute_auditor_review.return_value = auditor_result

    with patch.object(orchestrator, 'post_auditor_result'):
        orchestrator.execute_auditor_review(
            phase_id="phase-1",
            phase={},
            builder_result=builder_result,
            ci_result=None,
            project_rules=[],
            run_hints=[],
        )

    call_kwargs = orchestrator.llm_service.execute_auditor_review.call_args[1]
    assert call_kwargs["run_context"] == {"model": "claude-opus-4"}


def test_execute_auditor_review_posts_result(tmp_path: Path):
    """Test that execute_auditor_review posts result to API."""
    orchestrator = make_auditor_orchestrator(tmp_path)

    builder_result = Mock()
    builder_result.patch_content = "diff"

    auditor_result = Mock()
    auditor_result.approved = True
    auditor_result.issues_found = []
    auditor_result.auditor_messages = ["Approved"]
    auditor_result.tokens_used = 1000

    orchestrator.llm_service.execute_auditor_review.return_value = auditor_result

    with patch.object(orchestrator, 'post_auditor_result') as mock_post:
        orchestrator.execute_auditor_review(
            phase_id="phase-1",
            phase={},
            builder_result=builder_result,
            ci_result=None,
            project_rules=[],
            run_hints=[],
        )

    mock_post.assert_called_once_with("phase-1", auditor_result)


def test_post_auditor_result_formats_issues(tmp_path: Path):
    """Test that post_auditor_result formats issues correctly."""
    orchestrator = make_auditor_orchestrator(tmp_path)

    auditor_result = Mock()
    auditor_result.approved = False
    auditor_result.issues_found = [
        {
            "issue_key": "test-issue-1",
            "severity": "high",
            "source": "auditor",
            "category": "quality",
            "evidence_refs": ["line 10"],
            "description": "Test issue description",
        }
    ]
    auditor_result.auditor_messages = ["Found issues"]
    auditor_result.tokens_used = 1000
    auditor_result.error = None

    with patch('autopack.executor.auditor_parsing.parse_auditor_result') as mock_parse:
        mock_parsed = Mock()
        mock_parsed.recommendation = "APPROVE"
        mock_parsed.confidence_overall = 0.9
        mock_parsed.suggested_patches = []
        mock_parse.return_value = mock_parsed

        orchestrator.post_auditor_result("phase-1", auditor_result)

    # Verify API call
    call_args = orchestrator.api_client.submit_auditor_result.call_args
    payload = call_args[0][2]

    assert len(payload["issues_found"]) == 1
    assert payload["issues_found"][0]["issue_key"] == "test-issue-1"
    assert payload["issues_found"][0]["severity"] == "high"


def test_post_auditor_result_parses_structured_fields(tmp_path: Path):
    """Test that post_auditor_result parses structured fields using auditor_parsing."""
    orchestrator = make_auditor_orchestrator(tmp_path)

    auditor_result = Mock()
    auditor_result.approved = True
    auditor_result.issues_found = []
    auditor_result.auditor_messages = ["## Recommendation: APPROVE", "## Confidence: 0.95"]
    auditor_result.tokens_used = 1000
    auditor_result.error = None

    with patch('autopack.executor.auditor_parsing.parse_auditor_result') as mock_parse:
        mock_parsed = Mock()
        mock_parsed.recommendation = "APPROVE"
        mock_parsed.confidence_overall = 0.95
        mock_parsed.suggested_patches = []
        mock_parse.return_value = mock_parsed

        orchestrator.post_auditor_result("phase-1", auditor_result)

    # Verify parsing was called
    assert mock_parse.called
    call_kwargs = mock_parse.call_args[1]
    assert call_kwargs["auditor_messages"] == auditor_result.auditor_messages
    assert call_kwargs["approved"] == auditor_result.approved


def test_post_auditor_result_includes_suggested_patches(tmp_path: Path):
    """Test that post_auditor_result includes suggested patches from parsed result."""
    orchestrator = make_auditor_orchestrator(tmp_path)

    auditor_result = Mock()
    auditor_result.approved = False
    auditor_result.issues_found = []
    auditor_result.auditor_messages = ["## Suggested Patches\n```patch\ndiff --git a/test.py```"]
    auditor_result.tokens_used = 1000
    auditor_result.error = None

    mock_patch = Mock()
    mock_patch.to_dict = Mock(return_value={"patch_content": "diff --git a/test.py"})

    with patch('autopack.executor.auditor_parsing.parse_auditor_result') as mock_parse:
        mock_parsed = Mock()
        mock_parsed.recommendation = "REQUEST_CHANGES"
        mock_parsed.confidence_overall = 0.8
        mock_parsed.suggested_patches = [mock_patch]
        mock_parse.return_value = mock_parsed

        orchestrator.post_auditor_result("phase-1", auditor_result)

    # Verify suggested patches in payload
    call_args = orchestrator.api_client.submit_auditor_result.call_args
    payload = call_args[0][2]
    assert len(payload["suggested_patches"]) == 1


def test_post_auditor_result_handles_api_success(tmp_path: Path):
    """Test that post_auditor_result handles successful API call."""
    orchestrator = make_auditor_orchestrator(tmp_path)

    auditor_result = Mock()
    auditor_result.approved = True
    auditor_result.issues_found = []
    auditor_result.auditor_messages = []
    auditor_result.tokens_used = 1000
    auditor_result.error = None

    with patch('autopack.executor.auditor_parsing.parse_auditor_result') as mock_parse:
        mock_parsed = Mock()
        mock_parsed.recommendation = "APPROVE"
        mock_parsed.confidence_overall = 0.9
        mock_parsed.suggested_patches = []
        mock_parse.return_value = mock_parsed

        # Should not raise exception
        orchestrator.post_auditor_result("phase-1", auditor_result)


def test_post_auditor_result_handles_backwards_compatibility(tmp_path: Path):
    """Test that post_auditor_result handles backwards compatibility for schema mismatches."""
    from autopack.supervisor.api_client import SupervisorApiHttpError

    orchestrator = make_auditor_orchestrator(tmp_path)

    auditor_result = Mock()
    auditor_result.approved = True
    auditor_result.issues_found = []
    auditor_result.auditor_messages = ["Approved"]
    auditor_result.tokens_used = 1000
    auditor_result.error = None

    # First call fails with 422 missing "success" field
    error_detail = [{"loc": ["body", "success"], "msg": "Field required"}]
    error = SupervisorApiHttpError(
        status_code=422,
        response_body=json.dumps({"detail": error_detail}),
        message="Validation error"
    )

    orchestrator.api_client.submit_auditor_result.side_effect = [error, None]

    with patch('autopack.executor.auditor_parsing.parse_auditor_result') as mock_parse:
        mock_parsed = Mock()
        mock_parsed.recommendation = "APPROVE"
        mock_parsed.confidence_overall = 0.9
        mock_parsed.suggested_patches = []
        mock_parse.return_value = mock_parsed

        orchestrator.post_auditor_result("phase-1", auditor_result)

    # Verify retry with fallback payload
    assert orchestrator.api_client.submit_auditor_result.call_count == 2
    second_call_payload = orchestrator.api_client.submit_auditor_result.call_args_list[1][0][2]
    assert "success" in second_call_payload
    assert second_call_payload["success"] is True


def test_post_auditor_result_logs_non_http_errors(tmp_path: Path):
    """Test that post_auditor_result logs non-HTTP API errors gracefully."""
    import logging

    orchestrator = make_auditor_orchestrator(tmp_path)

    auditor_result = Mock()
    auditor_result.approved = True
    auditor_result.issues_found = []
    auditor_result.auditor_messages = []
    auditor_result.tokens_used = 1000
    auditor_result.error = None

    # Use a generic exception (not SupervisorApiHttpError which gets re-raised)
    error = Exception("Connection timeout")

    orchestrator.api_client.submit_auditor_result.side_effect = error

    with patch('autopack.executor.auditor_parsing.parse_auditor_result') as mock_parse:
        mock_parsed = Mock()
        mock_parsed.recommendation = "APPROVE"
        mock_parsed.confidence_overall = 0.9
        mock_parsed.suggested_patches = []
        mock_parse.return_value = mock_parsed

        # Capture logger warnings instead since that's what's actually visible
        with patch('autopack.executor.auditor_orchestrator.logger') as mock_logger:
            # Should not raise, just log
            orchestrator.post_auditor_result("phase-1", auditor_result)

            # Verify warning was logged
            assert mock_logger.warning.called
            call_args = str(mock_logger.warning.call_args)
            assert "Failed to post auditor result" in call_args


def test_post_auditor_result_uses_error_when_no_messages(tmp_path: Path):
    """Test that post_auditor_result uses error field when no auditor_messages."""
    orchestrator = make_auditor_orchestrator(tmp_path)

    auditor_result = Mock()
    auditor_result.approved = False
    auditor_result.issues_found = []
    auditor_result.auditor_messages = []
    auditor_result.tokens_used = 1000
    auditor_result.error = "LLM timeout error"

    with patch('autopack.executor.auditor_parsing.parse_auditor_result') as mock_parse:
        mock_parsed = Mock()
        mock_parsed.recommendation = "REJECT"
        mock_parsed.confidence_overall = 0.5
        mock_parsed.suggested_patches = []
        mock_parse.return_value = mock_parsed

        orchestrator.post_auditor_result("phase-1", auditor_result)

    # Verify error was used in review_notes
    call_args = orchestrator.api_client.submit_auditor_result.call_args
    payload = call_args[0][2]
    assert payload["review_notes"] == "LLM timeout error"


def test_compute_coverage_delta_delegates_to_coverage_metrics(tmp_path: Path):
    """Test that _compute_coverage_delta delegates to coverage_metrics module."""
    orchestrator = make_auditor_orchestrator(tmp_path)

    ci_result = {
        "coverage": {
            "before": 80.0,
            "after": 85.0
        }
    }

    with patch('autopack.executor.coverage_metrics.compute_coverage_delta', return_value=5.0) as mock_compute:
        delta = orchestrator._compute_coverage_delta(ci_result)

    assert delta == 5.0
    mock_compute.assert_called_once_with(ci_result)


def test_compute_coverage_delta_returns_none_when_unavailable(tmp_path: Path):
    """Test that _compute_coverage_delta returns None when coverage unavailable."""
    orchestrator = make_auditor_orchestrator(tmp_path)

    ci_result = {"passed": 10, "failed": 0}

    with patch('autopack.executor.coverage_metrics.compute_coverage_delta', return_value=None):
        delta = orchestrator._compute_coverage_delta(ci_result)

    assert delta is None


def test_build_run_context_delegates_to_executor(tmp_path: Path):
    """Test that _build_run_context delegates to executor's method."""
    orchestrator = make_auditor_orchestrator(tmp_path)
    orchestrator.executor._build_run_context = Mock(return_value={"model": "custom-model"})

    context = orchestrator._build_run_context()

    assert context == {"model": "custom-model"}
    orchestrator.executor._build_run_context.assert_called_once()


def test_execute_auditor_review_passes_attempt_index(tmp_path: Path):
    """Test that execute_auditor_review passes attempt_index for model escalation."""
    orchestrator = make_auditor_orchestrator(tmp_path)

    builder_result = Mock()
    builder_result.patch_content = "diff"

    auditor_result = Mock()
    auditor_result.approved = True
    auditor_result.issues_found = []
    auditor_result.auditor_messages = []
    auditor_result.tokens_used = 1000

    orchestrator.llm_service.execute_auditor_review.return_value = auditor_result

    with patch.object(orchestrator, 'post_auditor_result'):
        orchestrator.execute_auditor_review(
            phase_id="phase-1",
            phase={},
            builder_result=builder_result,
            ci_result=None,
            project_rules=[],
            run_hints=[],
            attempt_index=2,
        )

    call_kwargs = orchestrator.llm_service.execute_auditor_review.call_args[1]
    assert call_kwargs["attempt_index"] == 2


def test_post_auditor_result_includes_tokens_used(tmp_path: Path):
    """Test that post_auditor_result includes tokens_used in payload."""
    orchestrator = make_auditor_orchestrator(tmp_path)

    auditor_result = Mock()
    auditor_result.approved = True
    auditor_result.issues_found = []
    auditor_result.auditor_messages = []
    auditor_result.tokens_used = 5000
    auditor_result.error = None

    with patch('autopack.executor.auditor_parsing.parse_auditor_result') as mock_parse:
        mock_parsed = Mock()
        mock_parsed.recommendation = "APPROVE"
        mock_parsed.confidence_overall = 0.9
        mock_parsed.suggested_patches = []
        mock_parse.return_value = mock_parsed

        orchestrator.post_auditor_result("phase-1", auditor_result)

    call_args = orchestrator.api_client.submit_auditor_result.call_args
    payload = call_args[0][2]
    assert payload["tokens_used"] == 5000


def test_post_auditor_result_sets_auditor_attempts_to_1(tmp_path: Path):
    """Test that post_auditor_result sets auditor_attempts to 1."""
    orchestrator = make_auditor_orchestrator(tmp_path)

    auditor_result = Mock()
    auditor_result.approved = True
    auditor_result.issues_found = []
    auditor_result.auditor_messages = []
    auditor_result.tokens_used = 1000
    auditor_result.error = None

    with patch('autopack.executor.auditor_parsing.parse_auditor_result') as mock_parse:
        mock_parsed = Mock()
        mock_parsed.recommendation = "APPROVE"
        mock_parsed.confidence_overall = 0.9
        mock_parsed.suggested_patches = []
        mock_parse.return_value = mock_parsed

        orchestrator.post_auditor_result("phase-1", auditor_result)

    call_args = orchestrator.api_client.submit_auditor_result.call_args
    payload = call_args[0][2]
    assert payload["auditor_attempts"] == 1


def test_post_auditor_result_handles_missing_issue_fields(tmp_path: Path):
    """Test that post_auditor_result handles issues with missing fields gracefully."""
    orchestrator = make_auditor_orchestrator(tmp_path)

    auditor_result = Mock()
    auditor_result.approved = False
    auditor_result.issues_found = [
        {
            "issue_key": "test-issue",
            # Missing other fields
        }
    ]
    auditor_result.auditor_messages = []
    auditor_result.tokens_used = 1000
    auditor_result.error = None

    with patch('autopack.executor.auditor_parsing.parse_auditor_result') as mock_parse:
        mock_parsed = Mock()
        mock_parsed.recommendation = "REQUEST_CHANGES"
        mock_parsed.confidence_overall = 0.8
        mock_parsed.suggested_patches = []
        mock_parse.return_value = mock_parsed

        orchestrator.post_auditor_result("phase-1", auditor_result)

    # Verify issue was formatted with defaults
    call_args = orchestrator.api_client.submit_auditor_result.call_args
    payload = call_args[0][2]
    issue = payload["issues_found"][0]
    assert issue["issue_key"] == "test-issue"
    assert issue["severity"] == "medium"  # default
    assert issue["source"] == "auditor"  # default
