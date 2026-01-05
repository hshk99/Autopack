"""
Contract Test: SARIF Normalization Schema

Guardrail: Normalized findings must conform to expected schema.

Why This Matters:
- Diff gate assumes specific key structure
- Missing required fields → gate failures
- Schema drift → baseline corruption

Coverage:
- Required fields present (tool, ruleId, artifactUri, messageHash)
- Optional fields handled correctly (startLine, startColumn)
- No unexpected keys (schema stability)
"""

import sys
from pathlib import Path

# Add scripts/security to path for imports
sys.path.insert(0, str(Path(__file__).parents[2] / "scripts" / "security"))

from normalize_sarif import normalize_sarif_file


def test_normalized_findings_have_required_fields():
    """
    Guardrail: Every normalized finding must have required fields:
      - tool (str)
      - ruleId (str)
      - artifactUri (str)
      - messageHash (str, 16-char SHA256 prefix)
    """
    repo_root = Path(__file__).parents[2]
    fixture_path = repo_root / "tests" / "fixtures" / "security" / "trivy-sample.sarif"

    findings = normalize_sarif_file(fixture_path, tool_name="trivy")

    assert len(findings) > 0, "Fixture should have at least one finding"

    for finding in findings:
        # Required fields
        assert "tool" in finding, "Missing required field: tool"
        assert "ruleId" in finding, "Missing required field: ruleId"
        assert "artifactUri" in finding, "Missing required field: artifactUri"
        assert "messageHash" in finding, "Missing required field: messageHash"

        # Type checks
        assert isinstance(finding["tool"], str), "tool must be string"
        assert isinstance(finding["ruleId"], str), "ruleId must be string"
        assert isinstance(finding["artifactUri"], str), "artifactUri must be string"
        assert isinstance(finding["messageHash"], str), "messageHash must be string"

        # messageHash should be 16-char hex (SHA256 prefix)
        assert (
            len(finding["messageHash"]) == 16
        ), f"messageHash should be 16 chars, got {len(finding['messageHash'])}"
        assert all(
            c in "0123456789abcdef" for c in finding["messageHash"]
        ), "messageHash should be hex string"


def test_normalized_findings_optional_location_fields():
    """
    Guardrail: Optional location fields (startLine, startColumn) are integers when present.

    CodeQL findings include line/column; Trivy often does not.
    """
    repo_root = Path(__file__).parents[2]
    fixture_path = repo_root / "tests" / "fixtures" / "security" / "codeql-sample.sarif"

    findings = normalize_sarif_file(fixture_path, tool_name="codeql")

    assert len(findings) > 0, "Fixture should have at least one finding"

    for finding in findings:
        # If startLine present, must be int
        if "startLine" in finding:
            assert isinstance(
                finding["startLine"], int
            ), f"startLine must be int, got {type(finding['startLine'])}"

        # If startColumn present, must be int
        if "startColumn" in finding:
            assert isinstance(
                finding["startColumn"], int
            ), f"startColumn must be int, got {type(finding['startColumn'])}"


def test_normalized_findings_no_unexpected_keys():
    """
    Guardrail: Normalized findings should only have expected keys.

    Allowed keys: tool, ruleId, artifactUri, messageHash, startLine, startColumn, fingerprint

    Unexpected keys → schema drift → potential baseline corruption.
    """
    repo_root = Path(__file__).parents[2]
    fixture_path = repo_root / "tests" / "fixtures" / "security" / "trivy-sample.sarif"

    findings = normalize_sarif_file(fixture_path, tool_name="trivy")

    allowed_keys = {
        "tool",
        "ruleId",
        "artifactUri",
        "messageHash",
        "startLine",
        "startColumn",
        "fingerprint",
    }

    for finding in findings:
        unexpected_keys = set(finding.keys()) - allowed_keys
        assert not unexpected_keys, (
            f"Unexpected keys in normalized finding: {unexpected_keys}\\n"
            "This indicates schema drift. Update schema contract or fix normalization."
        )
