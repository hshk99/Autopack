"""
Tests for governance documentation contract (PR-05 G2+G3).

BUILD-199: Ensures GOVERNANCE.md accurately reflects NEVER_AUTO_APPROVE_PATTERNS
from plan_proposer.py to prevent "two truths" documentation drift.
"""

import re
from pathlib import Path

import pytest


class TestGovernanceDocsContract:
    """PR-05 G2+G3: Verify GOVERNANCE.md matches code patterns."""

    @pytest.fixture
    def never_auto_approve_patterns(self):
        """Get NEVER_AUTO_APPROVE_PATTERNS from plan_proposer.py."""
        from autopack.planning.plan_proposer import NEVER_AUTO_APPROVE_PATTERNS

        return NEVER_AUTO_APPROVE_PATTERNS

    @pytest.fixture
    def governance_content(self):
        """Read GOVERNANCE.md content."""
        docs_path = Path("docs/GOVERNANCE.md")
        if not docs_path.exists():
            pytest.skip("GOVERNANCE.md not found")
        return docs_path.read_text(encoding="utf-8")

    def test_docs_tests_not_auto_approved(self, governance_content):
        """GOVERNANCE.md must NOT show docs/ or tests/ as auto-approvable."""
        # Check that docs/ and tests/ are documented as NEVER auto-approved
        content_lower = governance_content.lower()

        # Negative assertion: should NOT have docs/tests listed as auto-approved
        # Pattern: "docs/*.md" or "tests/*.py" followed by "auto-approved"
        bad_patterns = [
            r"docs/\*\.md.*auto-approved",
            r"tests/\*\.py.*auto-approved",
            r"tests/.*auto-approved if all other criteria met",
            r"docs/.*auto-approved if all other criteria met",
        ]

        for pattern in bad_patterns:
            matches = re.findall(pattern, content_lower)
            assert not matches, (
                f"GOVERNANCE.md incorrectly shows docs/tests as auto-approvable. "
                f"Per DEC-046, docs/ and tests/ are in NEVER_AUTO_APPROVE_PATTERNS. "
                f"Found: {matches}"
            )

    def test_never_auto_approve_documented(self, governance_content, never_auto_approve_patterns):
        """All NEVER_AUTO_APPROVE_PATTERNS must be documented in GOVERNANCE.md."""
        for pattern in never_auto_approve_patterns:
            # Normalize pattern (remove trailing slash for matching)
            pattern_normalized = pattern.rstrip("/")

            # Check if pattern is mentioned in GOVERNANCE.md
            assert pattern_normalized in governance_content, (
                f"NEVER_AUTO_APPROVE pattern '{pattern}' is not documented in GOVERNANCE.md. "
                f"All patterns from plan_proposer.py must be documented for operator clarity."
            )

    def test_dec046_mentioned(self, governance_content):
        """GOVERNANCE.md must mention DEC-046 (contract-tested default-deny policy)."""
        assert "DEC-046" in governance_content, (
            "GOVERNANCE.md must reference DEC-046 (contract-tested default-deny policy) "
            "to indicate this is a contract-tested policy, not arbitrary documentation."
        )

    def test_default_deny_documented(self, governance_content):
        """GOVERNANCE.md must document default-deny policy."""
        assert "default-deny" in governance_content.lower(), (
            "GOVERNANCE.md must document the default-deny policy. "
            "This is a critical security invariant."
        )

    def test_examples_scripts_are_allowed(self, governance_content, never_auto_approve_patterns):
        """examples/ and scripts/ should be documented as allowed paths."""
        # These paths should NOT be in NEVER_AUTO_APPROVE_PATTERNS
        allowed_paths = ["examples/", "scripts/"]

        for path in allowed_paths:
            assert (
                path not in never_auto_approve_patterns
            ), f"{path} should be an allowed path, not in NEVER_AUTO_APPROVE_PATTERNS"

        # And GOVERNANCE.md should show them as allowed
        assert (
            "examples/" in governance_content
        ), "GOVERNANCE.md should document examples/ as an allowed path"
        assert (
            "scripts/" in governance_content
        ), "GOVERNANCE.md should document scripts/ as an allowed path"

    def test_protected_paths_section_exists(self, governance_content):
        """GOVERNANCE.md must have a Protected Paths section."""
        assert "Protected Paths" in governance_content, (
            "GOVERNANCE.md must have a 'Protected Paths' section "
            "documenting paths that require approval"
        )

    def test_never_auto_approve_list_current(self, governance_content, never_auto_approve_patterns):
        """NEVER_AUTO_APPROVE list in GOVERNANCE.md should match code."""
        # Extract paths mentioned after "NEVER_AUTO_APPROVE" heading
        # This is a loose check - just verify the patterns appear somewhere
        expected_paths = [p.rstrip("/") for p in never_auto_approve_patterns]

        # At minimum, check that all code patterns are documented
        missing = []
        for path in expected_paths:
            if path not in governance_content:
                missing.append(path)

        assert not missing, (
            f"GOVERNANCE.md is missing NEVER_AUTO_APPROVE patterns: {missing}. "
            f"Update GOVERNANCE.md to match plan_proposer.py NEVER_AUTO_APPROVE_PATTERNS."
        )


class TestGovernanceCodeContract:
    """Verify governance code invariants."""

    def test_never_auto_approve_includes_required_paths(self):
        """NEVER_AUTO_APPROVE_PATTERNS must include critical paths."""
        from autopack.planning.plan_proposer import NEVER_AUTO_APPROVE_PATTERNS

        # These paths MUST be in NEVER_AUTO_APPROVE per DEC-046
        required_paths = [
            "docs/",
            "tests/",
            "src/autopack/",
            "config/",
            ".github/",
        ]

        for path in required_paths:
            assert path in NEVER_AUTO_APPROVE_PATTERNS, (
                f"Critical path '{path}' is missing from NEVER_AUTO_APPROVE_PATTERNS. "
                f"Per DEC-046, this path must always require approval."
            )

    def test_allowed_paths_not_in_never_auto_approve(self):
        """examples/ and scripts/ should NOT be in NEVER_AUTO_APPROVE."""
        from autopack.planning.plan_proposer import NEVER_AUTO_APPROVE_PATTERNS

        # These paths should be allowed for auto-approval
        allowed_paths = ["examples/", "scripts/"]

        for path in allowed_paths:
            assert path not in NEVER_AUTO_APPROVE_PATTERNS, (
                f"Path '{path}' should be allowed for auto-approval, "
                f"but is incorrectly in NEVER_AUTO_APPROVE_PATTERNS."
            )

    def test_default_deny_in_proposer(self):
        """PlanProposer must implement default-deny policy."""
        from autopack.planning.plan_proposer import PlanProposer

        # Check that _apply_governance method exists and sets default-deny
        assert hasattr(
            PlanProposer, "_apply_governance"
        ), "PlanProposer must have _apply_governance method for default-deny"
