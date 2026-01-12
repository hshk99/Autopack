"""Client resolution and provider health logic for LLM service.

This module handles:
- Resolving client instances and fallback models based on availability
- Provider priority: Gemini → Anthropic → OpenAI
- GLM rejection enforcement (GLM is disabled)
- Provider health tracking via ModelRouter.disable_provider
"""

import logging
from typing import Literal, Optional, Tuple

logger = logging.getLogger(__name__)


def resolve_client_and_model(
    role: Literal["builder", "auditor"],
    requested_model: str,
    *,
    gemini_client: Optional[object] = None,
    anthropic_client: Optional[object] = None,
    openai_client: Optional[object] = None,
    glm_client: Optional[object] = None,
) -> Tuple[object, str]:
    """Resolve client and fallback model if needed.

    Routing priority (current stack):
    1. Gemini models (gemini-*) -> Gemini client (uses GOOGLE_API_KEY)
    2. Claude models (claude-*) -> Anthropic client
    3. OpenAI models (gpt-*, o1-*) -> OpenAI client
    4. Fallback chain: Gemini -> Anthropic -> OpenAI

    GLM models (glm-*) are treated as legacy; current configs never
    select them, and GLM clients are disabled.

    Args:
        role: Role requesting the client (builder or auditor)
        requested_model: Model name selected by ModelRouter
        gemini_client: Initialized Gemini client (or None if unavailable)
        anthropic_client: Initialized Anthropic client (or None if unavailable)
        openai_client: Initialized OpenAI client (or None if unavailable)
        glm_client: Initialized GLM client (or None if disabled)

    Returns:
        Tuple of (client, resolved_model)

    Raises:
        RuntimeError: If requested model is GLM (explicitly rejected)
        RuntimeError: If no clients are available for the requested model
    """
    # Route Gemini models to Gemini client
    if requested_model.lower().startswith("gemini-"):
        if gemini_client is not None:
            return gemini_client, requested_model
        # Gemini not available, try fallbacks
        if anthropic_client is not None:
            logger.warning(
                f"Gemini model {requested_model} selected but GOOGLE_API_KEY not set. "
                f"Falling back to Anthropic (claude-sonnet-4-5)."
            )
            return anthropic_client, "claude-sonnet-4-5"
        if openai_client is not None:
            logger.warning(
                f"Gemini model {requested_model} selected but GOOGLE_API_KEY not set. "
                f"Falling back to OpenAI (gpt-4o)."
            )
            return openai_client, "gpt-4o"
        if glm_client is not None:
            # Keep GLM fallback model configurable (avoid hardcoding model bumps).
            from autopack.model_registry import resolve_model_alias

            glm_fallback = resolve_model_alias("glm-tidy")
            logger.warning(
                f"Gemini model {requested_model} selected but GOOGLE_API_KEY not set. "
                f"Falling back to GLM ({glm_fallback})."
            )
            return glm_client, glm_fallback
        raise RuntimeError(
            f"Gemini model {requested_model} selected but no LLM clients are available. "
            f"Set GOOGLE_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY, or GLM_API_KEY."
        )

    # Legacy GLM models: treated as misconfiguration
    if requested_model.lower().startswith("glm-"):
        raise RuntimeError(
            f"GLM model {requested_model} selected but GLM support is disabled in current routing. "
            f"Update config/models.yaml to use claude-sonnet-4-5/claude-opus-4-5 instead."
        )

    # Route Claude models to Anthropic client
    if "claude" in requested_model.lower():
        if anthropic_client is not None:
            return anthropic_client, requested_model
        # Anthropic not available, try fallbacks
        if gemini_client is not None:
            logger.warning(
                f"Claude model {requested_model} selected but Anthropic not available. "
                f"Falling back to Gemini (gemini-2.5-pro)."
            )
            return gemini_client, "gemini-2.5-pro"
        if openai_client is not None:
            logger.warning(
                f"Claude model {requested_model} selected but Anthropic not available. "
                f"Falling back to OpenAI (gpt-4o)."
            )
            return openai_client, "gpt-4o"
        raise RuntimeError(
            f"Claude model {requested_model} selected but no LLM clients are available"
        )

    # Route OpenAI models (gpt-*, o1-*, etc.) to OpenAI client
    if openai_client is not None:
        return openai_client, requested_model
    # OpenAI not available, try fallbacks
    if gemini_client is not None:
        logger.warning(
            f"OpenAI model {requested_model} selected but OpenAI not available. "
            f"Falling back to Gemini (gemini-2.5-pro)."
        )
        return gemini_client, "gemini-2.5-pro"
    if anthropic_client is not None:
        logger.warning(
            f"OpenAI model {requested_model} selected but OpenAI not available. "
            f"Falling back to Anthropic (claude-sonnet-4-5)."
        )
        return anthropic_client, "claude-sonnet-4-5"
    raise RuntimeError(
        f"OpenAI model {requested_model} selected but no LLM clients are available"
    )


def resolve_builder_client(
    requested_model: str,
    *,
    gemini_builder: Optional[object] = None,
    anthropic_builder: Optional[object] = None,
    openai_builder: Optional[object] = None,
    glm_builder: Optional[object] = None,
) -> Tuple[object, str]:
    """Resolve builder client and model.

    This is a convenience wrapper around resolve_client_and_model for builder role.

    Args:
        requested_model: Model name selected by ModelRouter
        gemini_builder: Initialized Gemini builder client (or None if unavailable)
        anthropic_builder: Initialized Anthropic builder client (or None if unavailable)
        openai_builder: Initialized OpenAI builder client (or None if unavailable)
        glm_builder: Initialized GLM builder client (or None if disabled)

    Returns:
        Tuple of (builder_client, resolved_model)
    """
    return resolve_client_and_model(
        "builder",
        requested_model,
        gemini_client=gemini_builder,
        anthropic_client=anthropic_builder,
        openai_client=openai_builder,
        glm_client=glm_builder,
    )


def resolve_auditor_client(
    requested_model: str,
    *,
    gemini_auditor: Optional[object] = None,
    anthropic_auditor: Optional[object] = None,
    openai_auditor: Optional[object] = None,
    glm_auditor: Optional[object] = None,
) -> Tuple[object, str]:
    """Resolve auditor client and model.

    This is a convenience wrapper around resolve_client_and_model for auditor role.

    Args:
        requested_model: Model name selected by ModelRouter
        gemini_auditor: Initialized Gemini auditor client (or None if unavailable)
        anthropic_auditor: Initialized Anthropic auditor client (or None if unavailable)
        openai_auditor: Initialized OpenAI auditor client (or None if unavailable)
        glm_auditor: Initialized GLM auditor client (or None if disabled)

    Returns:
        Tuple of (auditor_client, resolved_model)
    """
    return resolve_client_and_model(
        "auditor",
        requested_model,
        gemini_client=gemini_auditor,
        anthropic_client=anthropic_auditor,
        openai_client=openai_auditor,
        glm_client=glm_auditor,
    )
