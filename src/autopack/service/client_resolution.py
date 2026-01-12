"""Client resolution and routing logic for LlmService.

This module contains pure functions for:
- Resolving which LLM client to use based on model name
- Mapping models to providers
- Client fallback chain logic

Design:
- Functions are pure and testable in isolation
- No side effects or database access
- Returns explicit results for the caller to act on

Extracted from: llm_service.py (_resolve_client_and_model, _model_to_provider)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class ClientResolutionResult:
    """Result of client resolution.

    Attributes:
        client: The resolved LLM client instance (or None if unavailable)
        model: The resolved model name (may differ from requested if fallback occurred)
        fallback_used: Whether a fallback was used
        fallback_reason: Reason for fallback (if any)
        error: Error message if no client could be resolved
    """

    client: Optional[Any]
    model: str
    fallback_used: bool
    fallback_reason: Optional[str]
    error: Optional[str]


@dataclass(frozen=True)
class ClientRegistry:
    """Registry of available LLM clients.

    Holds references to builder/auditor clients for each provider.
    Clients may be None if the provider is unavailable.
    """

    glm_builder: Optional[Any] = None
    glm_auditor: Optional[Any] = None
    openai_builder: Optional[Any] = None
    openai_auditor: Optional[Any] = None
    anthropic_builder: Optional[Any] = None
    anthropic_auditor: Optional[Any] = None
    gemini_builder: Optional[Any] = None
    gemini_auditor: Optional[Any] = None


def model_to_provider(model: str) -> str:
    """Map model name to provider.

    Args:
        model: Model name (e.g., "gpt-4o", "claude-sonnet-4-5", "gemini-2.5-pro")

    Returns:
        Provider name: "google", "openai", "anthropic"
    """
    if model.startswith("gemini-"):
        return "google"
    elif model.startswith("gpt-") or model.startswith("o1-"):
        return "openai"
    elif model.startswith("claude-") or model.startswith("opus-"):
        return "anthropic"
    else:
        return "openai"  # Safe default


def resolve_client_and_model(
    role: str,
    requested_model: str,
    registry: ClientRegistry,
) -> ClientResolutionResult:
    """Resolve client and fallback model if needed.

    Routing priority (current stack):
    1. Gemini models (gemini-*) -> Gemini client (uses GOOGLE_API_KEY)
    2. Claude models (claude-*) -> Anthropic client
    3. OpenAI models (gpt-*, o1-*) -> OpenAI client
    4. Fallback chain: Gemini -> Anthropic -> OpenAI

    GLM models (glm-*) are treated as legacy; current configs never
    select them, and GLM clients are disabled.

    Args:
        role: Either "builder" or "auditor"
        requested_model: The model name requested
        registry: Client registry with available clients

    Returns:
        ClientResolutionResult with resolved client and model
    """
    # Select client set based on role
    if role == "builder":
        glm_client = registry.glm_builder
        openai_client = registry.openai_builder
        anthropic_client = registry.anthropic_builder
        gemini_client = registry.gemini_builder
    else:
        glm_client = registry.glm_auditor
        openai_client = registry.openai_auditor
        anthropic_client = registry.anthropic_auditor
        gemini_client = registry.gemini_auditor

    # Route Gemini models to Gemini client
    if requested_model.lower().startswith("gemini-"):
        if gemini_client is not None:
            return ClientResolutionResult(
                client=gemini_client,
                model=requested_model,
                fallback_used=False,
                fallback_reason=None,
                error=None,
            )
        # Gemini not available, try fallbacks
        if anthropic_client is not None:
            return ClientResolutionResult(
                client=anthropic_client,
                model="claude-sonnet-4-5",
                fallback_used=True,
                fallback_reason=f"Gemini model {requested_model} selected but GOOGLE_API_KEY not set. Falling back to Anthropic (claude-sonnet-4-5).",
                error=None,
            )
        if openai_client is not None:
            return ClientResolutionResult(
                client=openai_client,
                model="gpt-4o",
                fallback_used=True,
                fallback_reason=f"Gemini model {requested_model} selected but GOOGLE_API_KEY not set. Falling back to OpenAI (gpt-4o).",
                error=None,
            )
        if glm_client is not None:
            # Keep GLM fallback model configurable (avoid hardcoding model bumps).
            # Import locally to avoid circular imports
            from autopack.model_registry import resolve_model_alias

            glm_fallback = resolve_model_alias("glm-tidy")
            return ClientResolutionResult(
                client=glm_client,
                model=glm_fallback,
                fallback_used=True,
                fallback_reason=f"Gemini model {requested_model} selected but GOOGLE_API_KEY not set. Falling back to GLM ({glm_fallback}).",
                error=None,
            )
        return ClientResolutionResult(
            client=None,
            model=requested_model,
            fallback_used=False,
            fallback_reason=None,
            error=f"Gemini model {requested_model} selected but no LLM clients are available. Set GOOGLE_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY, or GLM_API_KEY.",
        )

    # Legacy GLM models: treated as misconfiguration
    if requested_model.lower().startswith("glm-"):
        return ClientResolutionResult(
            client=None,
            model=requested_model,
            fallback_used=False,
            fallback_reason=None,
            error=f"GLM model {requested_model} selected but GLM support is disabled in current routing. "
            f"Update config/models.yaml to use claude-sonnet-4-5/claude-opus-4-5 instead.",
        )

    # Route Claude models to Anthropic client
    if "claude" in requested_model.lower():
        if anthropic_client is not None:
            return ClientResolutionResult(
                client=anthropic_client,
                model=requested_model,
                fallback_used=False,
                fallback_reason=None,
                error=None,
            )
        # Anthropic not available, try fallbacks
        if gemini_client is not None:
            return ClientResolutionResult(
                client=gemini_client,
                model="gemini-2.5-pro",
                fallback_used=True,
                fallback_reason=f"Claude model {requested_model} selected but Anthropic not available. Falling back to Gemini (gemini-2.5-pro).",
                error=None,
            )
        if openai_client is not None:
            return ClientResolutionResult(
                client=openai_client,
                model="gpt-4o",
                fallback_used=True,
                fallback_reason=f"Claude model {requested_model} selected but Anthropic not available. Falling back to OpenAI (gpt-4o).",
                error=None,
            )
        return ClientResolutionResult(
            client=None,
            model=requested_model,
            fallback_used=False,
            fallback_reason=None,
            error=f"Claude model {requested_model} selected but no LLM clients are available",
        )

    # Route OpenAI models (gpt-*, o1-*, etc.) to OpenAI client
    if openai_client is not None:
        return ClientResolutionResult(
            client=openai_client,
            model=requested_model,
            fallback_used=False,
            fallback_reason=None,
            error=None,
        )
    # OpenAI not available, try fallbacks
    if gemini_client is not None:
        return ClientResolutionResult(
            client=gemini_client,
            model="gemini-2.5-pro",
            fallback_used=True,
            fallback_reason=f"OpenAI model {requested_model} selected but OpenAI not available. Falling back to Gemini (gemini-2.5-pro).",
            error=None,
        )
    if anthropic_client is not None:
        return ClientResolutionResult(
            client=anthropic_client,
            model="claude-sonnet-4-5",
            fallback_used=True,
            fallback_reason=f"OpenAI model {requested_model} selected but OpenAI not available. Falling back to Anthropic (claude-sonnet-4-5).",
            error=None,
        )
    return ClientResolutionResult(
        client=None,
        model=requested_model,
        fallback_used=False,
        fallback_reason=None,
        error=f"OpenAI model {requested_model} selected but no LLM clients are available",
    )


def get_fallback_chain(requested_model: str) -> list[str]:
    """Get the fallback chain for a given model.

    Useful for understanding and testing the fallback behavior.

    Args:
        requested_model: The model name requested

    Returns:
        List of providers in fallback order
    """
    if requested_model.lower().startswith("gemini-"):
        return ["gemini", "anthropic", "openai", "glm"]
    elif "claude" in requested_model.lower():
        return ["anthropic", "gemini", "openai"]
    else:
        return ["openai", "gemini", "anthropic"]
