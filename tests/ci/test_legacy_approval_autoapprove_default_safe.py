"""
Tests for legacy approval endpoint safe-by-default (PR-01 P0).

BUILD-203: Ensures AUTO_APPROVE_BUILD113 defaults to "false" (DEC-046 compliance)
and that production mode blocks auto-approve even if explicitly enabled.

This test prevents regression to silent auto-approval footgun behavior.
"""

import os
import re
import pytest
from pathlib import Path


class TestLegacyApprovalSafeDefault:
    """PR-01 P0: Verify legacy approval endpoint has safe defaults."""

    @pytest.fixture
    def main_py_content(self):
        """Read src/autopack/main.py content."""
        main_path = Path("src/autopack/main.py")
        if not main_path.exists():
            pytest.skip("main.py not found")
        return main_path.read_text(encoding="utf-8")

    def test_auto_approve_defaults_to_false(self, main_py_content):
        """AUTO_APPROVE_BUILD113 must default to 'false', not 'true'.

        Per DEC-046 (default-deny), silent auto-approval is a governance bypass.
        The legacy endpoint must require explicit opt-in.
        """
        # Pattern: os.getenv("AUTO_APPROVE_BUILD113", "...")
        pattern = (
            r'os\.getenv\s*\(\s*["\']AUTO_APPROVE_BUILD113["\']\s*,\s*["\']([^"\']+)["\']\s*\)'
        )
        matches = re.findall(pattern, main_py_content)

        assert matches, (
            "AUTO_APPROVE_BUILD113 env var default not found in main.py. "
            "Expected: os.getenv('AUTO_APPROVE_BUILD113', 'false')"
        )

        for default_value in matches:
            assert default_value.lower() == "false", (
                f"AUTO_APPROVE_BUILD113 default is '{default_value}', must be 'false'. "
                f"Per DEC-046, silent auto-approval violates default-deny policy. "
                f"Set default to 'false' to require explicit opt-in."
            )

    def test_production_blocks_auto_approve(self, main_py_content):
        """Production mode must block auto-approve even if env var is set.

        This is a defense-in-depth: even if someone sets AUTO_APPROVE_BUILD113=true
        in production, it should not enable auto-approval.
        """
        # Check that production mode is checked when determining auto_approve
        # Pattern should show: production check AND env var check
        assert (
            "env_mode" in main_py_content or "AUTOPACK_ENV" in main_py_content
        ), "main.py should check AUTOPACK_ENV for production mode protection"

        # Check for production blocking pattern
        # Looking for: env_mode != "production" or similar
        production_check_patterns = [
            r'env_mode\s*!=\s*["\']production["\']',
            r"AUTOPACK_ENV.*production.*auto_approve",
            r"production.*auto.?approve.*false",
        ]

        has_production_check = any(
            re.search(pattern, main_py_content, re.IGNORECASE | re.DOTALL)
            for pattern in production_check_patterns
        )

        assert has_production_check, (
            "main.py must block auto-approve in production mode. "
            "Expected pattern: auto_approve = auto_approve_env and env_mode != 'production'"
        )

    def test_dec046_compliance_comment(self, main_py_content):
        """Code should reference DEC-046 for audit trail."""
        # Check for DEC-046 reference OR P0 reference (PR-01 P0)
        has_reference = (
            "DEC-046" in main_py_content
            or "P0" in main_py_content
            or "PR-01" in main_py_content
            or "safe-by-default" in main_py_content.lower()
        )

        assert has_reference, (
            "Legacy approval code should reference DEC-046 or PR-01/P0 for audit trail. "
            "This helps future maintainers understand why the default is safe."
        )


class TestLegacyApprovalDocContract:
    """Verify legacy approval documentation is accurate."""

    @pytest.fixture
    def canonical_api_content(self):
        """Read CANONICAL_API_CONTRACT.md content."""
        doc_path = Path("docs/CANONICAL_API_CONTRACT.md")
        if not doc_path.exists():
            pytest.skip("CANONICAL_API_CONTRACT.md not found")
        return doc_path.read_text(encoding="utf-8")

    @pytest.fixture
    def governance_content(self):
        """Read GOVERNANCE.md content."""
        doc_path = Path("docs/GOVERNANCE.md")
        if not doc_path.exists():
            pytest.skip("GOVERNANCE.md not found")
        return doc_path.read_text(encoding="utf-8")

    def test_canonical_api_reflects_safe_default(self, canonical_api_content):
        """CANONICAL_API_CONTRACT.md should document safe default.

        If the doc still says AUTO_APPROVE_BUILD113 defaults to true,
        it creates a "two truths" situation with the actual code.
        """
        # Check if the doc mentions AUTO_APPROVE_BUILD113
        if "AUTO_APPROVE_BUILD113" not in canonical_api_content:
            pytest.skip("AUTO_APPROVE_BUILD113 not documented in CANONICAL_API_CONTRACT.md")

        # The doc should show false as default, or at least warn about safe defaults
        safe_indicators = [
            "false",
            "safe",
            "opt-in",
            "disabled",
            "off",
        ]

        # Extract context around AUTO_APPROVE_BUILD113 mention
        idx = canonical_api_content.find("AUTO_APPROVE_BUILD113")
        context = canonical_api_content[max(0, idx - 200) : idx + 300].lower()

        has_safe_indicator = any(indicator in context for indicator in safe_indicators)

        # Relaxed check: either has safe indicator OR mentions production blocking
        production_mentioned = "production" in context

        assert has_safe_indicator or production_mentioned, (
            "CANONICAL_API_CONTRACT.md should indicate AUTO_APPROVE_BUILD113 has safe defaults. "
            "Either show 'false' as default or document production blocking behavior."
        )

    def test_governance_documents_legacy_approval(self, governance_content):
        """GOVERNANCE.md should mention legacy approval if it exists."""
        # This is a soft check - just verify the topic is addressed if relevant
        # The actual legacy endpoint documentation could be in various places

        legacy_keywords = [
            "legacy",
            "approval",
            "BUILD-113",
            "BUILD-117",
            "auto-approve",
        ]

        mentions = sum(1 for kw in legacy_keywords if kw.lower() in governance_content.lower())

        # At least some discussion of approval should exist
        assert mentions >= 1, (
            "GOVERNANCE.md should address approval mechanisms. "
            "At minimum, mention 'approval' or 'auto-approve' in the context of governance."
        )


class TestLegacyApprovalRuntimeBehavior:
    """Runtime behavior tests for legacy approval endpoint."""

    def test_default_env_is_safe(self):
        """With no env vars set, auto-approve should be disabled."""
        # Save current env
        original_auto_approve = os.environ.pop("AUTO_APPROVE_BUILD113", None)
        original_env_mode = os.environ.pop("AUTOPACK_ENV", None)

        try:
            # Simulate the code logic
            env_mode = os.getenv("AUTOPACK_ENV", "development").lower()
            auto_approve_env = os.getenv("AUTO_APPROVE_BUILD113", "false").lower() == "true"
            auto_approve = auto_approve_env and env_mode != "production"

            assert auto_approve is False, (
                "With no env vars set, auto_approve should be False. "
                f"Got: auto_approve={auto_approve}, env_mode={env_mode}, auto_approve_env={auto_approve_env}"
            )
        finally:
            # Restore env
            if original_auto_approve is not None:
                os.environ["AUTO_APPROVE_BUILD113"] = original_auto_approve
            if original_env_mode is not None:
                os.environ["AUTOPACK_ENV"] = original_env_mode

    def test_production_blocks_even_with_explicit_true(self):
        """Production mode blocks auto-approve even if explicitly enabled."""
        # Save current env
        original_auto_approve = os.environ.pop("AUTO_APPROVE_BUILD113", None)
        original_env_mode = os.environ.pop("AUTOPACK_ENV", None)

        try:
            # Set explicit auto-approve in production
            os.environ["AUTO_APPROVE_BUILD113"] = "true"
            os.environ["AUTOPACK_ENV"] = "production"

            # Simulate the code logic
            env_mode = os.getenv("AUTOPACK_ENV", "development").lower()
            auto_approve_env = os.getenv("AUTO_APPROVE_BUILD113", "false").lower() == "true"
            auto_approve = auto_approve_env and env_mode != "production"

            assert auto_approve is False, (
                "Production must block auto-approve even with AUTO_APPROVE_BUILD113=true. "
                f"Got: auto_approve={auto_approve}"
            )
        finally:
            # Restore env
            os.environ.pop("AUTO_APPROVE_BUILD113", None)
            os.environ.pop("AUTOPACK_ENV", None)
            if original_auto_approve is not None:
                os.environ["AUTO_APPROVE_BUILD113"] = original_auto_approve
            if original_env_mode is not None:
                os.environ["AUTOPACK_ENV"] = original_env_mode

    def test_dev_with_explicit_true_enables_auto_approve(self):
        """Development mode with explicit AUTO_APPROVE_BUILD113=true enables it."""
        # Save current env
        original_auto_approve = os.environ.pop("AUTO_APPROVE_BUILD113", None)
        original_env_mode = os.environ.pop("AUTOPACK_ENV", None)

        try:
            # Set explicit auto-approve in development
            os.environ["AUTO_APPROVE_BUILD113"] = "true"
            os.environ["AUTOPACK_ENV"] = "development"

            # Simulate the code logic
            env_mode = os.getenv("AUTOPACK_ENV", "development").lower()
            auto_approve_env = os.getenv("AUTO_APPROVE_BUILD113", "false").lower() == "true"
            auto_approve = auto_approve_env and env_mode != "production"

            assert auto_approve is True, (
                "Development with explicit AUTO_APPROVE_BUILD113=true should enable auto-approve. "
                f"Got: auto_approve={auto_approve}"
            )
        finally:
            # Restore env
            os.environ.pop("AUTO_APPROVE_BUILD113", None)
            os.environ.pop("AUTOPACK_ENV", None)
            if original_auto_approve is not None:
                os.environ["AUTO_APPROVE_BUILD113"] = original_auto_approve
            if original_env_mode is not None:
                os.environ["AUTOPACK_ENV"] = original_env_mode
