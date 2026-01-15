"""LLM Usage Recording Module

This module provides usage recording and tracking functions extracted from llm_service.py.
It handles recording LLM usage events in the database and provides utilities for model-to-provider
mapping and usage aggregation.

BUILD-144 P0: Supports both exact token splits and total-only recording modes.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..usage_recorder import LlmUsageEvent

logger = logging.getLogger(__name__)


def record_usage(
    db: Session,
    run_id: Optional[str],
    phase_id: Optional[str],
    model: str,
    usage: Dict,
    category: str,
    complexity: str,
    success: bool,
    client_id: Optional[str] = None,
) -> None:
    """
    Record LLM usage in database with exact token splits.

    This function records full usage details including prompt and completion token counts
    when available from the provider.

    BUILD-144 P0.4: Always records total_tokens = prompt_tokens + completion_tokens.
    IMP-TEL-001: Supports client_id for SaaS cost attribution.

    Args:
        db: Database session
        run_id: Run identifier (optional)
        phase_id: Phase identifier (optional)
        model: Model name
        usage: Usage dict with 'prompt_tokens', 'completion_tokens', and optional 'total_tokens'
        category: Task category (e.g., 'builder', 'auditor', 'doctor')
        complexity: Task complexity (e.g., 'low', 'medium', 'high')
        success: Whether the operation succeeded
        client_id: Client identifier for cost attribution (optional, for SaaS billing)
    """
    try:
        provider = model_to_provider(model)
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")

        # Calculate total_tokens if not provided
        if "total_tokens" in usage:
            total_tokens = usage["total_tokens"]
        elif prompt_tokens is not None and completion_tokens is not None:
            total_tokens = prompt_tokens + completion_tokens
        else:
            # Fallback: should not happen in practice
            total_tokens = 0
            logger.warning(f"[TOKEN-ACCOUNTING] Usage dict missing token counts: {usage}")

        usage_event = LlmUsageEvent(
            provider=provider,
            model=model,
            role=category,
            total_tokens=total_tokens,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            run_id=run_id,
            phase_id=phase_id,
            client_id=client_id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(usage_event)
        db.commit()
    except Exception as e:
        # Don't fail the LLM call if usage recording fails
        logger.error(f"Failed to record usage: {e}")
        db.rollback()


def record_usage_total_only(
    db: Session,
    run_id: Optional[str],
    phase_id: Optional[str],
    model: str,
    total_tokens: int,
    role: Optional[str] = None,
    client_id: Optional[str] = None,
) -> None:
    """
    Record LLM usage when provider doesn't return exact token splits.

    This function is used for total-only accounting mode when the provider API
    doesn't return separate prompt and completion token counts.

    BUILD-144 P0.4: Records total_tokens explicitly with prompt_tokens=None and
    completion_tokens=None to indicate "total-only" accounting. Dashboard totals
    now use total_tokens field to avoid under-reporting.
    IMP-TEL-001: Supports client_id for SaaS cost attribution.

    Args:
        db: Database session
        run_id: Run identifier (optional)
        phase_id: Phase identifier (optional)
        model: Model name
        total_tokens: Total tokens used (sum of prompt + completion)
        role: Role (optional, defaults to "unknown")
        client_id: Client identifier for cost attribution (optional, for SaaS billing)
    """
    try:
        provider = model_to_provider(model)

        # Record with total_tokens populated and prompt/completion as None
        usage_event = LlmUsageEvent(
            provider=provider,
            model=model,
            role=role or "unknown",  # Role unknown in total-only mode if not provided
            total_tokens=total_tokens,
            prompt_tokens=None,  # Explicit None: no guessing
            completion_tokens=None,  # Explicit None: no guessing
            run_id=run_id,
            phase_id=phase_id,
            client_id=client_id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(usage_event)
        db.commit()
        logger.info(
            f"[TOKEN-ACCOUNTING] Recorded total-only usage: provider={provider}, model={model}, "
            f"role={role or 'unknown'}, total={total_tokens} (no split available)"
        )
    except Exception as e:
        # Don't fail the LLM call if usage recording fails
        logger.error(f"Failed to record total-only usage: {e}")
        db.rollback()


def model_to_provider(model: str) -> str:
    """
    Map model name to provider.

    This function determines the provider (openai, anthropic, google, etc.) based on
    the model name prefix.

    Args:
        model: Model name (e.g., 'gpt-4o', 'claude-sonnet-4-5', 'gemini-1.5-pro')

    Returns:
        Provider name (e.g., 'openai', 'anthropic', 'google')
    """
    if model.startswith("gemini-"):
        return "google"
    elif model.startswith("gpt-") or model.startswith("o1-"):
        return "openai"
    elif model.startswith("claude-") or model.startswith("opus-"):
        return "anthropic"
    elif model.startswith("glm-"):
        return "zhipu_glm"
    else:
        # Safe default for unknown models
        return "openai"


def aggregate_usage_by_run(db: Session, run_id: str) -> Dict:
    """
    Aggregate usage totals for a run.

    This function sums up all token usage for a given run across all phases,
    models, and roles.

    Args:
        db: Database session
        run_id: Run identifier

    Returns:
        Dict with aggregated usage statistics including:
        - total_tokens: Total tokens used across all calls
        - total_calls: Number of LLM calls made
        - total_cost_estimate: Estimated cost (placeholder)
    """
    result = (
        db.query(
            func.sum(LlmUsageEvent.total_tokens).label("total_tokens"),
            func.count(LlmUsageEvent.id).label("total_calls"),
        )
        .filter(LlmUsageEvent.run_id == run_id)
        .first()
    )

    total_tokens = result.total_tokens or 0
    total_calls = result.total_calls or 0

    return {
        "run_id": run_id,
        "total_tokens": total_tokens,
        "total_calls": total_calls,
        "total_cost_estimate": 0.0,  # Placeholder for cost calculation
    }


def aggregate_usage_by_model(db: Session, run_id: str) -> Dict:
    """
    Aggregate usage breakdown by model for a run.

    This function groups token usage by model name, showing which models
    were used most frequently and consumed the most tokens.

    Args:
        db: Database session
        run_id: Run identifier

    Returns:
        Dict with model-level breakdown:
        {
            "model_name": {
                "total_tokens": int,
                "call_count": int,
                "provider": str
            },
            ...
        }
    """
    results = (
        db.query(
            LlmUsageEvent.model,
            LlmUsageEvent.provider,
            func.sum(LlmUsageEvent.total_tokens).label("total_tokens"),
            func.count(LlmUsageEvent.id).label("call_count"),
        )
        .filter(LlmUsageEvent.run_id == run_id)
        .group_by(LlmUsageEvent.model, LlmUsageEvent.provider)
        .all()
    )

    breakdown = {}
    for row in results:
        breakdown[row.model] = {
            "total_tokens": row.total_tokens or 0,
            "call_count": row.call_count or 0,
            "provider": row.provider,
        }

    return breakdown


def get_client_usage(
    db: Session,
    client_id: str,
    start_date: datetime,
    end_date: datetime,
) -> Dict:
    """
    Get aggregated usage for a client within a date range.

    IMP-TEL-001: Enables downstream SaaS projects to attribute costs to end users.
    This function aggregates token usage for a specific client across all runs
    within the specified time period.

    Args:
        db: Database session
        client_id: Client identifier to query
        start_date: Start of the date range (inclusive)
        end_date: End of the date range (inclusive)

    Returns:
        Dict with aggregated usage statistics including:
        - client_id: The queried client identifier
        - start_date: Query start date (ISO format)
        - end_date: Query end date (ISO format)
        - total_tokens: Total tokens used by this client
        - total_calls: Number of LLM calls made
        - by_model: Breakdown by model {model_name: {"tokens": int, "calls": int}}
        - by_provider: Breakdown by provider {provider_name: {"tokens": int, "calls": int}}
    """
    # Get totals
    totals = (
        db.query(
            func.sum(LlmUsageEvent.total_tokens).label("total_tokens"),
            func.count(LlmUsageEvent.id).label("total_calls"),
        )
        .filter(
            LlmUsageEvent.client_id == client_id,
            LlmUsageEvent.created_at >= start_date,
            LlmUsageEvent.created_at <= end_date,
        )
        .first()
    )

    total_tokens = totals.total_tokens or 0 if totals else 0
    total_calls = totals.total_calls or 0 if totals else 0

    # Get breakdown by model
    by_model_results = (
        db.query(
            LlmUsageEvent.model,
            func.sum(LlmUsageEvent.total_tokens).label("tokens"),
            func.count(LlmUsageEvent.id).label("calls"),
        )
        .filter(
            LlmUsageEvent.client_id == client_id,
            LlmUsageEvent.created_at >= start_date,
            LlmUsageEvent.created_at <= end_date,
        )
        .group_by(LlmUsageEvent.model)
        .all()
    )

    by_model = {}
    for row in by_model_results:
        by_model[row.model] = {
            "tokens": row.tokens or 0,
            "calls": row.calls or 0,
        }

    # Get breakdown by provider
    by_provider_results = (
        db.query(
            LlmUsageEvent.provider,
            func.sum(LlmUsageEvent.total_tokens).label("tokens"),
            func.count(LlmUsageEvent.id).label("calls"),
        )
        .filter(
            LlmUsageEvent.client_id == client_id,
            LlmUsageEvent.created_at >= start_date,
            LlmUsageEvent.created_at <= end_date,
        )
        .group_by(LlmUsageEvent.provider)
        .all()
    )

    by_provider = {}
    for row in by_provider_results:
        by_provider[row.provider] = {
            "tokens": row.tokens or 0,
            "calls": row.calls or 0,
        }

    return {
        "client_id": client_id,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "total_tokens": total_tokens,
        "total_calls": total_calls,
        "by_model": by_model,
        "by_provider": by_provider,
    }
