"""
Contract Test: Baseline Update Tool Determinism

Guardrail: update_baseline.py produces identical output on repeated runs.

Why This Matters:
- Baselines are committed to git (reviewable diffs)
- Non-deterministic writes → noisy git diffs
- Stable output required for SECBASE audit trail

Coverage:
- Same SARIF input → identical baseline file (bit-for-bit)
- Sorted JSON output (stable key order, stable finding order)
- Trailing newline (git-friendly)
"""

import json
import sys
import tempfile
from pathlib import Path

# Add scripts/security to path for imports
sys.path.insert(0, str(Path(__file__).parents[2] / "scripts" / "security"))

from update_baseline import write_baseline


def test_write_baseline_is_deterministic():
    """
    Guardrail: write_baseline() produces identical files on repeated runs.

    Same findings → same file content (byte-for-byte).
    """
    findings = [
        {"tool": "trivy", "ruleId": "CVE-2024-5678", "artifactUri": "requirements.txt", "messageHash": "abc123"},
        {"tool": "trivy", "ruleId": "CVE-2024-1234", "artifactUri": "Dockerfile", "messageHash": "def456"},
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        baseline_path = Path(tmpdir) / "test-baseline.json"

        # Write baseline 3 times
        write_baseline(baseline_path, findings)
        content_1 = baseline_path.read_text(encoding="utf-8")

        write_baseline(baseline_path, findings)
        content_2 = baseline_path.read_text(encoding="utf-8")

        write_baseline(baseline_path, findings)
        content_3 = baseline_path.read_text(encoding="utf-8")

        assert content_1 == content_2 == content_3, (
            "write_baseline() produced different output on repeated runs\\n"
            "This creates noisy git diffs and breaks audit trail."
        )


def test_write_baseline_sorts_findings():
    """
    Guardrail: Findings are sorted deterministically in written baseline.

    Unsorted findings → unstable diffs when findings added/removed.
    """
    # Deliberately unsorted input
    findings = [
        {"tool": "codeql", "ruleId": "py/unused-local-variable", "artifactUri": "zzz.py", "messageHash": "zzz999"},
        {"tool": "codeql", "ruleId": "py/empty-except", "artifactUri": "aaa.py", "messageHash": "aaa111"},
        {"tool": "codeql", "ruleId": "py/cyclic-import", "artifactUri": "mmm.py", "messageHash": "mmm555"},
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        baseline_path = Path(tmpdir) / "sorted-baseline.json"
        write_baseline(baseline_path, findings)

        written_findings = json.loads(baseline_path.read_text(encoding="utf-8"))

        # Findings should be sorted (by JSON representation)
        serialized = [json.dumps(f, sort_keys=True) for f in written_findings]
        assert serialized == sorted(serialized), (
            "Findings not sorted in written baseline\\n"
            "This causes unstable diffs and breaks determinism."
        )


def test_write_baseline_has_trailing_newline():
    """
    Guardrail: Baseline files end with newline (git-friendly).

    Missing trailing newline → git diff shows "No newline at end of file" warning.
    """
    findings = [
        {"tool": "trivy", "ruleId": "CVE-2024-0000", "artifactUri": "test.txt", "messageHash": "test00"}
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        baseline_path = Path(tmpdir) / "newline-test.json"
        write_baseline(baseline_path, findings)

        content = baseline_path.read_text(encoding="utf-8")
        assert content.endswith("\n"), (
            "Baseline file missing trailing newline\n"
            "This causes git diff warnings and breaks conventions."
        )


def test_write_baseline_stable_json_formatting():
    """
    Guardrail: JSON output uses stable formatting (indent=2, sort_keys=True).

    Unstable formatting → noisy diffs on baseline updates.
    """
    findings = [
        {"tool": "codeql", "ruleId": "py/test", "artifactUri": "src/app.py", "messageHash": "hash12", "startLine": 10}
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        baseline_path = Path(tmpdir) / "format-test.json"
        write_baseline(baseline_path, findings)

        content = baseline_path.read_text(encoding="utf-8")

        # Should be pretty-printed with 2-space indent
        assert "  " in content, "JSON should be indented (not minified)"

        # Parse and verify keys are sorted
        parsed = json.loads(content)
        for finding in parsed:
            keys = list(finding.keys())
            assert keys == sorted(keys), (
                f"Keys not sorted: {keys}\\n"
                "write_baseline() must use sort_keys=True for stable output."
            )
