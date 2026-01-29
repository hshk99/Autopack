"""Test AnthropicAuditorClientWrapper behavior for IMP-FEAT-005.

This test verifies that:
1. AnthropicAuditorClientWrapper properly wraps the real client when available
2. Gracefully degrades to stub when ANTHROPIC_API_KEY is not set
3. Logs clear warnings when auditing is disabled
"""

import logging
import os
from unittest.mock import MagicMock, patch

from autopack.dual_auditor import AnthropicAuditorClientWrapper, StubClaudeAuditor
from autopack.llm_client import AuditorResult


class TestAnthropicAuditorClientWrapper:
    """Test AnthropicAuditorClientWrapper functionality."""

    def test_wrapper_with_no_api_key_logs_warning_and_returns_stub(self, caplog):
        """Test that missing API key results in stub behavior with warning."""
        # Ensure API key is not set
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False):
            wrapper = AnthropicAuditorClientWrapper(api_key=None)

            # Client should not be available
            assert not wrapper.is_available()
            assert wrapper._client is None

            # Warning should be logged during initialization
            assert any(
                "Failed to initialize Anthropic auditor" in record.message
                for record in caplog.records
            )

            # Review should return stub result
            result = wrapper.review_patch(
                patch_content="diff --git a/foo.py b/foo.py",
                phase_spec={"goal": "test"},
                max_tokens=1000,
                model="claude-sonnet-4-5",
            )

            # Verify stub result
            assert result.approved is True
            assert result.issues_found == []
            assert result.tokens_used == 0
            assert "stub" in result.model_used
            assert any("Anthropic auditor not available" in msg for msg in result.auditor_messages)

    def test_wrapper_with_api_key_uses_real_client(self, caplog):
        """Test that valid API key initializes real Anthropic client."""
        # Mock AnthropicBuilderClient
        mock_client = MagicMock()
        mock_client.review_patch.return_value = AuditorResult(
            approved=True,
            issues_found=[
                {
                    "severity": "minor",
                    "category": "style",
                    "description": "Test issue",
                    "location": "foo.py:10",
                }
            ],
            auditor_messages=["Real audit completed"],
            tokens_used=500,
            model_used="claude-sonnet-4-5",
        )

        with caplog.at_level(logging.INFO):
            with patch(
                "autopack.anthropic_clients.AnthropicBuilderClient", return_value=mock_client
            ):
                # Set fake API key
                wrapper = AnthropicAuditorClientWrapper(api_key="fake-key-for-test")

                # Client should be available
                assert wrapper.is_available()
                assert wrapper._client is not None

                # Success log should appear
                assert any(
                    "Real Anthropic auditor initialized" in record.message
                    for record in caplog.records
                )

                # Review should use real client
                result = wrapper.review_patch(
                    patch_content="diff --git a/foo.py b/foo.py",
                    phase_spec={"goal": "test"},
                    max_tokens=1000,
                    model="claude-sonnet-4-5",
                )

                # Verify real client was called
                mock_client.review_patch.assert_called_once()
                assert result.approved is True
                assert len(result.issues_found) == 1
                assert result.issues_found[0]["description"] == "Test issue"
                assert result.tokens_used == 500
                assert result.model_used == "claude-sonnet-4-5"

    def test_wrapper_passes_all_parameters_to_real_client(self):
        """Test that wrapper correctly forwards all parameters."""
        mock_client = MagicMock()
        mock_client.review_patch.return_value = AuditorResult(
            approved=True,
            issues_found=[],
            auditor_messages=[],
            tokens_used=0,
            model_used="claude-sonnet-4-5",
        )

        with patch("autopack.anthropic_clients.AnthropicBuilderClient", return_value=mock_client):
            wrapper = AnthropicAuditorClientWrapper(api_key="test-key")

            # Call with all parameters
            wrapper.review_patch(
                patch_content="test patch",
                phase_spec={"goal": "test", "phase_id": "phase-1"},
                file_context={"files": {}},
                max_tokens=2000,
                model="claude-opus-4-5",
                project_rules=[{"rule": "test"}],
                run_hints=[{"hint": "test"}],
            )

            # Verify all parameters were passed
            mock_client.review_patch.assert_called_once_with(
                patch_content="test patch",
                phase_spec={"goal": "test", "phase_id": "phase-1"},
                file_context={"files": {}},
                max_tokens=2000,
                model="claude-opus-4-5",
                project_rules=[{"rule": "test"}],
                run_hints=[{"hint": "test"}],
            )

    def test_is_available_returns_false_on_import_error(self, caplog):
        """Test that ImportError during client init results in unavailable state."""
        with patch(
            "autopack.anthropic_clients.AnthropicBuilderClient", side_effect=ImportError("test")
        ):
            wrapper = AnthropicAuditorClientWrapper(api_key="test-key")

            assert not wrapper.is_available()
            assert wrapper._client is None

            # Warning should be logged
            assert any(
                "Failed to initialize Anthropic auditor" in record.message
                for record in caplog.records
            )


class TestStubClaudeAuditorWithWarnings:
    """Test StubClaudeAuditor with enhanced warnings for IMP-FEAT-005."""

    def test_stub_logs_warning_on_init(self, caplog):
        """Test that StubClaudeAuditor logs warning on initialization."""
        with caplog.at_level(logging.WARNING):
            StubClaudeAuditor()

            # Warning should be logged about non-functional auditing
            assert any(
                "NON-FUNCTIONAL" in record.message and "StubClaudeAuditor" in record.message
                for record in caplog.records
            )

    def test_stub_logs_warning_on_review(self, caplog):
        """Test that review_patch logs warning about non-functional audit."""
        stub = StubClaudeAuditor()

        with caplog.at_level(logging.WARNING):
            stub.review_patch(
                patch_content="diff --git a/foo.py b/foo.py",
                phase_spec={"phase_id": "test-phase", "goal": "test"},
            )

            # Warning should be logged during review
            assert any(
                "test-phase" in record.message and "NON-FUNCTIONAL" in record.message
                for record in caplog.records
            )

    def test_stub_result_contains_clear_disclaimer(self):
        """Test that stub result contains clear disclaimer about being non-functional."""
        stub = StubClaudeAuditor()

        result = stub.review_patch(
            patch_content="diff --git a/foo.py b/foo.py",
            phase_spec={"goal": "test"},
        )

        # Result should indicate stub usage
        assert "stub" in result.model_used

        # Messages should clearly indicate non-functional auditing
        assert any("NON-FUNCTIONAL" in msg for msg in result.auditor_messages)

    def test_stub_always_returns_empty_issues(self):
        """Test that stub never finds issues (no real auditing)."""
        stub = StubClaudeAuditor()

        # Even with obviously bad patch
        result = stub.review_patch(
            patch_content="-critical_security_check()\n+pass",
            phase_spec={"goal": "security_test"},
        )

        # Stub returns empty issues (no real auditing performed)
        assert result.issues_found == []
        assert result.approved is True
        assert result.tokens_used == 0
