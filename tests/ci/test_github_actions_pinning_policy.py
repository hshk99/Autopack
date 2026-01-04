"""
Test GitHub Actions pinning policy enforcement.

This test validates that check_github_actions_pinning.py correctly identifies
violations of the supply-chain security policy for GitHub Actions.

Policy enforced:
- Third-party actions MUST use full 40-char SHA pins
- First-party (actions/*) actions MAY use version tags
- Mutable refs (@master, @main, @vX for third-party) are BLOCKED
"""

import re
import subprocess
import tempfile
from pathlib import Path


def test_pinning_policy_passes_on_current_workflows():
    """
    Baseline test: current workflows should pass pinning policy.

    This test ensures the policy checker works and current state is compliant.
    """
    result = subprocess.run(
        ["python", "scripts/ci/check_github_actions_pinning.py"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Pinning policy failed on current workflows:\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )
    assert "[OK]" in result.stdout


def test_pinning_policy_allows_first_party_version_tags():
    """
    Verify policy allows actions/*@vX (first-party version tags).

    These are lower risk and commonly used with version tags.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        workflows = Path(tmpdir) / ".github" / "workflows"
        workflows.mkdir(parents=True)

        # Create test workflow with first-party version tags (allowed)
        test_yml = workflows / "test.yml"
        test_yml.write_text(
            """
name: Test
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - uses: actions/upload-artifact@v4
""",
            encoding="utf-8",
        )

        # Run checker from tmpdir
        result = subprocess.run(
            ["python", str(Path.cwd() / "scripts/ci/check_github_actions_pinning.py")],
            cwd=tmpdir,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"Policy should allow actions/*@vX:\n{result.stdout}"
        )


def test_pinning_policy_blocks_third_party_mutable_refs():
    """
    Verify policy blocks third-party actions with mutable refs.

    Mutable refs like @master or @v2 can be hijacked for supply-chain attacks.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        workflows = Path(tmpdir) / ".github" / "workflows"
        workflows.mkdir(parents=True)

        # Create test workflow with third-party mutable ref (blocked)
        test_yml = workflows / "test.yml"
        test_yml.write_text(
            """
name: Test
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: aquasecurity/trivy-action@master
""",
            encoding="utf-8",
        )

        # Run checker from tmpdir
        result = subprocess.run(
            ["python", str(Path.cwd() / "scripts/ci/check_github_actions_pinning.py")],
            cwd=tmpdir,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1, (
            f"Policy should block third-party @master:\n{result.stdout}"
        )
        assert "mutable ref not allowed" in result.stdout
        assert "trivy-action@master" in result.stdout


def test_pinning_policy_blocks_third_party_version_tags():
    """
    Verify policy blocks third-party actions with version tags (@vX).

    Third-party actions must use SHA pins for supply-chain security.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        workflows = Path(tmpdir) / ".github" / "workflows"
        workflows.mkdir(parents=True)

        # Create test workflow with third-party version tag (blocked)
        test_yml = workflows / "test.yml"
        test_yml.write_text(
            """
name: Test
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: gitleaks/gitleaks-action@v2
""",
            encoding="utf-8",
        )

        # Run checker from tmpdir
        result = subprocess.run(
            ["python", str(Path.cwd() / "scripts/ci/check_github_actions_pinning.py")],
            cwd=tmpdir,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1, (
            f"Policy should block third-party @v2:\n{result.stdout}"
        )
        assert "mutable ref not allowed" in result.stdout
        assert "gitleaks-action@v2" in result.stdout


def test_pinning_policy_allows_third_party_sha_pins():
    """
    Verify policy allows third-party actions with SHA pins.

    SHA pins are the required format for supply-chain security.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        workflows = Path(tmpdir) / ".github" / "workflows"
        workflows.mkdir(parents=True)

        # Create test workflow with third-party SHA pin (allowed)
        test_yml = workflows / "test.yml"
        test_yml.write_text(
            """
name: Test
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: aquasecurity/trivy-action@b6643a29fecd7f34b3597bc6acb0a98b03d33ff8  # v0.33.1
""",
            encoding="utf-8",
        )

        # Run checker from tmpdir
        result = subprocess.run(
            ["python", str(Path.cwd() / "scripts/ci/check_github_actions_pinning.py")],
            cwd=tmpdir,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"Policy should allow third-party SHA pins:\n{result.stdout}"
        )


def test_all_current_workflows_use_compliant_refs():
    """
    Guardrail: verify all .github/workflows/*.yml files are policy-compliant.

    This test ensures no workflow accidentally uses mutable refs or
    unpinned third-party actions.
    """
    workflows_dir = Path(".github/workflows")
    assert workflows_dir.exists(), "Workflows directory not found"

    # Pattern to find uses: lines
    uses_re = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)", re.MULTILINE)
    sha_re = re.compile(r"@[0-9a-f]{40}$", re.IGNORECASE)
    mutable_re = re.compile(r"@(master|main|v\d+)$", re.IGNORECASE)

    violations = []

    for workflow in workflows_dir.glob("*.yml"):
        content = workflow.read_text(encoding="utf-8")
        for match in uses_re.finditer(content):
            uses = match.group(1)

            # Skip first-party (allowed version tags)
            if uses.startswith("actions/"):
                continue

            # Check for mutable refs
            if mutable_re.search(uses):
                violations.append(f"{workflow.name}: mutable ref {uses}")
                continue

            # Check for SHA pin
            if not sha_re.search(uses):
                violations.append(f"{workflow.name}: non-SHA ref {uses}")

    assert not violations, (
        "Workflow pinning violations found:\n" + "\n".join(violations)
    )
