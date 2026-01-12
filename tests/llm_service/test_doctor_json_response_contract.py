"""Contract tests for Doctor JSON-only response behavior.

Tests that the doctor module returns JSON-only responses with no markdown
or explanatory text, and that the response structure is validated correctly.

Part of PR-SVC-3 (Item 1.1 god file refactoring).
"""

from unittest.mock import Mock
from autopack.llm.doctor import execute_doctor, _parse_doctor_json
from autopack.error_recovery import DoctorRequest, DoctorResponse


def test_doctor_returns_json_only():
    """Doctor should return JSON-only responses, not markdown."""
    # Create mock client
    mock_client = Mock()
    mock_completion = Mock()
    mock_completion.choices = [
        Mock(
            message=Mock(
                content='{"action": "retry_with_fix", "confidence": 0.85, "rationale": "Simple fix needed"}'
            )
        )
    ]
    mock_completion.usage = Mock(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    mock_client.client = Mock(
        chat=Mock(completions=Mock(create=Mock(return_value=mock_completion)))
    )

    # Create doctor request
    request = DoctorRequest(
        phase_id="test-phase-1",
        error_category="patch_apply_error",
        builder_attempts=2,
        health_budget={"http_500": 0, "patch_failures": 1, "total_failures": 1, "total_cap": 25},
    )

    # Execute doctor
    result = execute_doctor(
        client=mock_client,
        request=request,
        allow_escalation=False,
    )

    # Verify response is structured data
    assert isinstance(result, DoctorResponse)
    assert result.action == "retry_with_fix"
    assert result.confidence == 0.85
    assert result.rationale == "Simple fix needed"

    # Verify no markdown markers in response fields
    assert "```" not in str(result.action)
    assert "```" not in str(result.rationale)
    assert "##" not in str(result.rationale)


def test_doctor_response_structure():
    """Doctor response should have required fields."""
    # Create mock client
    mock_client = Mock()
    mock_completion = Mock()
    mock_completion.choices = [
        Mock(
            message=Mock(
                content='{"action": "replan", "confidence": 0.7, "rationale": "Phase needs redesign", "builder_hint": "Try different approach"}'
            )
        )
    ]
    mock_completion.usage = Mock(prompt_tokens=120, completion_tokens=60, total_tokens=180)
    mock_client.client = Mock(
        chat=Mock(completions=Mock(create=Mock(return_value=mock_completion)))
    )

    request = DoctorRequest(
        phase_id="test-phase-2",
        error_category="logic",
        builder_attempts=3,
        health_budget={"http_500": 0, "patch_failures": 2, "total_failures": 2, "total_cap": 25},
    )

    result = execute_doctor(
        client=mock_client,
        request=request,
        allow_escalation=False,
    )

    # Required fields
    assert hasattr(result, "action")
    assert hasattr(result, "confidence")
    assert hasattr(result, "rationale")

    # Optional fields
    assert hasattr(result, "builder_hint")
    assert hasattr(result, "suggested_patch")

    # Validate types
    assert isinstance(result.action, str)
    assert isinstance(result.confidence, float)
    assert isinstance(result.rationale, str)
    assert result.builder_hint is None or isinstance(result.builder_hint, str)


def test_doctor_handles_missing_diagnosis():
    """Doctor should handle cases where diagnosis is missing gracefully."""
    # Create mock client that returns minimal response
    mock_client = Mock()
    mock_completion = Mock()
    mock_completion.choices = [
        Mock(message=Mock(content='{"action": "replan", "confidence": 0.5}'))
    ]
    mock_completion.usage = Mock(prompt_tokens=100, completion_tokens=30, total_tokens=130)
    mock_client.client = Mock(
        chat=Mock(completions=Mock(create=Mock(return_value=mock_completion)))
    )

    request = DoctorRequest(
        phase_id="test-phase-3",
        error_category="unknown",
        builder_attempts=1,
        health_budget={"http_500": 0, "patch_failures": 0, "total_failures": 0, "total_cap": 25},
    )

    result = execute_doctor(
        client=mock_client,
        request=request,
        allow_escalation=False,
    )

    # Should have defaults for missing fields
    assert result.action == "replan"
    assert result.confidence == 0.5
    assert result.rationale  # Should have some rationale (default or "No rationale provided")
    assert result.builder_hint is None
    assert result.suggested_patch is None


def test_doctor_deterministic_parsing():
    """Doctor parsing should be deterministic for same input."""
    # Test that parsing the same JSON twice gives same result
    json_content = '{"action": "retry_with_fix", "confidence": 0.9, "rationale": "Test rationale", "builder_hint": "Test hint"}'

    result1 = _parse_doctor_json(json_content)
    result2 = _parse_doctor_json(json_content)

    # Same input should produce same output
    assert result1.action == result2.action
    assert result1.confidence == result2.confidence
    assert result1.rationale == result2.rationale
    assert result1.builder_hint == result2.builder_hint


def test_doctor_error_handling():
    """Doctor should handle client errors gracefully."""
    # Create mock client that raises an exception
    mock_client = Mock()
    mock_client.client = Mock(
        chat=Mock(completions=Mock(create=Mock(side_effect=Exception("API error"))))
    )

    request = DoctorRequest(
        phase_id="test-phase-4",
        error_category="network",
        builder_attempts=2,
        health_budget={"http_500": 1, "patch_failures": 0, "total_failures": 1, "total_cap": 25},
    )

    result = execute_doctor(
        client=mock_client,
        request=request,
        allow_escalation=False,
    )

    # Should return conservative default
    assert result.action == "replan"
    assert result.confidence == 0.2
    assert "failed" in result.rationale.lower()


def test_doctor_parses_json_from_markdown_block():
    """Doctor should extract JSON from markdown code blocks."""
    # Test Strategy 2: JSON in markdown block
    markdown_content = """Here's the diagnosis:
```json
{
  "action": "skip_phase",
  "confidence": 0.6,
  "rationale": "Phase is optional"
}
```
That's my recommendation."""

    result = _parse_doctor_json(markdown_content)

    assert result.action == "skip_phase"
    assert result.confidence == 0.6
    assert result.rationale == "Phase is optional"


def test_doctor_parses_json_embedded_in_text():
    """Doctor should extract JSON embedded in explanatory text."""
    # Test Strategy 3: JSON embedded in text
    text_content = """Based on my analysis, the recommended action is:
{"action": "mark_fatal", "confidence": 0.95, "rationale": "Unrecoverable error"}
This is the best approach."""

    result = _parse_doctor_json(text_content)

    assert result.action == "mark_fatal"
    assert result.confidence == 0.95
    assert result.rationale == "Unrecoverable error"


def test_doctor_validates_action_types():
    """Doctor should only return valid action types."""
    valid_actions = [
        "retry_with_fix",
        "replan",
        "rollback_run",
        "skip_phase",
        "mark_fatal",
        "execute_fix",
    ]

    # Test each valid action
    for action in valid_actions:
        json_content = f'{{"action": "{action}", "confidence": 0.7, "rationale": "Test"}}'
        result = _parse_doctor_json(json_content)
        assert result.action == action


def test_doctor_execute_fix_fields():
    """Doctor should include execute_fix fields when action is execute_fix."""
    json_content = """{
        "action": "execute_fix",
        "confidence": 0.9,
        "rationale": "Git conflict detected",
        "fix_commands": ["git checkout -- file.py"],
        "fix_type": "git",
        "verify_command": "git status"
    }"""

    result = _parse_doctor_json(json_content)

    assert result.action == "execute_fix"
    assert result.fix_commands == ["git checkout -- file.py"]
    assert result.fix_type == "git"
    assert result.verify_command == "git status"


def test_doctor_returns_no_markdown_in_rationale():
    """Doctor rationale should not contain markdown formatting."""
    mock_client = Mock()
    mock_completion = Mock()
    # Simulate a response with clean rationale (no markdown)
    mock_completion.choices = [
        Mock(
            message=Mock(
                content='{"action": "retry_with_fix", "confidence": 0.8, "rationale": "Patch line 42 mismatch. File was modified by previous phase."}'
            )
        )
    ]
    mock_completion.usage = Mock(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    mock_client.client = Mock(
        chat=Mock(completions=Mock(create=Mock(return_value=mock_completion)))
    )

    request = DoctorRequest(
        phase_id="test-phase-5",
        error_category="patch_apply_error",
        builder_attempts=2,
        health_budget={"http_500": 0, "patch_failures": 1, "total_failures": 1, "total_cap": 25},
    )

    result = execute_doctor(
        client=mock_client,
        request=request,
        allow_escalation=False,
    )

    # Verify rationale contains no markdown
    assert "```" not in result.rationale
    assert "##" not in result.rationale
    assert "**" not in result.rationale
    assert "__" not in result.rationale


def test_doctor_confidence_range():
    """Doctor confidence should be between 0.0 and 1.0."""
    test_cases = [
        ('{"action": "replan", "confidence": 0.0, "rationale": "Test"}', 0.0),
        ('{"action": "replan", "confidence": 0.5, "rationale": "Test"}', 0.5),
        ('{"action": "replan", "confidence": 1.0, "rationale": "Test"}', 1.0),
    ]

    for json_content, expected_confidence in test_cases:
        result = _parse_doctor_json(json_content)
        assert 0.0 <= result.confidence <= 1.0
        assert result.confidence == expected_confidence
