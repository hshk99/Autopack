"""Test IMP-COST-006: Size limits for project rules in auditor prompts.

This test verifies that:
1. Individual rules exceeding MAX_RULE_CHARS are truncated
2. Total rules respect MAX_TOTAL_RULES_TOKENS limit
3. Truncation is logged appropriately
"""

import logging
from unittest.mock import patch

import pytest

from autopack.anthropic_clients import (
    MAX_RULE_CHARS,
    MAX_TOTAL_RULES_TOKENS,
    AnthropicBuilderClient,
)


class TestProjectRulesSizeLimits:
    """Test project rules size limiting in auditor prompts."""

    @pytest.fixture
    def mock_client(self):
        """Create AnthropicBuilderClient with mocked dependencies."""
        with patch("autopack.anthropic_clients.AnthropicTransport"):
            with patch("autopack.anthropic_clients.Anthropic"):
                client = AnthropicBuilderClient(api_key="test-key")
                return client

    def test_constants_have_reasonable_values(self):
        """Verify the constants are set to expected values."""
        assert MAX_RULE_CHARS == 500
        assert MAX_TOTAL_RULES_TOKENS == 2000

    def test_short_rules_are_not_truncated(self, mock_client):
        """Rules under MAX_RULE_CHARS should pass through unchanged."""
        project_rules = [
            {"rule_text": "Short rule 1"},
            {"rule_text": "Short rule 2"},
        ]
        phase_spec = {"task_category": "test", "description": "test"}

        prompt = mock_client._build_user_prompt(
            patch_content="diff",
            phase_spec=phase_spec,
            file_context=None,
            project_rules=project_rules,
        )

        assert "Short rule 1" in prompt
        assert "Short rule 2" in prompt
        # No truncation marker
        assert "..." not in prompt or prompt.count("...") == 0

    def test_long_rule_is_truncated(self, mock_client, caplog):
        """Rules exceeding MAX_RULE_CHARS should be truncated with '...'."""
        long_rule = "A" * (MAX_RULE_CHARS + 100)  # 600 chars
        project_rules = [{"rule_text": long_rule}]
        phase_spec = {"task_category": "test", "description": "test"}

        with caplog.at_level(logging.INFO):
            prompt = mock_client._build_user_prompt(
                patch_content="diff",
                phase_spec=phase_spec,
                file_context=None,
                project_rules=project_rules,
            )

        # Rule should be truncated
        assert "A" * MAX_RULE_CHARS in prompt
        assert "..." in prompt
        # Full long rule should not be present
        assert long_rule not in prompt

        # Truncation should be logged
        assert any("individual rules truncated" in record.message for record in caplog.records)

    def test_total_rules_respects_token_limit(self, mock_client, caplog):
        """Total rules should stop when token limit is exceeded."""
        # Each rule is ~100 chars, so ~25 tokens each
        # MAX_TOTAL_RULES_TOKENS = 2000, which is ~8000 chars
        # Create 100 rules of 100 chars each = 10000 chars (should exceed limit)
        project_rules = [{"rule_text": f"Rule {i}: " + "X" * 90} for i in range(100)]
        phase_spec = {"task_category": "test", "description": "test"}

        with caplog.at_level(logging.INFO):
            prompt = mock_client._build_user_prompt(
                patch_content="diff",
                phase_spec=phase_spec,
                file_context=None,
                project_rules=project_rules,
            )

        # Should not have all 100 rules
        rule_count = prompt.count("Rule ")
        assert rule_count < 100, f"Expected fewer than 100 rules, got {rule_count}"

        # Should have logged the truncation
        assert any(
            "rules skipped" in record.message for record in caplog.records
        ), "Expected truncation log message"

    def test_empty_rules_are_skipped(self, mock_client):
        """Rules with empty or missing rule_text should be skipped."""
        project_rules = [
            {"rule_text": "Valid rule"},
            {"rule_text": ""},  # Empty
            {},  # Missing rule_text
            {"rule_text": "Another valid rule"},
        ]
        phase_spec = {"task_category": "test", "description": "test"}

        prompt = mock_client._build_user_prompt(
            patch_content="diff",
            phase_spec=phase_spec,
            file_context=None,
            project_rules=project_rules,
        )

        assert "Valid rule" in prompt
        assert "Another valid rule" in prompt
        # Only 2 valid rules should be in the prompt
        rule_lines = [line for line in prompt.split("\n") if line.startswith("- ")]
        valid_rule_lines = [
            line for line in rule_lines if "Valid rule" in line or "Another valid" in line
        ]
        assert len(valid_rule_lines) == 2

    def test_no_rules_produces_no_rules_section(self, mock_client):
        """Empty project_rules should not produce rules section."""
        phase_spec = {"task_category": "test", "description": "test"}

        prompt = mock_client._build_user_prompt(
            patch_content="diff",
            phase_spec=phase_spec,
            file_context=None,
            project_rules=[],
        )

        assert "Project Rules" not in prompt

    def test_none_rules_produces_no_rules_section(self, mock_client):
        """None project_rules should not produce rules section."""
        phase_spec = {"task_category": "test", "description": "test"}

        prompt = mock_client._build_user_prompt(
            patch_content="diff",
            phase_spec=phase_spec,
            file_context=None,
            project_rules=None,
        )

        assert "Project Rules" not in prompt

    def test_exact_boundary_rule_not_truncated(self, mock_client):
        """Rule exactly at MAX_RULE_CHARS should not be truncated."""
        exact_rule = "B" * MAX_RULE_CHARS  # Exactly 500 chars
        project_rules = [{"rule_text": exact_rule}]
        phase_spec = {"task_category": "test", "description": "test"}

        prompt = mock_client._build_user_prompt(
            patch_content="diff",
            phase_spec=phase_spec,
            file_context=None,
            project_rules=project_rules,
        )

        # Full rule should be present without truncation
        assert exact_rule in prompt
        # No truncation marker from this rule
        lines_with_b = [line for line in prompt.split("\n") if "BBB" in line]
        assert all("..." not in line for line in lines_with_b)

    def test_one_char_over_boundary_is_truncated(self, mock_client):
        """Rule one char over MAX_RULE_CHARS should be truncated."""
        over_rule = "C" * (MAX_RULE_CHARS + 1)  # 501 chars
        project_rules = [{"rule_text": over_rule}]
        phase_spec = {"task_category": "test", "description": "test"}

        prompt = mock_client._build_user_prompt(
            patch_content="diff",
            phase_spec=phase_spec,
            file_context=None,
            project_rules=project_rules,
        )

        # Should be truncated
        assert "C" * MAX_RULE_CHARS + "..." in prompt
        # Full rule should not be present
        assert over_rule not in prompt
