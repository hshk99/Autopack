"""Tests for IMP-COST-001 dual audit configuration options.

Tests verify:
1. dual_audit_enabled flag disables dual audit when False
2. dual_audit_secondary_model uses cheaper secondary model when set
3. Backward compatibility: default behavior unchanged (dual audit enabled)
"""

import os
from unittest.mock import MagicMock, Mock, patch

import pytest
from sqlalchemy.orm import Session

from autopack.config import Settings
from autopack.llm_service import LlmService


class TestDualAuditConfig:
    """Test dual audit configuration options (IMP-COST-001)."""

    def test_dual_audit_enabled_default_true(self):
        """Verify dual_audit_enabled defaults to True (backward compatible)."""
        settings = Settings()
        assert settings.dual_audit_enabled is True
        print("✓ dual_audit_enabled defaults to True (backward compatible)")

    def test_dual_audit_enabled_can_be_disabled(self):
        """Verify dual_audit_enabled can be set to False via env var."""
        with patch.dict(os.environ, {"AUTOPACK_DUAL_AUDIT_ENABLED": "false"}):
            settings = Settings()
            assert settings.dual_audit_enabled is False
            print("✓ dual_audit_enabled can be disabled via env var")

    def test_dual_audit_secondary_model_default_none(self):
        """Verify dual_audit_secondary_model defaults to None."""
        settings = Settings()
        assert settings.dual_audit_secondary_model is None
        print("✓ dual_audit_secondary_model defaults to None")

    def test_dual_audit_secondary_model_can_be_set(self):
        """Verify dual_audit_secondary_model can be set via env var."""
        with patch.dict(os.environ, {"AUTOPACK_DUAL_AUDIT_SECONDARY_MODEL": "claude-haiku-4-5"}):
            settings = Settings()
            assert settings.dual_audit_secondary_model == "claude-haiku-4-5"
            print("✓ dual_audit_secondary_model can be set via env var")

    @patch("autopack.llm_service.ModelRouter")
    @patch("autopack.config.settings")
    def test_secondary_model_uses_global_config(self, mock_settings: Mock, mock_model_router: Mock):
        """Verify secondary auditor uses global config when set."""
        # Mock settings with global secondary model
        mock_settings.dual_audit_enabled = True
        mock_settings.dual_audit_secondary_model = "claude-haiku-4-5"

        # Mock model router (empty policies)
        mock_router_instance = MagicMock()
        mock_model_router.return_value = mock_router_instance
        mock_router_instance.config = {"llm_routing_policies": {}}

        # Create mock DB session
        mock_db = Mock(spec=Session)

        # Create LLM service
        llm_service = LlmService(db=mock_db, config_path="config/models.yaml")

        # Test _get_secondary_auditor_model
        secondary_model = llm_service._get_secondary_auditor_model("any_category")

        # Verify global config is used
        assert secondary_model == "claude-haiku-4-5"
        print("✓ Secondary auditor uses global dual_audit_secondary_model when configured")

    @patch("autopack.llm_service.ModelRouter")
    @patch("autopack.config.settings")
    def test_secondary_model_fallback_to_category_policy(
        self, mock_settings: Mock, mock_model_router: Mock
    ):
        """Verify secondary auditor falls back to category-specific policy when no global config."""
        # Mock settings (no global secondary model)
        mock_settings.dual_audit_enabled = True
        mock_settings.dual_audit_secondary_model = None

        # Mock model router with category-specific policy
        mock_router_instance = MagicMock()
        mock_model_router.return_value = mock_router_instance
        mock_router_instance.config = {
            "llm_routing_policies": {
                "security_auth_change": {"secondary_auditor": "claude-sonnet-4-5"}
            }
        }

        # Create mock DB session
        mock_db = Mock(spec=Session)

        # Create LLM service
        llm_service = LlmService(db=mock_db, config_path="config/models.yaml")

        # Test _get_secondary_auditor_model
        secondary_model = llm_service._get_secondary_auditor_model("security_auth_change")

        # Verify category-specific policy is used
        assert secondary_model == "claude-sonnet-4-5"
        print("✓ Secondary auditor falls back to category-specific policy")

    @patch("autopack.llm_service.ModelRouter")
    @patch("autopack.config.settings")
    def test_secondary_model_fallback_to_default(
        self, mock_settings: Mock, mock_model_router: Mock
    ):
        """Verify secondary auditor falls back to default when no config available."""
        # Mock settings (no global secondary model)
        mock_settings.dual_audit_enabled = True
        mock_settings.dual_audit_secondary_model = None

        # Mock model router (no category-specific policy)
        mock_router_instance = MagicMock()
        mock_model_router.return_value = mock_router_instance
        mock_router_instance.config = {"llm_routing_policies": {}}

        # Create mock DB session
        mock_db = Mock(spec=Session)

        # Create LLM service
        llm_service = LlmService(db=mock_db, config_path="config/models.yaml")

        # Test _get_secondary_auditor_model
        secondary_model = llm_service._get_secondary_auditor_model("unknown_category")

        # Verify default is used
        assert secondary_model == "claude-sonnet-4-5"
        print("✓ Secondary auditor falls back to default (claude-sonnet-4-5)")


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v"])
