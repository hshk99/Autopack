"""Tests for second opinion LLM integration (Phase B1)."""

import json
import os

import pytest

from autopack.diagnostics.second_opinion import (
    SecondOpinionConfig,
    SecondOpinionTriageSystem,
    TriageReport,
)


def test_second_opinion_disabled_by_default():
    """Test that second opinion is disabled by default (safe-by-default)."""
    system = SecondOpinionTriageSystem()

    assert not system.is_enabled()
    assert system.config.enabled is False


def test_second_opinion_enabled_when_configured():
    """Test that second opinion can be enabled via config."""
    config = SecondOpinionConfig(enabled=True)
    system = SecondOpinionTriageSystem(config=config)

    assert system.is_enabled()


def test_second_opinion_skips_when_disabled():
    """Test that triage is skipped when disabled."""
    system = SecondOpinionTriageSystem()  # disabled by default

    handoff_bundle = {
        "phase": {"name": "test", "state": "FAILED"},
        "failure_reason": "Tests failed",
    }

    result = system.generate_triage(handoff_bundle)

    assert result is None  # Disabled, so no triage generated


def test_second_opinion_mock_fallback_without_api_key(tmp_path, monkeypatch):
    """Test that second opinion falls back to mock when API key not set."""
    # Clear API key
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    config = SecondOpinionConfig(enabled=True)
    system = SecondOpinionTriageSystem(config=config)

    handoff_bundle = {
        "phase": {"name": "build", "state": "FAILED"},
        "failure_reason": "Compilation error",
        "diagnostics": {"error": "undefined reference"},
    }

    result = system.generate_triage(handoff_bundle)

    # Should return mock response
    assert result is not None
    assert isinstance(result, TriageReport)
    assert len(result.hypotheses) > 0
    assert 0.0 <= result.confidence <= 1.0


def test_second_opinion_budget_enforcement():
    """Test that token budget is enforced."""
    config = SecondOpinionConfig(
        enabled=True,
        token_budget=100,  # Very low budget
    )
    system = SecondOpinionTriageSystem(config=config)

    # Simulate using up budget
    system._tokens_used = 150

    assert not system.within_budget()

    handoff_bundle = {"phase": {"name": "test"}}
    result = system.generate_triage(handoff_bundle)

    assert result is None  # Budget exceeded, no triage generated


def test_second_opinion_token_tracking():
    """Test that token usage is tracked."""
    config = SecondOpinionConfig(enabled=True, token_budget=10000)
    system = SecondOpinionTriageSystem(config=config)

    assert system.get_tokens_used() == 0
    assert system.get_tokens_remaining() == 10000

    handoff_bundle = {
        "phase": {"name": "test", "state": "FAILED"},
        "failure_reason": "Error",
    }

    # Generate triage (will use mock)
    result = system.generate_triage(handoff_bundle)

    # Mock response has 0 tokens, but real response would increment
    # (this test validates the tracking mechanism exists)
    assert result is not None


def test_second_opinion_save_and_load(tmp_path):
    """Test saving and loading triage reports."""
    config = SecondOpinionConfig(enabled=True)
    system = SecondOpinionTriageSystem(config=config)

    # Generate mock triage
    handoff_bundle = {
        "phase": {"name": "test"},
        "failure_reason": "Test failure",
    }

    report = system.generate_triage(handoff_bundle)
    assert report is not None

    # Save report
    report_path = tmp_path / "second_opinion.json"
    system.save_triage_report(report, report_path)

    assert report_path.exists()

    # Load report
    loaded_report = system.load_triage_report(report_path)

    assert loaded_report is not None
    assert loaded_report.confidence == report.confidence
    assert len(loaded_report.hypotheses) == len(report.hypotheses)


def test_triage_report_to_dict():
    """Test TriageReport serialization."""
    report = TriageReport(
        hypotheses=[
            {
                "description": "Test hypothesis",
                "likelihood": 0.8,
                "evidence_for": ["Evidence 1"],
                "evidence_against": [],
            }
        ],
        missing_evidence=["Missing item 1"],
        next_probes=[{"type": "check", "description": "Check something"}],
        minimal_patch_strategy={
            "approach": "Fix the issue",
            "files_to_modify": ["file.py"],
            "key_changes": ["Change 1"],
            "risks": ["Risk 1"],
        },
        confidence=0.75,
        reasoning="Test reasoning",
    )

    report_dict = report.to_dict()

    assert "hypotheses" in report_dict
    assert "confidence" in report_dict
    assert "timestamp" in report_dict
    assert report_dict["confidence"] == 0.75


def test_triage_report_to_json():
    """Test TriageReport JSON serialization."""
    report = TriageReport(
        hypotheses=[],
        missing_evidence=[],
        next_probes=[],
        minimal_patch_strategy={},
        confidence=0.5,
        reasoning="Test",
    )

    json_str = report.to_json()

    # Should be valid JSON
    parsed = json.loads(json_str)
    assert parsed["confidence"] == 0.5


def test_second_opinion_bounded_output(tmp_path, monkeypatch):
    """Test that second opinion output is bounded (no huge prompts/responses)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    config = SecondOpinionConfig(
        enabled=True,
        max_tokens=8192,  # Bounded max tokens
    )
    system = SecondOpinionTriageSystem(config=config)

    # Create large handoff bundle
    huge_diagnostics = {"log": "x" * 100000}  # 100KB of data

    handoff_bundle = {
        "phase": {"name": "test"},
        "diagnostics": huge_diagnostics,
    }

    # Generate triage (uses mock)
    result = system.generate_triage(handoff_bundle)

    assert result is not None

    # Verify output is bounded
    report_json = result.to_json()
    assert len(report_json) < 50000  # Should be much smaller than input


@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set - skipping real API test",
)
def test_second_opinion_real_api_call(tmp_path):
    """Test real Anthropic API call (requires ANTHROPIC_API_KEY).

    This test is skipped unless ANTHROPIC_API_KEY is set in environment.
    Use for manual validation only - not part of regular CI.
    """
    config = SecondOpinionConfig(
        enabled=True,
        model="claude-opus-4",
        max_tokens=4096,
        token_budget=50000,
    )
    system = SecondOpinionTriageSystem(config=config)

    handoff_bundle = {
        "phase": {
            "name": "test-phase",
            "description": "Run unit tests",
            "state": "FAILED",
            "builder_attempts": 2,
            "max_builder_attempts": 5,
        },
        "failure_reason": "Tests failed: 3 tests failed out of 10",
        "diagnostics": {
            "test_output": "FAILED tests/test_module.py::test_function - AssertionError",
            "error_summary": "Expected 5 but got 3",
        },
    }

    result = system.generate_triage(handoff_bundle)

    # Should get real triage from API
    assert result is not None
    assert isinstance(result, TriageReport)
    assert len(result.hypotheses) > 0
    assert 0.0 <= result.confidence <= 1.0
    assert len(result.reasoning) > 0

    # Verify token tracking
    assert system.get_tokens_used() > 0
    assert system.within_budget()

    # Save to file for inspection
    output_path = tmp_path / "real_triage.json"
    system.save_triage_report(result, output_path)
    assert output_path.exists()

    print(f"\nReal triage saved to: {output_path}")
    print(f"Tokens used: {system.get_tokens_used()}")
    print(f"Confidence: {result.confidence}")
