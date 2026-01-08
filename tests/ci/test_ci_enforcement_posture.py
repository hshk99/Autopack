"""CI enforcement posture contract tests (PR5 - P1-CI-002).

Contract tests ensuring:
1. CI_ENFORCEMENT_POSTURE.md exists and documents all workflows
2. Workflows match documented blocking/non-blocking status
3. Key jobs are correctly categorized

Security contract: Contributors can answer "will this fail CI?" by reading one doc.
"""

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent.parent


class TestCIEnforcementPostureDocument:
    """Verify CI posture documentation exists and is complete."""

    def test_posture_doc_exists(self):
        """CI_ENFORCEMENT_POSTURE.md must exist."""
        posture_doc = REPO_ROOT / "docs" / "CI_ENFORCEMENT_POSTURE.md"
        assert (
            posture_doc.exists()
        ), "docs/CI_ENFORCEMENT_POSTURE.md is required for CI transparency"

    def test_posture_doc_has_quick_reference_table(self):
        """Posture doc should have a quick reference table."""
        posture_doc = REPO_ROOT / "docs" / "CI_ENFORCEMENT_POSTURE.md"
        content = posture_doc.read_text(encoding="utf-8")

        assert "Quick Reference" in content, "Posture doc should have Quick Reference section"
        assert "Blocks PR?" in content, "Posture doc should have blocking status column"

    def test_posture_doc_documents_key_checks(self):
        """Posture doc should document all key CI checks."""
        posture_doc = REPO_ROOT / "docs" / "CI_ENFORCEMENT_POSTURE.md"
        content = posture_doc.read_text(encoding="utf-8")

        key_checks = [
            "Ruff",
            "Black",
            "Core tests",
            "mypy",  # Should be documented as non-blocking
            "Aspirational",
            "Research",
            "Security",
            "Frontend",
        ]

        for check in key_checks:
            assert check.lower() in content.lower(), f"Posture doc should document {check}"


class TestCIWorkflowConsistency:
    """Verify CI workflows match documented posture."""

    def test_ci_yml_exists(self):
        """ci.yml must exist."""
        ci_yml = REPO_ROOT / ".github" / "workflows" / "ci.yml"
        assert ci_yml.exists(), "ci.yml workflow is required"

    def test_mypy_is_non_blocking(self):
        """mypy check should be non-blocking (continue-on-error: true)."""
        ci_yml = REPO_ROOT / ".github" / "workflows" / "ci.yml"
        content = ci_yml.read_text(encoding="utf-8")

        # Find mypy step and check for continue-on-error
        # The pattern should be: mypy followed by continue-on-error
        assert (
            "continue-on-error: true" in content
        ), "ci.yml should have at least one continue-on-error step"

        # Check that mypy section has continue-on-error
        mypy_match = re.search(
            r"Type check with mypy.*?continue-on-error:\s*true", content, re.DOTALL
        )
        assert (
            mypy_match is not None
        ), "mypy step should have continue-on-error: true for staged adoption"

    def test_aspirational_tests_non_blocking(self):
        """Aspirational tests should be non-blocking."""
        ci_yml = REPO_ROOT / ".github" / "workflows" / "ci.yml"
        content = ci_yml.read_text(encoding="utf-8")

        # Check that aspirational job has continue-on-error
        aspirational_match = re.search(
            r"test-aspirational:.*?continue-on-error:\s*true", content, re.DOTALL
        )
        assert (
            aspirational_match is not None
        ), "Aspirational tests job should have continue-on-error: true"

    def test_research_tests_non_blocking(self):
        """Research tests should be non-blocking."""
        ci_yml = REPO_ROOT / ".github" / "workflows" / "ci.yml"
        content = ci_yml.read_text(encoding="utf-8")

        # Check that research job has continue-on-error
        research_match = re.search(
            r"test-research:.*?continue-on-error:\s*true", content, re.DOTALL
        )
        assert research_match is not None, "Research tests job should have continue-on-error: true"

    def test_core_tests_are_blocking(self):
        """Core tests should NOT have continue-on-error."""
        ci_yml = REPO_ROOT / ".github" / "workflows" / "ci.yml"
        content = ci_yml.read_text(encoding="utf-8")

        # Find test-core section
        core_match = re.search(r"test-core:.*?(?=\n  \w+-\w+:|\n  \w+:|\Z)", content, re.DOTALL)
        assert core_match is not None, "test-core job should exist"

        _core_section = core_match.group(0)  # noqa: F841 - for future assertions
        # Core tests should NOT have continue-on-error at job level
        # (Individual steps may have it, but job-level should block)
        job_level_continue = re.search(
            r"test-core:\s+\n.*?continue-on-error:\s*true\s+\n\s+(?:runs-on|services|steps)",
            content,
            re.DOTALL,
        )
        assert job_level_continue is None, "Core tests job should NOT have continue-on-error: true"


class TestSecurityWorkflowPosture:
    """Verify security workflows match documented posture."""

    def test_security_yml_exists(self):
        """security.yml must exist."""
        security_yml = REPO_ROOT / ".github" / "workflows" / "security.yml"
        assert security_yml.exists(), "security.yml workflow is required"

    def test_security_artifacts_is_informational(self):
        """security-artifacts.yml should be informational (continue-on-error)."""
        artifacts_yml = REPO_ROOT / ".github" / "workflows" / "security-artifacts.yml"
        if not artifacts_yml.exists():
            pytest.skip("security-artifacts.yml not found")

        content = artifacts_yml.read_text(encoding="utf-8")
        assert (
            "continue-on-error" in content
        ), "security-artifacts.yml should have continue-on-error for informational checks"


class TestDocLinkScanPosture:
    """Verify doc link scan is non-blocking."""

    def test_deep_scan_is_non_blocking(self):
        """doc-link-deep-scan.yml should be non-blocking or report-only."""
        deep_scan_yml = REPO_ROOT / ".github" / "workflows" / "doc-link-deep-scan.yml"
        if not deep_scan_yml.exists():
            pytest.skip("doc-link-deep-scan.yml not found")

        content = deep_scan_yml.read_text(encoding="utf-8")
        # Should have continue-on-error OR be a workflow_dispatch only
        is_non_blocking = "continue-on-error" in content or "workflow_dispatch" in content
        assert is_non_blocking, "doc-link-deep-scan.yml should be non-blocking or manual-only"


class TestCoveragePolicy:
    """Verify coverage policy is documented."""

    def test_coverage_policy_documented(self):
        """Coverage policy should be documented in posture doc."""
        posture_doc = REPO_ROOT / "docs" / "CI_ENFORCEMENT_POSTURE.md"
        content = posture_doc.read_text(encoding="utf-8")

        assert "Coverage" in content, "Posture doc should document coverage policy"
        assert (
            "Codecov" in content or "coverage" in content.lower()
        ), "Posture doc should mention coverage tooling"
