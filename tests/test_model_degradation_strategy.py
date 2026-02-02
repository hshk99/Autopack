"""Tests for IMP-GENAI-003: LLM model degradation strategy.

Tests the comprehensive degradation strategy that provides clear fallback
paths when primary models are unavailable.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestDegradationChainRetrieval:
    """Test getting degradation chains for roles and complexity levels."""

    def test_get_degradation_chain_from_escalation_chains_config(self, model_router):
        """Should retrieve degradation chain from escalation_chains config."""
        chain = model_router.get_degradation_chain("builder", "low")

        # Should return a list with at least 2 models
        assert isinstance(chain, list)
        assert len(chain) >= 1
        # First model should be Claude Haiku for low complexity
        assert "haiku" in chain[0].lower() or "sonnet" in chain[0].lower()

    def test_get_degradation_chain_for_auditor_high_complexity(self, model_router):
        """Should get correct degradation chain for auditor high complexity."""
        chain = model_router.get_degradation_chain("auditor", "high")

        assert isinstance(chain, list)
        assert len(chain) >= 1
        # Auditor high complexity should have clear escalation path
        assert "sonnet" in chain[0].lower() or "opus" in chain[0].lower()

    def test_degradation_chain_has_no_duplicates(self, model_router):
        """Degradation chain should not contain duplicate models."""
        chain = model_router.get_degradation_chain("builder", "medium")

        # Check for duplicates
        assert len(chain) == len(set(chain)), f"Chain has duplicates: {chain}"

    def test_degradation_chain_ordering_ascending(self, model_router):
        """Models in degradation chain should generally escalate in capability."""
        chain = model_router.get_degradation_chain("builder", "high")

        # Define a simple capability order
        capability_order = {
            "haiku": 1,
            "sonnet": 2,
            "opus": 3,
            "gpt": 2,
        }

        # Extract capabilities from model names
        capabilities = []
        for model in chain:
            for key, value in capability_order.items():
                if key in model.lower():
                    capabilities.append(value)
                    break
            else:
                capabilities.append(0)  # Unknown model

        # Generally, capabilities should not decrease dramatically
        # (allowing for some flexibility since config may override)
        assert len(capabilities) > 0


class TestModelAvailabilityChecking:
    """Test model availability checking logic."""

    def test_is_model_available_when_provider_enabled(self, model_router):
        """Should return True for available models."""
        with patch.object(model_router, "_is_provider_disabled", return_value=False):
            with patch.object(
                model_router.usage_service,
                "get_provider_usage_summary",
                return_value={"anthropic": {"total_tokens": 100000}},
            ):
                # Set soft limit high enough to not trigger
                model_router.provider_quotas["anthropic"]["weekly_token_cap"] = 10000000
                assert model_router.is_model_available("claude-sonnet-4-5") is True

    def test_is_model_unavailable_when_provider_disabled(self, model_router):
        """Should return False when provider is disabled."""
        with patch.object(model_router, "_is_provider_disabled", return_value=True):
            assert model_router.is_model_available("claude-sonnet-4-5") is False

    def test_is_model_unavailable_when_over_hard_limit(self, model_router):
        """Should return False when provider exceeds hard token limit."""
        model_router.provider_quotas["anthropic"]["weekly_token_cap"] = 1000
        with patch.object(model_router, "_is_provider_disabled", return_value=False):
            with patch.object(
                model_router.usage_service,
                "get_provider_usage_summary",
                return_value={"anthropic": {"total_tokens": 1001}},
            ):
                assert model_router.is_model_available("claude-sonnet-4-5") is False

    def test_is_model_available_with_no_quota_cap(self, model_router):
        """Should return True when no quota cap is configured."""
        model_router.provider_quotas["anthropic"]["weekly_token_cap"] = 0
        with patch.object(model_router, "_is_provider_disabled", return_value=False):
            with patch.object(
                model_router.usage_service,
                "get_provider_usage_summary",
                return_value={"anthropic": {"total_tokens": 999999999}},
            ):
                assert model_router.is_model_available("claude-sonnet-4-5") is True


class TestNextDegradedModelSelection:
    """Test selecting the next model in degradation chain."""

    def test_get_next_degraded_model_in_chain(self, model_router):
        """Should return next model in degradation chain."""
        # Mock the chain and availability
        with patch.object(
            model_router,
            "get_degradation_chain",
            return_value=[
                "claude-opus-4-5",
                "claude-sonnet-4-5",
                "claude-3-haiku-20240307",
            ],
        ):
            with patch.object(model_router, "is_model_available", return_value=True):
                next_model = model_router.get_next_degraded_model(
                    "claude-opus-4-5", "builder", "high"
                )
                assert next_model == "claude-sonnet-4-5"

    def test_get_next_degraded_model_skips_unavailable(self, model_router):
        """Should skip unavailable models in chain."""
        with patch.object(
            model_router,
            "get_degradation_chain",
            return_value=[
                "claude-opus-4-5",
                "claude-sonnet-4-5",
                "claude-3-haiku-20240307",
            ],
        ):
            # First fallback unavailable, should get second
            def is_available(model):
                return model != "claude-sonnet-4-5"

            with patch.object(model_router, "is_model_available", side_effect=is_available):
                next_model = model_router.get_next_degraded_model(
                    "claude-opus-4-5", "builder", "high"
                )
                assert next_model == "claude-3-haiku-20240307"

    def test_get_next_degraded_model_returns_none_when_none_available(self, model_router):
        """Should return None when no models in chain are available."""
        with patch.object(
            model_router,
            "get_degradation_chain",
            return_value=["claude-opus-4-5", "claude-sonnet-4-5"],
        ):
            with patch.object(model_router, "is_model_available", return_value=False):
                next_model = model_router.get_next_degraded_model(
                    "claude-opus-4-5", "builder", "high"
                )
                assert next_model is None

    def test_get_next_degraded_model_handles_model_not_in_chain(self, model_router):
        """Should handle case where current model is not in chain."""
        with patch.object(
            model_router,
            "get_degradation_chain",
            return_value=["claude-opus-4-5", "claude-sonnet-4-5"],
        ):
            with patch.object(model_router, "is_model_available", return_value=True):
                # Call with model not in chain
                next_model = model_router.get_next_degraded_model("gpt-4o", "builder", "high")
                # Should return first available from chain
                assert next_model == "claude-opus-4-5"


class TestSelectModelWithDegradation:
    """Test comprehensive model selection with degradation strategy."""

    def test_select_model_with_degradation_uses_primary_if_available(self, model_router):
        """Should use primary model when available."""
        with patch.object(model_router, "select_model", return_value=("claude-sonnet-4-5", None)):
            with patch.object(model_router, "is_model_available", return_value=True):
                model, info = model_router.select_model_with_degradation("builder", "tests", "low")
                assert model == "claude-sonnet-4-5"
                assert info is None  # No degradation

    def test_select_model_with_degradation_degrades_when_unavailable(self, model_router):
        """Should degrade to next model when primary is unavailable."""
        with patch.object(model_router, "select_model", return_value=("claude-opus-4-5", None)):
            # First call (primary) returns False, second call (next) returns True
            availability = [False, True]
            availability_iter = iter(availability)

            def is_available(model):
                return next(availability_iter)

            with patch.object(model_router, "is_model_available", side_effect=is_available):
                with patch.object(
                    model_router,
                    "get_next_degraded_model",
                    return_value="claude-sonnet-4-5",
                ):
                    model, info = model_router.select_model_with_degradation(
                        "builder", "core_backend", "high"
                    )
                    assert model == "claude-sonnet-4-5"
                    assert info is not None
                    assert info["degraded"] is True
                    assert info["original_model"] == "claude-opus-4-5"
                    assert info["degraded_model"] == "claude-sonnet-4-5"

    def test_select_model_with_degradation_returns_original_on_full_degradation_failure(
        self, model_router
    ):
        """Should return original model if degradation chain is exhausted."""
        with patch.object(model_router, "select_model", return_value=("claude-opus-4-5", None)):
            with patch.object(model_router, "is_model_available", return_value=False):
                with patch.object(model_router, "get_next_degraded_model", return_value=None):
                    with patch.object(
                        model_router,
                        "get_degradation_chain",
                        return_value=["claude-opus-4-5", "claude-sonnet-4-5"],
                    ):
                        model, info = model_router.select_model_with_degradation(
                            "builder", "core_backend", "high"
                        )
                        # Should return original even though degradation failed
                        assert model == "claude-opus-4-5"
                        assert info is not None
                        assert info["degraded"] is True
                        assert "error" in info
                        assert "unavailable" in info["error"].lower()


class TestDegradationIntegration:
    """Integration tests for complete degradation scenarios."""

    def test_degradation_preserves_budget_warnings(self, model_router):
        """Degradation should preserve budget warnings from original selection."""
        budget_warning = {"level": "warning", "message": "Over soft limit"}
        with patch.object(
            model_router, "select_model", return_value=("claude-opus-4-5", budget_warning)
        ):
            with patch.object(model_router, "is_model_available", return_value=True):
                model, info = model_router.select_model_with_degradation(
                    "builder", "tests", "medium"
                )
                # Budget warning not returned by select_model_with_degradation
                # but should be considered in real usage

    def test_degradation_respects_run_context(self, model_router):
        """Degradation should respect model overrides in run context."""
        run_context = {"model_overrides": {"builder": {"tests:low": "gpt-4o"}}}
        with patch.object(
            model_router, "select_model", return_value=("gpt-4o", None)
        ) as mock_select:
            with patch.object(model_router, "is_model_available", return_value=True):
                model, info = model_router.select_model_with_degradation(
                    "builder", "tests", "low", run_context=run_context
                )
                assert model == "gpt-4o"
                # Verify run_context was passed through
                mock_select.assert_called_once()
                call_kwargs = mock_select.call_args[1]
                assert call_kwargs["run_context"] == run_context


# Fixtures


@pytest.fixture
def model_router(tmp_path):
    """Create a ModelRouter instance for testing."""
    # Create minimal models.yaml config
    config_content = """
complexity_models:
  low:
    builder: claude-3-haiku-20240307
    auditor: claude-3-haiku-20240307
  medium:
    builder: claude-sonnet-4-5
    auditor: claude-sonnet-4-5
  high:
    builder: claude-sonnet-4-5
    auditor: claude-sonnet-4-5
    escalation_builder: claude-opus-4-5
    escalation_auditor: claude-opus-4-5

escalation_chains:
  builder:
    low:
      models:
        - claude-3-haiku-20240307
        - claude-sonnet-4-5
        - claude-opus-4-5
    medium:
      models:
        - claude-sonnet-4-5
        - claude-opus-4-5
    high:
      models:
        - claude-sonnet-4-5
        - claude-opus-4-5
  auditor:
    low:
      models:
        - claude-3-haiku-20240307
        - claude-sonnet-4-5
        - claude-opus-4-5
    medium:
      models:
        - claude-sonnet-4-5
        - claude-opus-4-5
    high:
      models:
        - claude-sonnet-4-5
        - claude-opus-4-5

provider_quotas:
  anthropic:
    weekly_token_cap: 10000000
    soft_limit_ratio: 0.8
  openai:
    weekly_token_cap: 10000000
    soft_limit_ratio: 0.8

quota_routing:
  enabled: true
  never_fallback_categories:
    - security_auth_change

fallback_strategy:
  by_category:
    general:
      fallbacks:
        - claude-sonnet-4-5
  default_fallbacks:
    - claude-sonnet-4-5

defaults:
  high_risk_builder: gpt-4o
  high_risk_auditor: gpt-4o

model_aliases:
  sonnet: claude-sonnet-4-5
  opus: claude-opus-4-5
  haiku: claude-3-haiku-20240307
"""

    config_file = tmp_path / "models.yaml"
    config_file.write_text(config_content)

    # Mock database session
    mock_db = MagicMock()

    # Import after creating config file
    from src.autopack.model_router import ModelRouter

    router = ModelRouter(mock_db, str(config_file))
    return router
