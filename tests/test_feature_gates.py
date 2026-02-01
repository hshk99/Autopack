"""Comprehensive tests for Feature Quarantine/Enablement API (IMP-REL-001).

Tests cover:
- Feature gate enabling/disabling
- Kill switch environment variable handling
- Runtime feature state management
- Dependency checking and validation
- API endpoints for feature management
- Graceful degradation helpers
- Feature state reporting
"""

import os
from unittest.mock import patch

import pytest

from autopack.feature_gates import (
    FeatureDisabledError,
    check_feature_dependencies,
    get_disabled_features,
    get_disabled_graceful,
    get_enabled_features,
    get_feature_info,
    get_feature_states,
    handle_disabled_feature,
    is_feature_enabled,
    log_feature_usage,
    require_feature,
    reset_feature_overrides,
    set_feature_enabled,
    validate_feature_state,
)


class TestFeatureGateBasics:
    """Test basic feature gate functionality."""

    def setup_method(self):
        """Reset feature overrides before each test."""
        reset_feature_overrides()

    def test_feature_disabled_by_default(self):
        """Verify features are disabled by default (OFF by default for safety)."""
        # Most features should be disabled unless explicitly enabled
        with patch.dict(os.environ, {}, clear=True):
            reset_feature_overrides()
            # Check that a research feature is disabled
            assert not is_feature_enabled("research_cycle_triggering")
            assert not is_feature_enabled("sot_artifact_substitution")

    def test_feature_enabled_via_env_var(self):
        """Verify feature can be enabled via environment variable."""
        with patch.dict(os.environ, {"AUTOPACK_ENABLE_RESEARCH_CYCLE_TRIGGERING": "1"}):
            reset_feature_overrides()
            assert is_feature_enabled("research_cycle_triggering")

    def test_feature_requires_exact_value(self):
        """Verify feature only enables with exact value '1'."""
        test_cases = [
            ("true", False),
            ("True", False),
            ("yes", False),
            ("YES", False),
            ("enabled", False),
            ("0", False),
            ("", False),
            ("1", True),
        ]

        for env_value, expected in test_cases:
            with patch.dict(os.environ, {"AUTOPACK_ENABLE_MONETIZATION_GUIDANCE": env_value}):
                reset_feature_overrides()
                assert is_feature_enabled("monetization_guidance") == expected, (
                    f"Feature should be {'enabled' if expected else 'disabled'} "
                    f"when AUTOPACK_ENABLE_MONETIZATION_GUIDANCE={env_value}"
                )

    def test_unknown_feature_returns_false(self):
        """Verify unknown feature returns False instead of raising."""
        assert is_feature_enabled("nonexistent_feature") is False

    def test_get_feature_info(self):
        """Verify get_feature_info returns correct metadata."""
        info = get_feature_info("research_cycle_triggering")
        assert info is not None
        assert info.feature_id == "research_cycle_triggering"
        assert info.name == "Research Cycle Triggering in Autopilot"
        assert info.wave == "wave3"
        assert info.imp_id == "IMP-AUT-001"
        assert info.risk_level == "HIGH"

    def test_get_feature_info_nonexistent(self):
        """Verify get_feature_info returns None for unknown features."""
        assert get_feature_info("nonexistent_feature") is None


class TestRuntimeFeatureToggles:
    """Test runtime feature toggle functionality."""

    def setup_method(self):
        """Reset feature overrides before each test."""
        reset_feature_overrides()

    def test_set_feature_enabled_runtime(self):
        """Verify feature can be enabled at runtime without env var."""
        # Disable env var to start
        with patch.dict(os.environ, {}, clear=True):
            reset_feature_overrides()
            assert not is_feature_enabled("deployment_guidance")

            # Enable at runtime
            set_feature_enabled("deployment_guidance", True)
            assert is_feature_enabled("deployment_guidance")

    def test_set_feature_disabled_runtime(self):
        """Verify feature can be disabled at runtime (kill switch)."""
        # Enable via env var
        with patch.dict(os.environ, {"AUTOPACK_ENABLE_DEPLOYMENT_GUIDANCE": "1"}):
            reset_feature_overrides()
            assert is_feature_enabled("deployment_guidance")

            # Disable at runtime (emergency kill switch)
            set_feature_enabled("deployment_guidance", False)
            assert not is_feature_enabled("deployment_guidance")

    def test_set_unknown_feature_raises_error(self):
        """Verify setting unknown feature raises ValueError."""
        with pytest.raises(ValueError, match="Unknown feature"):
            set_feature_enabled("nonexistent_feature", True)

    def test_runtime_override_persists(self):
        """Verify runtime overrides persist across multiple calls."""
        set_feature_enabled("cicd_pipeline_generator", True)
        assert is_feature_enabled("cicd_pipeline_generator")

        set_feature_enabled("cicd_pipeline_generator", False)
        assert not is_feature_enabled("cicd_pipeline_generator")

        # Re-enable
        set_feature_enabled("cicd_pipeline_generator", True)
        assert is_feature_enabled("cicd_pipeline_generator")

    def test_reset_feature_overrides(self):
        """Verify reset_feature_overrides clears all runtime changes."""
        set_feature_enabled("deployment_guidance", True)
        set_feature_enabled("monetization_guidance", False)

        assert is_feature_enabled("deployment_guidance")
        assert not is_feature_enabled("monetization_guidance")

        # Reset
        reset_feature_overrides()

        # Back to env var defaults
        with patch.dict(os.environ, {}, clear=True):
            reset_feature_overrides()
            assert not is_feature_enabled("deployment_guidance")
            assert not is_feature_enabled("monetization_guidance")


class TestFeatureDependencies:
    """Test feature dependency checking."""

    def setup_method(self):
        """Reset feature overrides before each test."""
        reset_feature_overrides()

    def test_check_dependencies_satisfied(self):
        """Verify check_feature_dependencies works when deps are satisfied."""
        # Enable dependencies first
        set_feature_enabled("research_budget_enforcement", True)
        set_feature_enabled("monetization_guidance", True)

        # Check deps
        satisfied, missing = check_feature_dependencies("monetization_guidance")
        assert satisfied is True
        assert missing == []

    def test_check_dependencies_missing(self):
        """Verify check_feature_dependencies detects missing dependencies."""
        # Don't enable budget enforcement dependency
        reset_feature_overrides()

        # monetization_guidance requires research_budget_enforcement
        satisfied, missing = check_feature_dependencies("monetization_guidance")
        assert satisfied is False
        assert "research_budget_enforcement" in missing

    def test_check_no_dependencies(self):
        """Verify features with no dependencies always have satisfied deps."""
        satisfied, missing = check_feature_dependencies("phase6_metrics")
        assert satisfied is True
        assert missing == []

    def test_transitive_dependencies(self):
        """Verify transitive dependency checking (A requires B which requires C)."""
        # post_build_artifacts requires deployment_guidance and cicd_pipeline_generator
        # cicd_pipeline_generator requires deployment_guidance
        # So enabling post_build_artifacts without deployment_guidance should fail
        reset_feature_overrides()

        satisfied, missing = check_feature_dependencies("post_build_artifacts")
        assert satisfied is False
        assert "deployment_guidance" in missing


class TestFeatureStateQueries:
    """Test feature state query methods."""

    def setup_method(self):
        """Reset feature overrides before each test."""
        reset_feature_overrides()

    def test_get_feature_states(self):
        """Verify get_feature_states returns all features with correct structure."""
        states = get_feature_states()

        # Should have multiple features
        assert len(states) > 10

        # Check structure
        for feature_id, state in states.items():
            assert state["feature_id"] == feature_id
            assert "name" in state
            assert "enabled" in state
            assert isinstance(state["enabled"], bool)
            assert "wave" in state
            assert "imp_id" in state
            assert "risk_level" in state

    def test_get_enabled_features(self):
        """Verify get_enabled_features returns only enabled features."""
        # Enable some features
        set_feature_enabled("phase6_metrics", True)
        set_feature_enabled("consolidated_metrics", True)

        enabled = get_enabled_features()

        # These should be in enabled list
        assert "phase6_metrics" in enabled
        assert "consolidated_metrics" in enabled

    def test_get_disabled_features(self):
        """Verify get_disabled_features returns only disabled features."""
        # Most features are disabled by default
        disabled = get_disabled_features()

        # Should be many disabled features
        assert len(disabled) > 0

        # All should have enabled=False
        for feature_id, state in disabled.items():
            assert state["enabled"] is False

    def test_enabled_disabled_count(self):
        """Verify enabled and disabled counts sum to total."""
        set_feature_enabled("phase6_metrics", True)
        reset_feature_overrides()  # Keep the explicit enable

        enabled = get_enabled_features()
        disabled = get_disabled_features()
        states = get_feature_states()

        assert len(enabled) + len(disabled) == len(states)


class TestRequireFeature:
    """Test require_feature validation."""

    def setup_method(self):
        """Reset feature overrides before each test."""
        reset_feature_overrides()

    def test_require_feature_enabled(self):
        """Verify require_feature passes when feature is enabled."""
        set_feature_enabled("research_cycle_triggering", True)

        # Should not raise
        require_feature("research_cycle_triggering")

    def test_require_feature_disabled_raises(self):
        """Verify require_feature raises FeatureDisabledError when disabled."""
        reset_feature_overrides()

        with pytest.raises(FeatureDisabledError):
            require_feature("research_cycle_triggering")

    def test_require_feature_graceful(self):
        """Verify require_feature with graceful=True doesn't raise."""
        reset_feature_overrides()

        # Should not raise even though feature is disabled
        require_feature("research_cycle_triggering", graceful=True)


class TestDisabledGraceful:
    """Test graceful degradation helper."""

    def setup_method(self):
        """Reset feature overrides before each test."""
        reset_feature_overrides()

    def test_get_disabled_graceful_enabled_feature(self):
        """Verify get_disabled_graceful returns False when feature enabled."""
        set_feature_enabled("sot_artifact_substitution", True)

        assert get_disabled_graceful("sot_artifact_substitution") is False

    def test_get_disabled_graceful_disabled_feature(self):
        """Verify get_disabled_graceful returns True when feature disabled."""
        reset_feature_overrides()

        assert get_disabled_graceful("sot_artifact_substitution") is True

    def test_graceful_conditional_logic(self):
        """Verify graceful degradation in conditional logic."""
        reset_feature_overrides()

        # This is the typical usage pattern
        if get_disabled_graceful("research_cycle_triggering"):
            # Feature disabled, use fallback
            result = "fallback_result"
        else:
            # Feature enabled, use main logic
            result = "main_result"

        assert result == "fallback_result"


class TestHandleDisabledFeature:
    """Test disabled feature response helper."""

    def setup_method(self):
        """Reset feature overrides before each test."""
        reset_feature_overrides()

    def test_handle_disabled_feature_response(self):
        """Verify handle_disabled_feature generates proper response."""
        response = handle_disabled_feature("research_cycle_triggering")

        assert "error" in response
        assert response["feature_id"] == "research_cycle_triggering"
        assert response["status_code"] == 503
        assert "Research Cycle Triggering" in response["feature_name"]
        assert response["details"]["imp_id"] == "IMP-AUT-001"

    def test_handle_disabled_feature_custom_message(self):
        """Verify handle_disabled_feature respects custom message."""
        custom_msg = "Research features temporarily unavailable for maintenance"
        response = handle_disabled_feature("research_cycle_triggering", custom_msg)

        assert response["error"] == custom_msg

    def test_handle_disabled_feature_unknown(self):
        """Verify handle_disabled_feature handles unknown features."""
        response = handle_disabled_feature("nonexistent_feature")

        assert response["status_code"] == 404
        assert "Unknown feature" in response["error"]


class TestFeatureValidation:
    """Test feature state validation."""

    def setup_method(self):
        """Reset feature overrides before each test."""
        reset_feature_overrides()

    def test_validate_feature_state_valid(self):
        """Verify validate_feature_state returns valid when all OK."""
        validation = validate_feature_state()

        assert validation["valid"] is True
        assert len(validation["issues"]) == 0
        assert validation["total_features"] > 0

    def test_validate_feature_state_unmet_deps(self):
        """Verify validate_feature_state detects unmet dependencies."""
        # Enable feature with unmet dependencies
        set_feature_enabled("post_build_artifacts", True)

        validation = validate_feature_state()

        # Should detect unmet dependencies
        assert validation["valid"] is False
        assert any("missing dependencies" in issue for issue in validation["issues"])

    def test_validate_feature_state_counts(self):
        """Verify validation counts are correct."""
        set_feature_enabled("phase6_metrics", True)
        set_feature_enabled("consolidated_metrics", True)

        validation = validate_feature_state()

        assert validation["enabled_count"] >= 2
        assert validation["disabled_count"] >= 0
        assert (
            validation["enabled_count"] + validation["disabled_count"]
            == validation["total_features"]
        )

    def test_validate_invalid_env_var_value(self):
        """Verify validation detects invalid environment variable values."""
        with patch.dict(os.environ, {"AUTOPACK_ENABLE_PHASE6_METRICS": "invalid"}):
            validation = validate_feature_state()

            # Should detect invalid value
            assert validation["valid"] is False
            assert any("invalid value" in issue for issue in validation["issues"])


class TestFeatureRiskLevels:
    """Test feature risk level classification."""

    def test_high_risk_features(self):
        """Verify high-risk features are properly marked."""
        high_risk_features = [
            "research_cycle_triggering",
            "research_budget_enforcement",
        ]

        for feature_id in high_risk_features:
            info = get_feature_info(feature_id)
            assert info is not None
            assert info.risk_level == "HIGH"

    def test_medium_risk_features(self):
        """Verify medium-risk features are properly marked."""
        medium_risk_features = [
            "deployment_guidance",
            "cicd_pipeline_generator",
            "sot_artifact_substitution",
        ]

        for feature_id in medium_risk_features:
            info = get_feature_info(feature_id)
            assert info is not None
            assert info.risk_level == "MEDIUM"

    def test_low_risk_features(self):
        """Verify low-risk features are properly marked."""
        low_risk_features = ["phase6_metrics", "consolidated_metrics"]

        for feature_id in low_risk_features:
            info = get_feature_info(feature_id)
            assert info is not None
            assert info.risk_level == "LOW"


class TestFeatureWaves:
    """Test feature wave classification."""

    def test_wave_1_features(self):
        """Verify Wave 1 features are properly classified."""
        wave1_features = ["research_budget_enforcement", "mcp_registry_scanner"]

        for feature_id in wave1_features:
            info = get_feature_info(feature_id)
            assert info is not None
            assert info.wave == "wave1"

    def test_wave_2_features(self):
        """Verify Wave 2 features are properly classified."""
        wave2_features = ["monetization_guidance", "deployment_guidance"]

        for feature_id in wave2_features:
            info = get_feature_info(feature_id)
            assert info is not None
            assert info.wave == "wave2"

    def test_wave_3_features(self):
        """Verify Wave 3 features are properly classified."""
        wave3_features = ["research_cycle_triggering", "sot_artifact_substitution"]

        for feature_id in wave3_features:
            info = get_feature_info(feature_id)
            assert info is not None
            assert info.wave == "wave3"


class TestLogFeatureUsage:
    """Test feature usage logging."""

    def setup_method(self):
        """Reset feature overrides before each test."""
        reset_feature_overrides()

    def test_log_feature_usage_enabled(self, caplog):
        """Verify log_feature_usage logs correctly for enabled features."""
        import logging

        caplog.set_level(logging.INFO)
        set_feature_enabled("phase6_metrics", True)

        log_feature_usage("phase6_metrics", "started")

        # Check that something was logged with feature name
        assert any("phase6_metrics" in record.message for record in caplog.records)

    def test_log_feature_usage_disabled(self, caplog):
        """Verify log_feature_usage logs correctly for disabled features."""
        import logging

        caplog.set_level(logging.INFO)
        reset_feature_overrides()

        log_feature_usage("research_cycle_triggering", "accessed")

        # Check that something was logged with feature name
        assert any("research_cycle_triggering" in record.message for record in caplog.records)
