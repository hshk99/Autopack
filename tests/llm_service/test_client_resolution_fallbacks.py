"""Tests for client resolution and fallback logic (PR-SVC-1).

These tests verify:
- Gemini → Anthropic fallback when Gemini unavailable
- Anthropic → OpenAI fallback when Anthropic unavailable
- GLM is always rejected (never selected)
- Provider priority and fallback behavior is documented
- Fallback exhaustion raises clear error
"""

import pytest
from unittest.mock import MagicMock

from autopack.llm.client_resolution import (
    resolve_client_and_model,
    resolve_builder_client,
    resolve_auditor_client,
)


class TestClientResolutionFallbacks:
    """Tests for client resolution and provider fallback logic."""

    def test_gemini_model_with_gemini_client_available(self):
        """Gemini model routes to Gemini client when available."""
        mock_gemini_client = MagicMock()

        client, model = resolve_client_and_model(
            "builder",
            "gemini-2.5-pro",
            gemini_client=mock_gemini_client,
            anthropic_client=None,
            openai_client=None,
        )

        assert client is mock_gemini_client
        assert model == "gemini-2.5-pro"

    def test_gemini_fallback_to_anthropic(self):
        """Gemini model falls back to Anthropic when Gemini unavailable."""
        mock_anthropic_client = MagicMock()

        client, model = resolve_client_and_model(
            "builder",
            "gemini-2.5-pro",
            gemini_client=None,
            anthropic_client=mock_anthropic_client,
            openai_client=None,
        )

        assert client is mock_anthropic_client
        assert model == "claude-sonnet-4-5"

    def test_gemini_fallback_to_openai(self):
        """Gemini model falls back to OpenAI when Gemini and Anthropic unavailable."""
        mock_openai_client = MagicMock()

        client, model = resolve_client_and_model(
            "builder",
            "gemini-2.5-pro",
            gemini_client=None,
            anthropic_client=None,
            openai_client=mock_openai_client,
        )

        assert client is mock_openai_client
        assert model == "gpt-4o"

    def test_claude_model_with_anthropic_client_available(self):
        """Claude model routes to Anthropic client when available."""
        mock_anthropic_client = MagicMock()

        client, model = resolve_client_and_model(
            "auditor",
            "claude-sonnet-4-5",
            gemini_client=None,
            anthropic_client=mock_anthropic_client,
            openai_client=None,
        )

        assert client is mock_anthropic_client
        assert model == "claude-sonnet-4-5"

    def test_claude_fallback_to_gemini(self):
        """Claude model falls back to Gemini when Anthropic unavailable."""
        mock_gemini_client = MagicMock()

        client, model = resolve_client_and_model(
            "auditor",
            "claude-opus-4-5",
            gemini_client=mock_gemini_client,
            anthropic_client=None,
            openai_client=None,
        )

        assert client is mock_gemini_client
        assert model == "gemini-2.5-pro"

    def test_claude_fallback_to_openai(self):
        """Claude model falls back to OpenAI when Anthropic and Gemini unavailable."""
        mock_openai_client = MagicMock()

        client, model = resolve_client_and_model(
            "auditor",
            "claude-sonnet-4-5",
            gemini_client=None,
            anthropic_client=None,
            openai_client=mock_openai_client,
        )

        assert client is mock_openai_client
        assert model == "gpt-4o"

    def test_openai_model_with_openai_client_available(self):
        """OpenAI model routes to OpenAI client when available."""
        mock_openai_client = MagicMock()

        client, model = resolve_client_and_model(
            "builder",
            "gpt-4o",
            gemini_client=None,
            anthropic_client=None,
            openai_client=mock_openai_client,
        )

        assert client is mock_openai_client
        assert model == "gpt-4o"

    def test_openai_fallback_to_gemini(self):
        """OpenAI model falls back to Gemini when OpenAI unavailable."""
        mock_gemini_client = MagicMock()

        client, model = resolve_client_and_model(
            "builder",
            "gpt-4o",
            gemini_client=mock_gemini_client,
            anthropic_client=None,
            openai_client=None,
        )

        assert client is mock_gemini_client
        assert model == "gemini-2.5-pro"

    def test_openai_fallback_to_anthropic(self):
        """OpenAI model falls back to Anthropic when OpenAI and Gemini unavailable."""
        mock_anthropic_client = MagicMock()

        client, model = resolve_client_and_model(
            "builder",
            "gpt-4o",
            gemini_client=None,
            anthropic_client=mock_anthropic_client,
            openai_client=None,
        )

        assert client is mock_anthropic_client
        assert model == "claude-sonnet-4-5"

    def test_glm_model_rejected(self):
        """GLM models are always rejected with clear error."""
        mock_glm_client = MagicMock()

        with pytest.raises(RuntimeError) as exc_info:
            resolve_client_and_model(
                "builder",
                "glm-4-flash",
                gemini_client=None,
                anthropic_client=None,
                openai_client=None,
                glm_client=mock_glm_client,
            )

        assert "GLM support is disabled" in str(exc_info.value)
        assert "config/models.yaml" in str(exc_info.value)

    def test_fallback_exhaustion_gemini_model(self):
        """Gemini model with no clients raises clear error."""
        with pytest.raises(RuntimeError) as exc_info:
            resolve_client_and_model(
                "builder",
                "gemini-2.5-pro",
                gemini_client=None,
                anthropic_client=None,
                openai_client=None,
            )

        assert "no LLM clients are available" in str(exc_info.value)
        assert "GOOGLE_API_KEY" in str(exc_info.value)

    def test_fallback_exhaustion_claude_model(self):
        """Claude model with no clients raises clear error."""
        with pytest.raises(RuntimeError) as exc_info:
            resolve_client_and_model(
                "auditor",
                "claude-sonnet-4-5",
                gemini_client=None,
                anthropic_client=None,
                openai_client=None,
            )

        assert "no LLM clients are available" in str(exc_info.value)

    def test_fallback_exhaustion_openai_model(self):
        """OpenAI model with no clients raises clear error."""
        with pytest.raises(RuntimeError) as exc_info:
            resolve_client_and_model(
                "builder",
                "gpt-4o",
                gemini_client=None,
                anthropic_client=None,
                openai_client=None,
            )

        assert "no LLM clients are available" in str(exc_info.value)


class TestBuilderClientResolution:
    """Tests for resolve_builder_client convenience function."""

    def test_resolve_builder_client_gemini(self):
        """resolve_builder_client routes Gemini model correctly."""
        mock_gemini_builder = MagicMock()

        client, model = resolve_builder_client(
            "gemini-2.5-pro",
            gemini_builder=mock_gemini_builder,
        )

        assert client is mock_gemini_builder
        assert model == "gemini-2.5-pro"

    def test_resolve_builder_client_anthropic(self):
        """resolve_builder_client routes Claude model correctly."""
        mock_anthropic_builder = MagicMock()

        client, model = resolve_builder_client(
            "claude-sonnet-4-5",
            anthropic_builder=mock_anthropic_builder,
        )

        assert client is mock_anthropic_builder
        assert model == "claude-sonnet-4-5"

    def test_resolve_builder_client_openai(self):
        """resolve_builder_client routes OpenAI model correctly."""
        mock_openai_builder = MagicMock()

        client, model = resolve_builder_client(
            "gpt-4o",
            openai_builder=mock_openai_builder,
        )

        assert client is mock_openai_builder
        assert model == "gpt-4o"

    def test_resolve_builder_client_fallback(self):
        """resolve_builder_client falls back when primary unavailable."""
        mock_anthropic_builder = MagicMock()

        client, model = resolve_builder_client(
            "gemini-2.5-pro",
            gemini_builder=None,
            anthropic_builder=mock_anthropic_builder,
        )

        assert client is mock_anthropic_builder
        assert model == "claude-sonnet-4-5"


class TestAuditorClientResolution:
    """Tests for resolve_auditor_client convenience function."""

    def test_resolve_auditor_client_gemini(self):
        """resolve_auditor_client routes Gemini model correctly."""
        mock_gemini_auditor = MagicMock()

        client, model = resolve_auditor_client(
            "gemini-2.5-pro",
            gemini_auditor=mock_gemini_auditor,
        )

        assert client is mock_gemini_auditor
        assert model == "gemini-2.5-pro"

    def test_resolve_auditor_client_anthropic(self):
        """resolve_auditor_client routes Claude model correctly."""
        mock_anthropic_auditor = MagicMock()

        client, model = resolve_auditor_client(
            "claude-opus-4-5",
            anthropic_auditor=mock_anthropic_auditor,
        )

        assert client is mock_anthropic_auditor
        assert model == "claude-opus-4-5"

    def test_resolve_auditor_client_openai(self):
        """resolve_auditor_client routes OpenAI model correctly."""
        mock_openai_auditor = MagicMock()

        client, model = resolve_auditor_client(
            "gpt-4o",
            openai_auditor=mock_openai_auditor,
        )

        assert client is mock_openai_auditor
        assert model == "gpt-4o"

    def test_resolve_auditor_client_fallback(self):
        """resolve_auditor_client falls back when primary unavailable."""
        mock_openai_auditor = MagicMock()

        client, model = resolve_auditor_client(
            "claude-sonnet-4-5",
            gemini_auditor=None,
            anthropic_auditor=None,
            openai_auditor=mock_openai_auditor,
        )

        assert client is mock_openai_auditor
        assert model == "gpt-4o"


class TestProviderPriority:
    """Tests documenting provider priority and fallback behavior."""

    def test_provider_priority_gemini_first(self):
        """Provider priority: Gemini is preferred when available."""
        mock_gemini = MagicMock()
        mock_anthropic = MagicMock()
        mock_openai = MagicMock()

        client, model = resolve_client_and_model(
            "builder",
            "gemini-2.5-pro",
            gemini_client=mock_gemini,
            anthropic_client=mock_anthropic,
            openai_client=mock_openai,
        )

        # Gemini model uses Gemini client (not fallback)
        assert client is mock_gemini
        assert model == "gemini-2.5-pro"

    def test_provider_priority_anthropic_second(self):
        """Provider priority: Anthropic is second choice for Gemini fallback."""
        mock_anthropic = MagicMock()
        mock_openai = MagicMock()

        client, model = resolve_client_and_model(
            "builder",
            "gemini-2.5-pro",
            gemini_client=None,
            anthropic_client=mock_anthropic,
            openai_client=mock_openai,
        )

        # When Gemini unavailable, prefer Anthropic over OpenAI
        assert client is mock_anthropic
        assert model == "claude-sonnet-4-5"

    def test_provider_priority_openai_third(self):
        """Provider priority: OpenAI is third choice (final fallback)."""
        mock_openai = MagicMock()

        client, model = resolve_client_and_model(
            "builder",
            "gemini-2.5-pro",
            gemini_client=None,
            anthropic_client=None,
            openai_client=mock_openai,
        )

        # OpenAI is last resort
        assert client is mock_openai
        assert model == "gpt-4o"

    def test_fallback_chain_documented(self):
        """Fallback chain is: Gemini → Anthropic → OpenAI."""
        # Test 1: Gemini available - no fallback
        mock_gemini = MagicMock()
        client, _ = resolve_client_and_model(
            "builder",
            "gemini-2.5-pro",
            gemini_client=mock_gemini,
        )
        assert client is mock_gemini

        # Test 2: Only Anthropic available - first fallback
        mock_anthropic = MagicMock()
        client, model = resolve_client_and_model(
            "builder",
            "gemini-2.5-pro",
            gemini_client=None,
            anthropic_client=mock_anthropic,
        )
        assert client is mock_anthropic
        assert model == "claude-sonnet-4-5"

        # Test 3: Only OpenAI available - second fallback
        mock_openai = MagicMock()
        client, model = resolve_client_and_model(
            "builder",
            "gemini-2.5-pro",
            gemini_client=None,
            anthropic_client=None,
            openai_client=mock_openai,
        )
        assert client is mock_openai
        assert model == "gpt-4o"
