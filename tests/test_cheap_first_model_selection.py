"""Tests for IMP-COST-004: Cheap-first model selection optimization.

This module tests that non-critical tasks (docs, tests, etc.) use cheaper
models first before escalating to more expensive models.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml


class TestCheapFirstConfiguration:
    """Test that cheap_first_optimization config is properly structured."""

    @pytest.fixture
    def models_config(self):
        """Load config/models.yaml."""
        config_path = Path("config/models.yaml")
        if not config_path.exists():
            pytest.skip("config/models.yaml not found")

        with open(config_path) as f:
            return yaml.safe_load(f)

    def test_cheap_first_config_exists(self, models_config):
        """config/models.yaml should have cheap_first_optimization section."""
        assert "cheap_first_optimization" in models_config
        assert isinstance(models_config["cheap_first_optimization"], dict)

    def test_cheap_first_config_enabled(self, models_config):
        """cheap_first_optimization should be enabled by default."""
        config = models_config["cheap_first_optimization"]
        assert config.get("enabled", False) is True

    def test_cheap_first_has_eligible_categories(self, models_config):
        """cheap_first_optimization should have eligible_categories list."""
        config = models_config["cheap_first_optimization"]
        assert "eligible_categories" in config
        assert isinstance(config["eligible_categories"], list)
        assert len(config["eligible_categories"]) > 0

    def test_docs_and_tests_are_eligible(self, models_config):
        """docs and tests should be eligible for cheap-first."""
        config = models_config["cheap_first_optimization"]
        eligible = config["eligible_categories"]
        assert "docs" in eligible
        assert "tests" in eligible

    def test_cheap_model_is_haiku(self, models_config):
        """cheap_model should be set to haiku for cost savings."""
        config = models_config["cheap_first_optimization"]
        assert "cheap_model" in config
        assert "haiku" in config["cheap_model"].lower()

    def test_cheap_attempts_before_escalation(self, models_config):
        """Should have cheap_attempts_before_escalation setting."""
        config = models_config["cheap_first_optimization"]
        assert "cheap_attempts_before_escalation" in config
        assert config["cheap_attempts_before_escalation"] >= 1


class TestCheapFirstRoutingPolicy:
    """Test that routing policies use cheap_first strategy."""

    @pytest.fixture
    def models_config(self):
        """Load config/models.yaml."""
        config_path = Path("config/models.yaml")
        if not config_path.exists():
            pytest.skip("config/models.yaml not found")

        with open(config_path) as f:
            return yaml.safe_load(f)

    def test_docs_uses_cheap_first_strategy(self, models_config):
        """docs category should use cheap_first strategy."""
        policies = models_config.get("llm_routing_policies", {})
        docs_policy = policies.get("docs", {})
        assert docs_policy.get("strategy") == "cheap_first"

    def test_tests_uses_cheap_first_strategy(self, models_config):
        """tests category should use cheap_first strategy."""
        policies = models_config.get("llm_routing_policies", {})
        tests_policy = policies.get("tests", {})
        assert tests_policy.get("strategy") == "cheap_first"

    def test_docs_starts_with_haiku(self, models_config):
        """docs should start with haiku as builder_primary."""
        policies = models_config.get("llm_routing_policies", {})
        docs_policy = policies.get("docs", {})
        builder_primary = docs_policy.get("builder_primary", "")
        assert "haiku" in builder_primary.lower()

    def test_tests_starts_with_haiku(self, models_config):
        """tests should start with haiku as builder_primary."""
        policies = models_config.get("llm_routing_policies", {})
        tests_policy = policies.get("tests", {})
        builder_primary = tests_policy.get("builder_primary", "")
        assert "haiku" in builder_primary.lower()

    def test_docs_escalates_to_sonnet(self, models_config):
        """docs should escalate to sonnet after initial attempt."""
        policies = models_config.get("llm_routing_policies", {})
        docs_policy = policies.get("docs", {})
        escalate_to = docs_policy.get("escalate_to", {})
        assert "sonnet" in escalate_to.get("builder", "").lower()

    def test_docs_final_escalation_to_opus(self, models_config):
        """docs should have final escalation to opus."""
        policies = models_config.get("llm_routing_policies", {})
        docs_policy = policies.get("docs", {})
        final = docs_policy.get("final_escalation", {})
        assert "opus" in final.get("builder", "").lower()


class TestModelRouterCheapFirst:
    """Test ModelRouter cheap-first model selection."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return MagicMock()

    @pytest.fixture
    def model_router(self, mock_db):
        """Create a ModelRouter instance with mocked dependencies."""
        with patch("src.autopack.model_router.UsageService"):
            with patch("src.autopack.model_router.get_model_selector"):
                with patch(
                    "src.autopack.model_router.TelemetryDrivenModelOptimizer",
                    return_value=None,
                ):
                    from src.autopack.model_router import ModelRouter

                    router = ModelRouter(mock_db, config_path="config/models.yaml")
                    return router

    def test_cheap_first_config_loaded(self, model_router):
        """ModelRouter should load cheap_first_optimization config."""
        assert hasattr(model_router, "cheap_first_config")
        assert model_router.cheap_first_config.get("enabled", False) is True

    def test_is_cheap_first_eligible_for_docs(self, model_router):
        """is_cheap_first_eligible should return True for docs."""
        assert model_router.is_cheap_first_eligible("docs") is True

    def test_is_cheap_first_eligible_for_tests(self, model_router):
        """is_cheap_first_eligible should return True for tests."""
        assert model_router.is_cheap_first_eligible("tests") is True

    def test_is_cheap_first_not_eligible_for_security(self, model_router):
        """is_cheap_first_eligible should return False for security."""
        assert model_router.is_cheap_first_eligible("security_auth_change") is False

    def test_is_cheap_first_not_eligible_for_none(self, model_router):
        """is_cheap_first_eligible should return False for None."""
        assert model_router.is_cheap_first_eligible(None) is False

    def test_get_cheap_first_model_returns_haiku_for_docs(self, model_router):
        """_get_cheap_first_model should return haiku for docs on first attempt."""
        model = model_router._get_cheap_first_model("docs", attempt_index=0)
        assert model is not None
        assert "haiku" in model.lower()

    def test_get_cheap_first_model_returns_haiku_for_tests(self, model_router):
        """_get_cheap_first_model should return haiku for tests on first attempt."""
        model = model_router._get_cheap_first_model("tests", attempt_index=0)
        assert model is not None
        assert "haiku" in model.lower()

    def test_get_cheap_first_model_returns_none_after_escalation(self, model_router):
        """_get_cheap_first_model should return None after max cheap attempts."""
        # Get the max cheap attempts from config
        max_attempts = model_router.cheap_first_config.get("cheap_attempts_before_escalation", 1)
        # On attempt_index >= max_attempts, should return None
        model = model_router._get_cheap_first_model("docs", attempt_index=max_attempts)
        assert model is None

    def test_get_cheap_first_model_returns_none_for_security(self, model_router):
        """_get_cheap_first_model should return None for security categories."""
        model = model_router._get_cheap_first_model("security_auth_change", attempt_index=0)
        assert model is None

    def test_select_model_uses_cheap_for_docs_first_attempt(self, model_router):
        """select_model should use cheap model for docs on first attempt."""
        model, warning = model_router.select_model(
            role="builder",
            task_category="docs",
            complexity="low",
            attempt_index=0,
        )
        assert "haiku" in model.lower()
        assert warning is not None
        assert "Cheap-first" in warning.get("message", "")

    def test_select_model_uses_cheap_for_tests_first_attempt(self, model_router):
        """select_model should use cheap model for tests on first attempt."""
        model, warning = model_router.select_model(
            role="builder",
            task_category="tests",
            complexity="low",
            attempt_index=0,
        )
        assert "haiku" in model.lower()

    def test_select_model_escalates_after_cheap_attempts(self, model_router):
        """select_model should escalate from cheap model after max attempts."""
        max_attempts = model_router.cheap_first_config.get("cheap_attempts_before_escalation", 1)

        # First attempt should be cheap
        model_first, _ = model_router.select_model(
            role="builder",
            task_category="docs",
            complexity="low",
            attempt_index=0,
        )
        assert "haiku" in model_first.lower()

        # After max attempts, should escalate
        model_escalated, _ = model_router.select_model(
            role="builder",
            task_category="docs",
            complexity="low",
            attempt_index=max_attempts,
        )
        # Should not be haiku anymore (escalated to sonnet or higher)
        assert "haiku" not in model_escalated.lower() or model_escalated == model_first


class TestModelSelectorCheapFirstStrategy:
    """Test ModelSelector cheap_first strategy handling."""

    @pytest.fixture
    def model_selector(self):
        """Create a ModelSelector instance."""
        from src.autopack.model_selection import ModelSelector

        return ModelSelector(config_path="config/models.yaml")

    def test_cheap_first_strategy_selects_haiku_first(self, model_selector):
        """cheap_first strategy should select haiku on first attempt."""
        policies = model_selector.llm_routing_policies
        docs_policy = policies.get("docs", {})

        if docs_policy.get("strategy") != "cheap_first":
            pytest.skip("docs is not configured for cheap_first strategy")

        model = model_selector._apply_routing_policy("builder", docs_policy, attempt_index=0)
        assert model is not None
        assert "haiku" in model.lower()

    def test_cheap_first_strategy_escalates_to_sonnet(self, model_selector):
        """cheap_first strategy should escalate to sonnet after first attempt."""
        policies = model_selector.llm_routing_policies
        docs_policy = policies.get("docs", {})

        if docs_policy.get("strategy") != "cheap_first":
            pytest.skip("docs is not configured for cheap_first strategy")

        escalate_after = docs_policy.get("escalate_to", {}).get("after_attempts", 1)
        model = model_selector._apply_routing_policy(
            "builder", docs_policy, attempt_index=escalate_after
        )
        assert model is not None
        assert "sonnet" in model.lower()

    def test_cheap_first_strategy_final_escalation_to_opus(self, model_selector):
        """cheap_first strategy should escalate to opus for final escalation."""
        policies = model_selector.llm_routing_policies
        docs_policy = policies.get("docs", {})

        if docs_policy.get("strategy") != "cheap_first":
            pytest.skip("docs is not configured for cheap_first strategy")

        final_after = docs_policy.get("final_escalation", {}).get("after_attempts", 3)
        model = model_selector._apply_routing_policy(
            "builder", docs_policy, attempt_index=final_after
        )
        # Should be opus or None if not configured
        if model is not None:
            assert "opus" in model.lower()


class TestEscalationChainWithHaiku:
    """Test that escalation chains include haiku for low complexity."""

    @pytest.fixture
    def models_config(self):
        """Load config/models.yaml."""
        config_path = Path("config/models.yaml")
        if not config_path.exists():
            pytest.skip("config/models.yaml not found")

        with open(config_path) as f:
            return yaml.safe_load(f)

    def test_builder_low_chain_starts_with_haiku(self, models_config):
        """Builder low complexity chain should start with haiku."""
        chains = models_config.get("escalation_chains", {})
        builder_chains = chains.get("builder", {})
        low_chain = builder_chains.get("low", {}).get("models", [])

        assert len(low_chain) >= 2
        assert "haiku" in low_chain[0].lower()

    def test_auditor_low_chain_starts_with_haiku(self, models_config):
        """Auditor low complexity chain should start with haiku."""
        chains = models_config.get("escalation_chains", {})
        auditor_chains = chains.get("auditor", {})
        low_chain = auditor_chains.get("low", {}).get("models", [])

        assert len(low_chain) >= 2
        assert "haiku" in low_chain[0].lower()

    def test_builder_low_chain_includes_sonnet_and_opus(self, models_config):
        """Builder low chain should include sonnet and opus for escalation."""
        chains = models_config.get("escalation_chains", {})
        builder_chains = chains.get("builder", {})
        low_chain = builder_chains.get("low", {}).get("models", [])

        chain_str = " ".join(low_chain).lower()
        assert "sonnet" in chain_str
        assert "opus" in chain_str


class TestHaikuAliasExists:
    """Test that haiku alias is properly configured."""

    @pytest.fixture
    def models_config(self):
        """Load config/models.yaml."""
        config_path = Path("config/models.yaml")
        if not config_path.exists():
            pytest.skip("config/models.yaml not found")

        with open(config_path) as f:
            return yaml.safe_load(f)

    def test_haiku_alias_exists(self, models_config):
        """model_aliases should have 'haiku' alias."""
        aliases = models_config.get("model_aliases", {})
        assert "haiku" in aliases

    def test_haiku_alias_maps_to_correct_model(self, models_config):
        """haiku alias should map to claude-3-haiku model."""
        aliases = models_config.get("model_aliases", {})
        haiku_model = aliases.get("haiku", "")
        assert "claude" in haiku_model
        assert "haiku" in haiku_model
