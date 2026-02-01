"""Contract tests for service/client_resolution.py.

These tests verify the client resolution module's behavior independently
of the full LlmService, using mock client objects.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from autopack.service.client_resolution import (ClientRegistry,
                                                ClientResolutionResult,
                                                get_fallback_chain,
                                                model_to_provider,
                                                resolve_client_and_model)

# ============================================================================
# model_to_provider tests
# ============================================================================


class TestModelToProvider:
    """Tests for model_to_provider function."""

    @pytest.mark.parametrize(
        "model,expected_provider",
        [
            # Gemini models
            ("gemini-2.5-pro", "google"),
            ("gemini-1.5-flash", "google"),
            # GPT models
            ("gpt-4o", "openai"),
            ("gpt-4-turbo", "openai"),
            # O1 models
            ("o1-preview", "openai"),
            ("o1-mini", "openai"),
            # Claude models
            ("claude-sonnet-4-5", "anthropic"),
            ("claude-opus-4-5", "anthropic"),
            # Opus prefix
            ("opus-4", "anthropic"),
            # Unknown models (default to openai)
            ("unknown-model", "openai"),
            ("llama-70b", "openai"),
        ],
    )
    def test_model_to_provider(self, model: str, expected_provider: str) -> None:
        """Test model to provider mapping with parameterized inputs."""
        assert model_to_provider(model) == expected_provider


# ============================================================================
# resolve_client_and_model tests
# ============================================================================


class TestResolveClientAndModel:
    """Tests for resolve_client_and_model function."""

    @pytest.fixture
    def mock_gemini_client(self) -> MagicMock:
        return MagicMock(name="gemini_client")

    @pytest.fixture
    def mock_anthropic_client(self) -> MagicMock:
        return MagicMock(name="anthropic_client")

    @pytest.fixture
    def mock_openai_client(self) -> MagicMock:
        return MagicMock(name="openai_client")

    # --- Gemini model routing ---

    def test_gemini_model_routes_to_gemini_client(self, mock_gemini_client: MagicMock) -> None:
        registry = ClientRegistry(gemini_builder=mock_gemini_client)
        result = resolve_client_and_model("builder", "gemini-2.5-pro", registry)

        assert result.client == mock_gemini_client
        assert result.model == "gemini-2.5-pro"
        assert result.fallback_used is False
        assert result.error is None

    def test_gemini_model_falls_back_to_anthropic(self, mock_anthropic_client: MagicMock) -> None:
        registry = ClientRegistry(anthropic_builder=mock_anthropic_client)
        result = resolve_client_and_model("builder", "gemini-2.5-pro", registry)

        assert result.client == mock_anthropic_client
        assert result.model == "claude-sonnet-4-5"
        assert result.fallback_used is True
        assert "Falling back to Anthropic" in (result.fallback_reason or "")

    def test_gemini_model_falls_back_to_openai(self, mock_openai_client: MagicMock) -> None:
        registry = ClientRegistry(openai_builder=mock_openai_client)
        result = resolve_client_and_model("builder", "gemini-2.5-pro", registry)

        assert result.client == mock_openai_client
        assert result.model == "gpt-4o"
        assert result.fallback_used is True
        assert "Falling back to OpenAI" in (result.fallback_reason or "")

    def test_gemini_model_no_clients_returns_error(self) -> None:
        registry = ClientRegistry()
        result = resolve_client_and_model("builder", "gemini-2.5-pro", registry)

        assert result.client is None
        assert result.error is not None
        assert "no LLM clients are available" in result.error

    # --- Claude model routing ---

    def test_claude_model_routes_to_anthropic_client(
        self, mock_anthropic_client: MagicMock
    ) -> None:
        registry = ClientRegistry(anthropic_auditor=mock_anthropic_client)
        result = resolve_client_and_model("auditor", "claude-sonnet-4-5", registry)

        assert result.client == mock_anthropic_client
        assert result.model == "claude-sonnet-4-5"
        assert result.fallback_used is False
        assert result.error is None

    def test_claude_model_falls_back_to_gemini(self, mock_gemini_client: MagicMock) -> None:
        registry = ClientRegistry(gemini_auditor=mock_gemini_client)
        result = resolve_client_and_model("auditor", "claude-sonnet-4-5", registry)

        assert result.client == mock_gemini_client
        assert result.model == "gemini-2.5-pro"
        assert result.fallback_used is True
        assert "Falling back to Gemini" in (result.fallback_reason or "")

    def test_claude_model_falls_back_to_openai(self, mock_openai_client: MagicMock) -> None:
        registry = ClientRegistry(openai_auditor=mock_openai_client)
        result = resolve_client_and_model("auditor", "claude-opus-4-5", registry)

        assert result.client == mock_openai_client
        assert result.model == "gpt-4o"
        assert result.fallback_used is True
        assert "Falling back to OpenAI" in (result.fallback_reason or "")

    def test_claude_model_no_clients_returns_error(self) -> None:
        registry = ClientRegistry()
        result = resolve_client_and_model("builder", "claude-sonnet-4-5", registry)

        assert result.client is None
        assert result.error is not None
        assert "no LLM clients are available" in result.error

    # --- OpenAI model routing ---

    def test_openai_model_routes_to_openai_client(self, mock_openai_client: MagicMock) -> None:
        registry = ClientRegistry(openai_builder=mock_openai_client)
        result = resolve_client_and_model("builder", "gpt-4o", registry)

        assert result.client == mock_openai_client
        assert result.model == "gpt-4o"
        assert result.fallback_used is False
        assert result.error is None

    def test_openai_model_falls_back_to_gemini(self, mock_gemini_client: MagicMock) -> None:
        registry = ClientRegistry(gemini_builder=mock_gemini_client)
        result = resolve_client_and_model("builder", "gpt-4o", registry)

        assert result.client == mock_gemini_client
        assert result.model == "gemini-2.5-pro"
        assert result.fallback_used is True
        assert "Falling back to Gemini" in (result.fallback_reason or "")

    def test_openai_model_falls_back_to_anthropic(self, mock_anthropic_client: MagicMock) -> None:
        registry = ClientRegistry(anthropic_builder=mock_anthropic_client)
        result = resolve_client_and_model("builder", "gpt-4o", registry)

        assert result.client == mock_anthropic_client
        assert result.model == "claude-sonnet-4-5"
        assert result.fallback_used is True
        assert "Falling back to Anthropic" in (result.fallback_reason or "")

    def test_openai_model_no_clients_returns_error(self) -> None:
        registry = ClientRegistry()
        result = resolve_client_and_model("builder", "gpt-4o", registry)

        assert result.client is None
        assert result.error is not None
        assert "no LLM clients are available" in result.error

    # --- GLM model routing (legacy, disabled) ---

    def test_glm_model_returns_error(self) -> None:
        registry = ClientRegistry()
        result = resolve_client_and_model("builder", "glm-4-plus", registry)

        assert result.client is None
        assert result.error is not None
        assert "GLM support is disabled" in result.error

    # --- Role-specific client selection ---

    def test_builder_role_uses_builder_clients(
        self,
        mock_gemini_client: MagicMock,
        mock_anthropic_client: MagicMock,
    ) -> None:
        registry = ClientRegistry(
            gemini_builder=mock_gemini_client,
            gemini_auditor=mock_anthropic_client,  # Different client for auditor
        )
        result = resolve_client_and_model("builder", "gemini-2.5-pro", registry)

        assert result.client == mock_gemini_client

    def test_auditor_role_uses_auditor_clients(
        self,
        mock_gemini_client: MagicMock,
        mock_anthropic_client: MagicMock,
    ) -> None:
        registry = ClientRegistry(
            gemini_builder=mock_gemini_client,  # Different client for builder
            gemini_auditor=mock_anthropic_client,
        )
        result = resolve_client_and_model("auditor", "gemini-2.5-pro", registry)

        assert result.client == mock_anthropic_client


# ============================================================================
# get_fallback_chain tests
# ============================================================================


class TestGetFallbackChain:
    """Tests for get_fallback_chain function."""

    @pytest.mark.parametrize(
        "model,expected_chain",
        [
            ("gemini-2.5-pro", ["gemini", "anthropic", "openai", "glm"]),
            ("claude-sonnet-4-5", ["anthropic", "gemini", "openai"]),
            ("gpt-4o", ["openai", "gemini", "anthropic"]),
            ("llama-70b", ["openai", "gemini", "anthropic"]),
        ],
    )
    def test_fallback_chain(self, model: str, expected_chain: list) -> None:
        """Test fallback chain with parameterized model inputs."""
        chain = get_fallback_chain(model)
        assert chain == expected_chain


# ============================================================================
# ClientResolutionResult dataclass tests
# ============================================================================


class TestClientResolutionResult:
    """Tests for ClientResolutionResult dataclass."""

    def test_frozen_dataclass(self) -> None:
        result = ClientResolutionResult(
            client=None,
            model="gpt-4o",
            fallback_used=False,
            fallback_reason=None,
            error=None,
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            result.model = "changed"  # type: ignore[misc]

    def test_success_result(self) -> None:
        client = MagicMock()
        result = ClientResolutionResult(
            client=client,
            model="gpt-4o",
            fallback_used=False,
            fallback_reason=None,
            error=None,
        )
        assert result.client is not None
        assert result.error is None

    def test_fallback_result(self) -> None:
        client = MagicMock()
        result = ClientResolutionResult(
            client=client,
            model="claude-sonnet-4-5",
            fallback_used=True,
            fallback_reason="Primary unavailable",
            error=None,
        )
        assert result.fallback_used is True
        assert result.fallback_reason is not None

    def test_error_result(self) -> None:
        result = ClientResolutionResult(
            client=None,
            model="gpt-4o",
            fallback_used=False,
            fallback_reason=None,
            error="No clients available",
        )
        assert result.client is None
        assert result.error is not None
