"""Tests for IMP-COST-002: Pre-call token budget validation

Tests that verify the LlmService correctly checks token budget before
making LLM calls and returns appropriate error results when budget is exceeded.
"""

import pytest
from unittest.mock import MagicMock, patch

from autopack.llm_service import LlmService, estimate_tokens


class TestEstimateTokens:
    """Tests for the estimate_tokens helper function"""

    def test_estimate_tokens_basic(self):
        """Test basic token estimation (4 chars per token)"""
        text = "Hello world"  # 11 chars
        result = estimate_tokens(text)
        assert result == 2  # 11 / 4 = 2.75, int = 2

    def test_estimate_tokens_empty_string(self):
        """Test estimation returns minimum of 1 for empty string"""
        result = estimate_tokens("")
        assert result == 1  # minimum is 1

    def test_estimate_tokens_long_text(self):
        """Test estimation for longer text"""
        text = "a" * 1000  # 1000 chars
        result = estimate_tokens(text)
        assert result == 250  # 1000 / 4 = 250

    def test_estimate_tokens_custom_ratio(self):
        """Test estimation with custom chars_per_token ratio"""
        text = "Hello world"  # 11 chars
        result = estimate_tokens(text, chars_per_token=2.0)
        assert result == 5  # 11 / 2 = 5.5, int = 5


class TestCheckPreCallBudget:
    """Tests for the _check_pre_call_budget method"""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session"""
        return MagicMock()

    @pytest.fixture
    def llm_service(self, mock_db_session, tmp_path):
        """Create an LlmService instance with mocked dependencies"""
        # Mock the ModelRouter to avoid needing real config
        with patch("autopack.llm_service.ModelRouter"):
            with patch("autopack.llm_service.QualityGate"):
                # Create service without any real providers
                service = LlmService(
                    db=mock_db_session,
                    config_path=str(tmp_path / "models.yaml"),
                    repo_root=tmp_path,
                )
                return service

    def test_within_budget_returns_true(self, llm_service):
        """Test that calls within budget are approved"""
        result = llm_service._check_pre_call_budget(
            phase_spec={"task": "test"},
            file_context={"file.py": "code"},
            project_rules=["rule1"],
            run_hints=["hint1"],
            retrieved_context="some context",
            run_token_budget=100_000,
            tokens_used_so_far=10_000,
            max_output_tokens=4000,
        )

        assert result["within_budget"] is True
        assert result["estimated_input_tokens"] > 0
        assert result["estimated_output_tokens"] == 4000
        assert result["budget_remaining"] == 90_000

    def test_exceeds_budget_returns_false(self, llm_service):
        """Test that calls exceeding budget are rejected"""
        # Create a large phase spec that would exceed remaining budget
        large_context = {"files": {"large.py": "x" * 100_000}}  # ~25k tokens

        result = llm_service._check_pre_call_budget(
            phase_spec={"task": "test"},
            file_context=large_context,
            project_rules=None,
            run_hints=None,
            retrieved_context=None,
            run_token_budget=50_000,
            tokens_used_so_far=45_000,
            max_output_tokens=4000,
        )

        assert result["within_budget"] is False
        assert "exceeds" in result["reason"].lower()
        assert result["budget_remaining"] == 5_000

    def test_uses_90_percent_threshold(self, llm_service):
        """Test that a 90% buffer is applied to budget check"""
        # With 10k budget remaining, effective budget is 9k (90%)
        # Create an input that totals just over the 90% threshold
        # Budget remaining: 10k, effective: 9k
        # Need total > 9k to be rejected
        # So need: input_tokens + output_tokens > 9000
        # With output=4000, need input > 5000
        # Input = file_context tokens + phase_spec tokens + 500 overhead
        # Need file_context of ~20k chars to get ~5k tokens
        result = llm_service._check_pre_call_budget(
            phase_spec={"task": "test"},
            file_context={"file.py": "x" * 20_000},  # ~5k tokens
            project_rules=None,
            run_hints=None,
            retrieved_context=None,
            run_token_budget=100_000,
            tokens_used_so_far=90_000,
            max_output_tokens=4000,  # ~5k + 4k + overhead = ~9.5k total
        )

        # ~9.5k > 9k effective budget, should be rejected
        assert result["within_budget"] is False

    def test_handles_none_inputs_gracefully(self, llm_service):
        """Test that None inputs are handled without errors"""
        result = llm_service._check_pre_call_budget(
            phase_spec={},
            file_context=None,
            project_rules=None,
            run_hints=None,
            retrieved_context=None,
            run_token_budget=100_000,
            tokens_used_so_far=0,
            max_output_tokens=None,  # Should default to 4000
        )

        assert result["within_budget"] is True
        assert result["estimated_output_tokens"] == 4000
        # Minimum is phase spec (empty dict ~2 chars) + 500 overhead
        assert result["estimated_input_tokens"] >= 500

    def test_includes_system_prompt_overhead(self, llm_service):
        """Test that ~500 token overhead is added for system prompts"""
        result = llm_service._check_pre_call_budget(
            phase_spec={"task": "test"},  # ~15 chars = 3 tokens
            file_context=None,
            project_rules=None,
            run_hints=None,
            retrieved_context=None,
            run_token_budget=100_000,
            tokens_used_so_far=0,
            max_output_tokens=4000,
        )

        # Should include 500 overhead
        assert result["estimated_input_tokens"] >= 500


class TestExecuteBuilderPhaseWithBudget:
    """Tests for execute_builder_phase budget validation integration"""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session"""
        return MagicMock()

    @pytest.fixture
    def llm_service(self, mock_db_session, tmp_path):
        """Create an LlmService instance with mocked dependencies"""
        with patch("autopack.llm_service.ModelRouter") as mock_router:
            with patch("autopack.llm_service.QualityGate"):
                mock_router_instance = MagicMock()
                mock_router_instance.select_model_with_escalation.return_value = (
                    "claude-3-5-sonnet-20241022",
                    "medium",
                    {},
                )
                mock_router.return_value = mock_router_instance

                service = LlmService(
                    db=mock_db_session,
                    config_path=str(tmp_path / "models.yaml"),
                    repo_root=tmp_path,
                )
                return service

    def test_skips_budget_check_when_params_not_provided(self, llm_service):
        """Test that budget check is skipped when budget params are None"""
        with patch.object(llm_service, "_check_pre_call_budget") as mock_check:
            with patch.object(llm_service, "_resolve_client_and_model") as mock_resolve:
                mock_client = MagicMock()
                mock_client.execute_phase.return_value = MagicMock(
                    success=True,
                    tokens_used=100,
                    prompt_tokens=50,
                    completion_tokens=50,
                )
                mock_resolve.return_value = (mock_client, "claude-3-5-sonnet-20241022")

                # Call without budget params
                llm_service.execute_builder_phase(
                    phase_spec={"task": "test"},
                    run_token_budget=None,  # No budget provided
                    tokens_used_so_far=None,
                )

                # Budget check should NOT be called
                mock_check.assert_not_called()
                # But LLM call should proceed
                mock_client.execute_phase.assert_called_once()

    def test_returns_error_when_budget_exceeded(self, llm_service):
        """Test that a failed BuilderResult is returned when budget exceeded"""
        with patch.object(llm_service, "_check_pre_call_budget") as mock_check:
            # Simulate budget exceeded
            mock_check.return_value = {
                "within_budget": False,
                "estimated_input_tokens": 10_000,
                "estimated_output_tokens": 4_000,
                "budget_remaining": 5_000,
                "reason": "Estimated call exceeds budget",
            }

            result = llm_service.execute_builder_phase(
                phase_spec={"task": "test"},
                run_token_budget=100_000,
                tokens_used_so_far=95_000,
            )

            assert result.success is False
            assert "budget_exceeded" in result.error
            assert result.tokens_used == 0
            assert result.model_used == "none"

    def test_proceeds_when_within_budget(self, llm_service):
        """Test that LLM call proceeds when within budget"""
        with patch.object(llm_service, "_check_pre_call_budget") as mock_check:
            with patch.object(llm_service, "_resolve_client_and_model") as mock_resolve:
                mock_check.return_value = {
                    "within_budget": True,
                    "estimated_input_tokens": 1_000,
                    "estimated_output_tokens": 4_000,
                    "budget_remaining": 90_000,
                    "reason": "Within budget",
                }

                mock_client = MagicMock()
                mock_client.execute_phase.return_value = MagicMock(
                    success=True,
                    patch_content="diff --git",
                    builder_messages=[],
                    tokens_used=5_000,
                    model_used="claude-3-5-sonnet-20241022",
                    prompt_tokens=1_000,
                    completion_tokens=4_000,
                )
                mock_resolve.return_value = (mock_client, "claude-3-5-sonnet-20241022")

                result = llm_service.execute_builder_phase(
                    phase_spec={"task": "test"},
                    run_token_budget=100_000,
                    tokens_used_so_far=10_000,
                )

                # Budget check was called
                mock_check.assert_called_once()
                # LLM call proceeded
                mock_client.execute_phase.assert_called_once()
                assert result.success is True
