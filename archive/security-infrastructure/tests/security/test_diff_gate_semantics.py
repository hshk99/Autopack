"""
Contract Test: Diff Gate Semantics

Guardrail: diff_gate.py correctly detects regressions and passes stable baselines.

Why This Matters:
- Diff gate is the enforcement mechanism (new findings = CI failure)
- False positives → developer friction
- False negatives → undetected vulnerabilities slip through

Coverage:
- Regression detection (new findings → exit 1)
- Stable baseline (no changes → exit 0)
- Removed findings (acceptable → exit 0)
- Empty baseline handling (with/without --allow-empty-baseline flag)
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def _run_diff_gate(baseline_json: list, current_json: list, allow_empty: bool = False) -> int:
    """
    Helper: Run diff_gate.py with temporary baseline and current files.

    Returns exit code (0 = pass, 1 = fail/regression).
    """
    repo_root = Path(__file__).parents[2]
    diff_gate_script = repo_root / "scripts" / "security" / "diff_gate.py"

    # Create temp files with delete=False to avoid Windows file locking issues
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as baseline_f:
        json.dump(baseline_json, baseline_f, indent=2)
        baseline_path = Path(baseline_f.name)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as current_f:
        json.dump(current_json, current_f, indent=2)
        current_path = Path(current_f.name)

    try:
        cmd = [
            sys.executable,
            str(diff_gate_script),
            "--baseline",
            str(baseline_path),
            "--current",
            str(current_path),
            "--name",
            "Test Gate",
        ]

        if allow_empty:
            cmd.append("--allow-empty-baseline")

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        return result.returncode
    finally:
        # Cleanup temp files (after subprocess completes)
        baseline_path.unlink(missing_ok=True)
        current_path.unlink(missing_ok=True)


def test_diff_gate_detects_new_findings():
    """
    Guardrail: Diff gate exits 1 when new findings appear (regression).
    """
    baseline = [
        {
            "tool": "trivy",
            "ruleId": "CVE-2023-0001",
            "artifactUri": "file.py",
            "messageHash": "abc123",
        }
    ]
    current = [
        {
            "tool": "trivy",
            "ruleId": "CVE-2023-0001",
            "artifactUri": "file.py",
            "messageHash": "abc123",
        },
        {
            "tool": "trivy",
            "ruleId": "CVE-2024-9999",
            "artifactUri": "new.py",
            "messageHash": "def456",
        },  # NEW
    ]

    exit_code = _run_diff_gate(baseline, current)
    assert exit_code == 1, (
        "Diff gate should exit 1 when new findings detected (regression)\\n"
        "This is the core enforcement mechanism."
    )


def test_diff_gate_passes_stable_baseline():
    """
    Guardrail: Diff gate exits 0 when current matches baseline exactly.
    """
    baseline = [
        {
            "tool": "codeql",
            "ruleId": "py/empty-except",
            "artifactUri": "src/main.py",
            "messageHash": "xyz789",
            "startLine": 42,
        }
    ]
    current = baseline.copy()  # Identical

    exit_code = _run_diff_gate(baseline, current)
    assert exit_code == 0, (
        "Diff gate should exit 0 when current matches baseline (no regression)\\n"
        "Stable baselines must not block CI."
    )


def test_diff_gate_allows_removed_findings():
    """
    Guardrail: Diff gate exits 0 when findings are removed (improvement).

    Removing findings = security improvement = acceptable.
    """
    baseline = [
        {
            "tool": "trivy",
            "ruleId": "CVE-2023-0001",
            "artifactUri": "file.py",
            "messageHash": "abc123",
        },
        {
            "tool": "trivy",
            "ruleId": "CVE-2023-0002",
            "artifactUri": "file.py",
            "messageHash": "def456",
        },
    ]
    current = [
        {
            "tool": "trivy",
            "ruleId": "CVE-2023-0001",
            "artifactUri": "file.py",
            "messageHash": "abc123",
        },
        # CVE-2023-0002 removed (fixed)
    ]

    exit_code = _run_diff_gate(baseline, current)
    assert exit_code == 0, (
        "Diff gate should exit 0 when findings are removed (security improvement)\\n"
        "Only new findings should block CI."
    )


def test_diff_gate_empty_baseline_without_flag_fails():
    """
    Guardrail: Empty baseline without --allow-empty-baseline flag exits 1.

    Prevents accidental use of uninitialized baselines (would allow all findings).
    """
    baseline = []
    current = [
        {
            "tool": "trivy",
            "ruleId": "CVE-2024-1111",
            "artifactUri": "test.py",
            "messageHash": "aaa111",
        }
    ]

    exit_code = _run_diff_gate(baseline, current, allow_empty=False)
    assert exit_code == 1, (
        "Diff gate should reject empty baseline (without --allow-empty-baseline flag)\\n"
        "This prevents uninitialized baselines from silently passing all findings."
    )


def test_diff_gate_empty_baseline_with_flag_allows_new_findings():
    """
    Guardrail: Empty baseline with --allow-empty-baseline flag exits 0 (bootstrap mode).

    Used during initial rollout; removed after baselines established.
    """
    baseline = []
    current = [
        {
            "tool": "codeql",
            "ruleId": "py/unused-import",
            "artifactUri": "app.py",
            "messageHash": "bbb222",
        }
    ]

    exit_code = _run_diff_gate(baseline, current, allow_empty=True)
    assert exit_code == 0, (
        "Diff gate should pass empty baseline with --allow-empty-baseline (bootstrap mode)\\n"
        "This flag is removed after baselines are established."
    )
