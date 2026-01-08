"""Contract tests for feature flags single source of truth (P1-FLAGS-001).

Ensures:
- All AUTOPACK_ENABLE_* flags in code are registered in feature_flags.py
- No mystery flags exist that bypass the registry
- Production posture defaults are safe
"""

import os
import re
import subprocess
from pathlib import Path

import pytest

# Get project root
PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestFeatureFlagRegistry:
    """Tests that feature_flags.py is the single source of truth."""

    def test_registry_module_exists(self):
        """Feature flags registry module must exist."""
        registry_path = PROJECT_ROOT / "src" / "autopack" / "feature_flags.py"
        assert (
            registry_path.exists()
        ), "feature_flags.py must exist at src/autopack/feature_flags.py"

    def test_registry_imports_successfully(self):
        """Feature flags registry must import without errors."""
        from autopack.feature_flags import FEATURE_FLAGS, get_flag, is_enabled

        assert isinstance(FEATURE_FLAGS, dict)
        assert callable(get_flag)
        assert callable(is_enabled)

    def test_all_flags_have_required_fields(self):
        """All registered flags must have required metadata."""
        from autopack.feature_flags import FEATURE_FLAGS, RiskLevel, Scope

        for name, flag in FEATURE_FLAGS.items():
            assert flag.name == name, f"Flag name mismatch: {flag.name} vs {name}"
            assert isinstance(flag.default, bool), f"{name} default must be bool"
            assert flag.description, f"{name} must have description"
            assert isinstance(flag.risk, RiskLevel), f"{name} must have RiskLevel"
            assert isinstance(flag.scope, Scope), f"{name} must have Scope"

    def test_all_flags_start_with_autopack_enable(self):
        """All registered flags must follow naming convention."""
        from autopack.feature_flags import FEATURE_FLAGS

        for name in FEATURE_FLAGS:
            assert name.startswith(
                "AUTOPACK_ENABLE_"
            ), f"Flag {name} must start with AUTOPACK_ENABLE_"


class TestNoMysteryFlags:
    """Tests that all AUTOPACK_ENABLE_* in code are registered."""

    @pytest.fixture
    def flags_in_code(self) -> set[str]:
        """Find all AUTOPACK_ENABLE_* references in Python code."""
        # Use grep to find all occurrences
        result = subprocess.run(
            ["git", "grep", "-h", "-o", "-E", r"AUTOPACK_ENABLE_[A-Z0-9_]+", "--", "*.py"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        # Parse unique flag names
        flags = set()
        for line in result.stdout.strip().split("\n"):
            if line:
                # Clean up any trailing characters
                match = re.match(r"(AUTOPACK_ENABLE_[A-Z0-9_]+)", line)
                if match:
                    flags.add(match.group(1))

        return flags

    @pytest.fixture
    def registered_flags(self) -> set[str]:
        """Get all flags registered in feature_flags.py."""
        from autopack.feature_flags import FEATURE_FLAGS

        return set(FEATURE_FLAGS.keys())

    def test_all_code_flags_are_registered(self, flags_in_code, registered_flags):
        """Every AUTOPACK_ENABLE_* in code must be in the registry."""
        # Exclude flags that appear only in test files checking for unregistered flags
        # and the registry module itself
        unregistered = flags_in_code - registered_flags

        # Filter out test-only flags (flags only used in test assertions)
        # These are intentionally not registered to test the warning behavior
        test_only_flags = {
            "AUTOPACK_ENABLE_UNKNOWN_FLAG",  # Used in tests to verify warning
            "AUTOPACK_ENABLE_NONEXISTENT",  # Used in tests to verify warning
        }
        unregistered = unregistered - test_only_flags

        assert not unregistered, (
            f"Unregistered flags found in code: {unregistered}. "
            "Register them in src/autopack/feature_flags.py"
        )

    def test_no_orphaned_registered_flags(self, flags_in_code, registered_flags):
        """Registered flags should be referenced somewhere in code."""
        # Flags that are only in the registry but never used
        orphaned = registered_flags - flags_in_code

        # Note: We allow orphaned flags for now as they may be:
        # - Planned features not yet implemented
        # - Flags used only via environment variables
        # This test is informational, not blocking
        if orphaned:
            pytest.skip(f"Informational: orphaned flags not used in code: {orphaned}")


class TestProductionPosture:
    """Tests that production defaults are safe."""

    def test_external_risk_flags_default_false(self):
        """Flags with external side effects must default to False."""
        from autopack.feature_flags import FEATURE_FLAGS, RiskLevel

        violations = []
        for name, flag in FEATURE_FLAGS.items():
            if flag.risk == RiskLevel.EXTERNAL and flag.default is True:
                violations.append(name)

        assert not violations, f"EXTERNAL risk flags must default to False: {violations}"

    def test_production_posture_is_conservative(self):
        """Production posture should disable external/API flags."""
        from autopack.feature_flags import get_production_posture, RiskLevel, FEATURE_FLAGS

        posture = get_production_posture()

        for name, recommended in posture.items():
            flag = FEATURE_FLAGS[name]
            if flag.risk == RiskLevel.EXTERNAL:
                assert (
                    recommended is False
                ), f"Production posture for EXTERNAL flag {name} must be False"


class TestIsEnabledBehavior:
    """Tests for is_enabled() function behavior."""

    def test_is_enabled_returns_default_when_no_env(self):
        """is_enabled returns flag default when env var not set."""
        from autopack.feature_flags import is_enabled, FEATURE_FLAGS

        # Pick a flag we know exists
        flag_name = "AUTOPACK_ENABLE_PHASE6_METRICS"
        expected_default = FEATURE_FLAGS[flag_name].default

        # Ensure env var is not set
        original = os.environ.pop(flag_name, None)
        try:
            assert is_enabled(flag_name) == expected_default
        finally:
            if original is not None:
                os.environ[flag_name] = original

    def test_is_enabled_respects_env_true(self):
        """is_enabled returns True when env var is 'true'."""
        from autopack.feature_flags import is_enabled

        flag_name = "AUTOPACK_ENABLE_PHASE6_METRICS"
        original = os.environ.get(flag_name)
        try:
            for true_value in ("true", "1", "yes", "TRUE", "Yes"):
                os.environ[flag_name] = true_value
                assert is_enabled(flag_name) is True, f"Failed for {true_value}"
        finally:
            if original is not None:
                os.environ[flag_name] = original
            else:
                os.environ.pop(flag_name, None)

    def test_is_enabled_respects_env_false(self):
        """is_enabled returns False when env var is 'false'."""
        from autopack.feature_flags import is_enabled

        flag_name = "AUTOPACK_ENABLE_PHASE6_METRICS"
        original = os.environ.get(flag_name)
        try:
            for false_value in ("false", "0", "no", "FALSE", "No"):
                os.environ[flag_name] = false_value
                assert is_enabled(flag_name) is False, f"Failed for {false_value}"
        finally:
            if original is not None:
                os.environ[flag_name] = original
            else:
                os.environ.pop(flag_name, None)

    def test_is_enabled_warns_for_unregistered_flag(self, caplog):
        """is_enabled logs warning for unregistered flags."""
        from autopack.feature_flags import is_enabled
        import logging

        caplog.set_level(logging.WARNING)
        result = is_enabled("AUTOPACK_ENABLE_NONEXISTENT")

        assert result is False
        assert "Unknown feature flag" in caplog.text
        assert "AUTOPACK_ENABLE_NONEXISTENT" in caplog.text
