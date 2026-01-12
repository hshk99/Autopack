"""Usage recording module for LlmService.

This module contains functions for:
- Recording LLM usage events to the database
- Token estimation for soft cap warnings
- Usage event creation

Design:
- Functions encapsulate usage recording logic
- Database session is passed in (no global state)
- Returns explicit results for observability

Extracted from: llm_service.py (_record_usage, _record_usage_total_only, estimate_tokens)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from autopack.usage_recorder import LlmUsageEvent

logger = logging.getLogger(__name__)


def estimate_tokens(text: str, *, chars_per_token: float = 4.0) -> int:
    """
    Rough token estimation for soft cap warnings.

    Per GPT_RESPONSE20 C2 and GPT_RESPONSE21 Q2: Single factor 4.0 for all models in Phase 1.
    ±20-30% error is acceptable for advisory soft caps.
    Actual usage from provider is authoritative for cost tracking.

    Args:
        text: Text to estimate tokens for
        chars_per_token: Average characters per token (default 4.0 for all models)

    Returns:
        Estimated token count (minimum 1)
    """
    return max(1, int(len(text) / chars_per_token))


@dataclass(frozen=True)
class UsageRecordingResult:
    """Result of usage recording operation.

    Attributes:
        success: Whether the recording succeeded
        event_id: ID of the created event (if successful)
        error: Error message (if failed)
    """

    success: bool
    event_id: Optional[int]
    error: Optional[str]


def record_usage(
    db: Session,
    *,
    provider: str,
    model: str,
    role: str,
    prompt_tokens: int,
    completion_tokens: int,
    run_id: Optional[str] = None,
    phase_id: Optional[str] = None,
) -> UsageRecordingResult:
    """
    Record LLM usage in database with exact token splits.

    BUILD-144 P0.4: Always records total_tokens = prompt_tokens + completion_tokens.

    Args:
        db: Database session
        provider: Provider name (openai, anthropic, etc.)
        model: Model name
        role: builder, auditor, or agent:name
        prompt_tokens: Input tokens (exact from provider)
        completion_tokens: Output tokens (exact from provider)
        run_id: Optional run identifier
        phase_id: Optional phase identifier

    Returns:
        UsageRecordingResult indicating success or failure
    """
    try:
        usage_event = LlmUsageEvent(
            provider=provider,
            model=model,
            role=role,
            total_tokens=prompt_tokens + completion_tokens,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            run_id=run_id,
            phase_id=phase_id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(usage_event)
        db.commit()

        # Refresh to get the auto-generated ID
        db.refresh(usage_event)

        return UsageRecordingResult(
            success=True,
            event_id=usage_event.id if hasattr(usage_event, "id") else None,
            error=None,
        )
    except Exception as e:
        # Don't fail the LLM call if usage recording fails
        logger.warning(f"Failed to record usage: {e}")
        db.rollback()
        return UsageRecordingResult(
            success=False,
            event_id=None,
            error=str(e),
        )


def record_usage_total_only(
    db: Session,
    *,
    provider: str,
    model: str,
    role: str,
    total_tokens: int,
    run_id: Optional[str] = None,
    phase_id: Optional[str] = None,
) -> UsageRecordingResult:
    """
    Record LLM usage when provider doesn't return exact token splits.

    BUILD-144 P0.4: Records total_tokens explicitly with prompt_tokens=None and
    completion_tokens=None to indicate "total-only" accounting. Dashboard totals
    now use total_tokens field to avoid under-reporting.

    Args:
        db: Database session
        provider: Provider name (openai, anthropic, etc.)
        model: Model name
        role: builder, auditor, or agent:name
        total_tokens: Total tokens used (sum of prompt + completion)
        run_id: Optional run identifier
        phase_id: Optional phase identifier

    Returns:
        UsageRecordingResult indicating success or failure
    """
    try:
        # Record with total_tokens populated and prompt/completion as None
        usage_event = LlmUsageEvent(
            provider=provider,
            model=model,
            role=role,
            total_tokens=total_tokens,
            prompt_tokens=None,  # Explicit None: no guessing
            completion_tokens=None,  # Explicit None: no guessing
            run_id=run_id,
            phase_id=phase_id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(usage_event)
        db.commit()

        # Refresh to get the auto-generated ID
        db.refresh(usage_event)

        logger.info(
            f"[TOKEN-ACCOUNTING] Recorded total-only usage: provider={provider}, model={model}, "
            f"role={role}, total={total_tokens} (no split available)"
        )

        return UsageRecordingResult(
            success=True,
            event_id=usage_event.id if hasattr(usage_event, "id") else None,
            error=None,
        )
    except Exception as e:
        # Don't fail the LLM call if usage recording fails
        logger.warning(f"Failed to record total-only usage: {e}")
        db.rollback()
        return UsageRecordingResult(
            success=False,
            event_id=None,
            error=str(e),
        )


def create_usage_event(
    *,
    provider: str,
    model: str,
    role: str,
    total_tokens: int,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    run_id: Optional[str] = None,
    phase_id: Optional[str] = None,
) -> LlmUsageEvent:
    """
    Create an LlmUsageEvent without persisting to database.

    Useful for batch operations or when caller wants to control persistence.

    Args:
        provider: Provider name (openai, anthropic, etc.)
        model: Model name
        role: builder, auditor, or agent:name
        total_tokens: Total tokens used
        prompt_tokens: Input tokens (None if unknown)
        completion_tokens: Output tokens (None if unknown)
        run_id: Optional run identifier
        phase_id: Optional phase identifier

    Returns:
        LlmUsageEvent ready to be added to a session
    """
    return LlmUsageEvent(
        provider=provider,
        model=model,
        role=role,
        total_tokens=total_tokens,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        run_id=run_id,
        phase_id=phase_id,
        created_at=datetime.now(timezone.utc),
    )


def calculate_token_totals(
    prompt_tokens: Optional[int],
    completion_tokens: Optional[int],
) -> tuple[int, bool]:
    """
    Calculate total tokens and determine if split is available.

    Args:
        prompt_tokens: Input tokens (None if unknown)
        completion_tokens: Output tokens (None if unknown)

    Returns:
        Tuple of (total_tokens, has_split) where has_split indicates
        if both prompt and completion were provided.
    """
    if prompt_tokens is not None and completion_tokens is not None:
        return prompt_tokens + completion_tokens, True
    elif prompt_tokens is not None:
        return prompt_tokens, False
    elif completion_tokens is not None:
        return completion_tokens, False
    else:
        return 0, False
