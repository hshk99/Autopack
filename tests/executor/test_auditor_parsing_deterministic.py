"""Contract-first tests for auditor parsing (BUILD-187 Phase 8).

These tests verify:
- Deterministic output for same inputs
- Explicit "unknown" indicators for uncertain data
- No guessing or LLM inference
- High-confidence parsing only
"""

from __future__ import annotations

import pytest


def test_parse_empty_messages():
    """Empty messages result in not_parsed status."""
    from autopack.executor.auditor_parsing import parse_auditor_result

    result = parse_auditor_result([], approved=True)

    assert result.parse_status == "not_parsed"
    assert "No auditor messages" in result.parse_notes[0]


def test_parse_with_prestructured_issues():
    """Pre-structured issues are parsed with high confidence."""
    from autopack.executor.auditor_parsing import parse_auditor_result

    issues = [
        {
            "issue_key": "ISS-001",
            "severity": "high",
            "description": "Missing error handling",
            "category": "error_handling",
        },
        {
            "issue_key": "ISS-002",
            "severity": "medium",
            "description": "Unused import",
        },
    ]

    result = parse_auditor_result(
        auditor_messages=["Review complete"],
        approved=False,
        issues_found=issues,
    )

    assert result.parse_status == "parsed"
    assert len(result.issues) == 2
    assert result.issues[0].issue_key == "ISS-001"
    assert result.issues[0].confidence == "high"


def test_parse_extracts_file_mentions():
    """File mentions are extracted from messages."""
    from autopack.executor.auditor_parsing import parse_auditor_result

    messages = [
        "Found issue in src/main.py",
        "Also check tests/test_main.py for related tests",
        "The config.yaml needs updating",
    ]

    result = parse_auditor_result(messages, approved=True)

    assert "src/main.py" in result.files_mentioned
    assert "tests/test_main.py" in result.files_mentioned
    assert "config.yaml" in result.files_mentioned


def test_parse_recommendation_from_approval():
    """Recommendation is derived from approval flag."""
    from autopack.executor.auditor_parsing import parse_auditor_result

    approved = parse_auditor_result([], approved=True)
    rejected = parse_auditor_result([], approved=False)

    assert approved.recommendation == "approve"
    assert rejected.recommendation == "revise"


def test_parse_unknown_severity_stays_unknown():
    """Unknown severity is not guessed."""
    from autopack.executor.auditor_parsing import parse_auditor_result

    issues = [
        {
            "issue_key": "ISS-001",
            "severity": "invalid_severity",
            "description": "Test issue",
        }
    ]

    result = parse_auditor_result([], approved=False, issues_found=issues)

    assert result.issues[0].severity == "unknown"


def test_parse_deterministic():
    """Same inputs always produce same output."""
    from autopack.executor.auditor_parsing import parse_auditor_result

    messages = ["Review found issues in src/foo.py"]
    issues = [{"issue_key": "ISS-001", "severity": "high", "description": "Test"}]

    result1 = parse_auditor_result(messages, approved=False, issues_found=issues)
    result2 = parse_auditor_result(messages, approved=False, issues_found=issues)
    result3 = parse_auditor_result(messages, approved=False, issues_found=issues)

    assert result1.to_dict() == result2.to_dict() == result3.to_dict()


def test_parse_quality_gate_result():
    """Quality gate results are parsed deterministically."""
    from autopack.executor.auditor_parsing import parse_quality_gate_result

    quality_report = {
        "quality_level": "acceptable",
        "blocked": False,
        "risk_assessment": {
            "risk_level": "low",
            "risk_score": 0.25,
        },
    }

    result = parse_quality_gate_result(quality_report)

    assert result["quality_level"] == "acceptable"
    assert result["risk_level"] == "low"
    assert result["risk_score"] == 0.25
    assert result["parse_confidence"] == "high"


def test_parse_quality_gate_missing_risk():
    """Missing risk data results in unknown."""
    from autopack.executor.auditor_parsing import parse_quality_gate_result

    quality_report = {
        "quality_level": "acceptable",
        "blocked": False,
    }

    result = parse_quality_gate_result(quality_report)

    assert result["risk_level"] == "unknown"
    assert result["risk_score"] is None
    assert result["parse_confidence"] == "unknown"


def test_file_extraction_filters_non_paths():
    """File extraction filters out non-file-path strings."""
    from autopack.executor.auditor_parsing import parse_auditor_result

    messages = [
        "See https://example.com/docs for more info",
        "Contact user@example.com for help",
        "Version 1.0.0 released",
        "Check src/main.py for details",
    ]

    result = parse_auditor_result(messages, approved=True)

    # URLs and emails should not be in files
    assert "https://example.com/docs" not in result.files_mentioned
    assert "user@example.com" not in result.files_mentioned
    assert "1.0.0" not in result.files_mentioned
    # Real file path should be found
    assert "src/main.py" in result.files_mentioned


def test_auditor_parse_result_serialization():
    """AuditorParseResult serializes to dict correctly."""
    from autopack.executor.auditor_parsing import AuditorParseResult, ParsedIssue

    result = AuditorParseResult(
        parse_status="parsed",
        confidence_overall="high",
        recommendation="approve",
        issues=[
            ParsedIssue(
                issue_key="ISS-001",
                severity="high",
                description="Test issue",
            )
        ],
        files_mentioned=["src/main.py"],
    )

    d = result.to_dict()

    assert d["parse_status"] == "parsed"
    assert len(d["issues"]) == 1
    assert d["issues"][0]["issue_key"] == "ISS-001"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
