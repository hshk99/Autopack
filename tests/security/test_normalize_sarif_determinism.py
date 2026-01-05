"""
Contract Test: SARIF Normalization Determinism

Guardrail: normalize_sarif.py must produce identical output on repeated runs.

Why This Matters:
- Baselines are derived truth; normalization must be deterministic
- Non-deterministic normalization → false positive diff gate failures
- CI contract enforcement requires stable comparison keys

Coverage:
- Same SARIF input → same normalized output (multiple runs)
- Path normalization (Windows vs Linux)
- Sorting stability (findings always in same order)
"""

import json
import sys
from pathlib import Path

# Add scripts/security to path for imports
sys.path.insert(0, str(Path(__file__).parents[2] / "scripts" / "security"))

from normalize_sarif import normalize_sarif_file


def test_normalize_sarif_is_deterministic():
    """
    Guardrail: Running normalize_sarif_file() multiple times on the same input
    produces identical output (bit-for-bit identical JSON).
    """
    repo_root = Path(__file__).parents[2]
    fixture_path = repo_root / "tests" / "fixtures" / "security" / "trivy-sample.sarif"

    assert fixture_path.exists(), f"Missing fixture: {fixture_path}"

    # Run normalization 5 times
    runs = [normalize_sarif_file(fixture_path, tool_name="trivy") for _ in range(5)]

    # All runs must produce identical output
    serialized_runs = [json.dumps(run, sort_keys=True) for run in runs]
    assert all(s == serialized_runs[0] for s in serialized_runs), (
        "normalize_sarif_file() produced different output on repeated runs\\n"
        "This breaks deterministic baseline comparison."
    )


def test_normalize_sarif_path_normalization():
    """
    Guardrail: Path normalization converts Windows paths to forward slashes.

    This ensures baselines generated on Windows CI match Linux CI baselines.
    """
    repo_root = Path(__file__).parents[2]
    fixture_path = repo_root / "tests" / "fixtures" / "security" / "trivy-sample.sarif"

    findings = normalize_sarif_file(fixture_path, tool_name="trivy")

    # All artifact URIs must use forward slashes
    for finding in findings:
        artifact_uri = finding.get("artifactUri", "")
        assert "\\" not in artifact_uri, (
            f"Artifact URI contains backslash (non-portable): {artifact_uri}\\n"
            "Normalization must convert Windows paths to forward slashes."
        )


def test_normalize_sarif_sorting_stability():
    """
    Guardrail: Findings are sorted deterministically (same order every run).

    Non-stable sorting → baseline diff noise.
    """
    repo_root = Path(__file__).parents[2]
    fixture_path = repo_root / "tests" / "fixtures" / "security" / "codeql-sample.sarif"

    # Run normalization twice
    findings_1 = normalize_sarif_file(fixture_path, tool_name="codeql")
    findings_2 = normalize_sarif_file(fixture_path, tool_name="codeql")

    # Serialize to JSON strings for exact comparison
    json_1 = json.dumps(findings_1, sort_keys=True, indent=2)
    json_2 = json.dumps(findings_2, sort_keys=True, indent=2)

    assert json_1 == json_2, (
        "Finding order differs between runs (non-deterministic sorting)\\n"
        "This breaks baseline stability."
    )
