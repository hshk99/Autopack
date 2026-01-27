"""Runtime statistics aggregation from telemetry.

This module aggregates llm_usage_events into model_runtime_stats for a rolling window,
computing cost estimates using the pricing table.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

import numpy as np
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from ..usage_recorder import LlmUsageEvent
from .models import ModelPricing, ModelRuntimeStats


def compute_runtime_stats(
    session: Session,
    window_days: int = 30,
    window_start: Optional[datetime] = None,
    window_end: Optional[datetime] = None,
) -> int:
    """Compute runtime statistics from llm_usage_events for a rolling window.

    Args:
        session: Database session.
        window_days: Number of days to look back (default: 30).
        window_start: Explicit window start (overrides window_days).
        window_end: Explicit window end (defaults to now).

    Returns:
        Number of runtime stats records created/updated.
    """
    if window_end is None:
        window_end = datetime.now(timezone.utc)

    if window_start is None:
        window_start = window_end - timedelta(days=window_days)

    # Query llm_usage_events grouped by provider, model, role
    usage_groups = (
        session.query(
            LlmUsageEvent.provider,
            LlmUsageEvent.model,
            LlmUsageEvent.role,
            func.count(LlmUsageEvent.id).label("calls"),
            func.sum(LlmUsageEvent.total_tokens).label("total_tokens"),
            func.sum(LlmUsageEvent.prompt_tokens).label("prompt_tokens"),
            func.sum(LlmUsageEvent.completion_tokens).label("completion_tokens"),
        )
        .filter(
            and_(
                LlmUsageEvent.created_at >= window_start,
                LlmUsageEvent.created_at < window_end,
            )
        )
        .group_by(LlmUsageEvent.provider, LlmUsageEvent.model, LlmUsageEvent.role)
        .all()
    )

    stats_count = 0

    for group in usage_groups:
        provider = group.provider
        model = group.model
        role = group.role
        calls = group.calls
        total_tokens = group.total_tokens or 0
        prompt_tokens = group.prompt_tokens
        completion_tokens = group.completion_tokens

        # Compute cost estimate using pricing table
        est_cost_usd = compute_cost_estimate(
            session, model, prompt_tokens, completion_tokens, window_end
        )

        # Compute percentiles for tokens
        p50_tokens, p90_tokens = compute_token_percentiles(
            session, provider, model, role, window_start, window_end
        )

        # Check if stats record already exists
        existing = (
            session.query(ModelRuntimeStats)
            .filter_by(
                window_start=window_start,
                window_end=window_end,
                provider=provider,
                model=model,
                role=role,
            )
            .first()
        )

        if existing:
            # Update existing record
            existing.calls = calls
            existing.total_tokens = total_tokens
            existing.prompt_tokens = prompt_tokens
            existing.completion_tokens = completion_tokens
            existing.est_cost_usd = est_cost_usd
            existing.p50_tokens = p50_tokens
            existing.p90_tokens = p90_tokens
        else:
            # Create new record
            stats_record = ModelRuntimeStats(
                window_start=window_start,
                window_end=window_end,
                provider=provider,
                model=model,
                role=role,
                calls=calls,
                total_tokens=total_tokens,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                est_cost_usd=est_cost_usd,
                p50_tokens=p50_tokens,
                p90_tokens=p90_tokens,
            )
            session.add(stats_record)
            stats_count += 1

    session.commit()
    return stats_count


def compute_cost_estimate(
    session: Session,
    model: str,
    prompt_tokens: Optional[int],
    completion_tokens: Optional[int],
    as_of: datetime,
) -> Optional[Decimal]:
    """Compute cost estimate for a model using pricing table.

    Args:
        session: Database session.
        model: Model identifier.
        prompt_tokens: Number of prompt tokens (nullable).
        completion_tokens: Number of completion tokens (nullable).
        as_of: Date for pricing lookup.

    Returns:
        Estimated cost in USD, or None if pricing not available.
    """
    if prompt_tokens is None or completion_tokens is None:
        return None

    # Get most recent pricing record for model as of date
    pricing = (
        session.query(ModelPricing)
        .filter(
            and_(
                ModelPricing.model_id == model,
                ModelPricing.effective_at <= as_of,
            )
        )
        .order_by(ModelPricing.effective_at.desc())
        .first()
    )

    if not pricing:
        return None

    # Compute cost: (prompt_tokens * input_per_1k / 1000) + (completion_tokens * output_per_1k / 1000)
    input_cost = Decimal(prompt_tokens) * pricing.input_per_1k / Decimal(1000)
    output_cost = Decimal(completion_tokens) * pricing.output_per_1k / Decimal(1000)
    return input_cost + output_cost


def compute_token_percentiles(
    session: Session,
    provider: str,
    model: str,
    role: str,
    window_start: datetime,
    window_end: datetime,
) -> tuple[Optional[int], Optional[int]]:
    """Compute p50 and p90 token percentiles for a provider/model/role.

    Args:
        session: Database session.
        provider: Provider name.
        model: Model identifier.
        role: Role (builder, auditor, etc.).
        window_start: Window start time.
        window_end: Window end time.

    Returns:
        Tuple of (p50_tokens, p90_tokens).
    """
    # Query all total_tokens for the group
    tokens = (
        session.query(LlmUsageEvent.total_tokens)
        .filter(
            and_(
                LlmUsageEvent.provider == provider,
                LlmUsageEvent.model == model,
                LlmUsageEvent.role == role,
                LlmUsageEvent.created_at >= window_start,
                LlmUsageEvent.created_at < window_end,
                LlmUsageEvent.total_tokens.isnot(None),
            )
        )
        .all()
    )

    if not tokens:
        return None, None

    token_values = [t[0] for t in tokens]

    p50 = int(np.percentile(token_values, 50))
    p90 = int(np.percentile(token_values, 90))

    return p50, p90


def get_runtime_stats_summary(
    session: Session,
    model: Optional[str] = None,
    role: Optional[str] = None,
    limit: int = 10,
) -> list[Dict[str, Any]]:
    """Get summary of runtime stats for reporting.

    Args:
        session: Database session.
        model: Filter by model (optional).
        role: Filter by role (optional).
        limit: Maximum number of records to return.

    Returns:
        List of runtime stats dictionaries.
    """
    query = session.query(ModelRuntimeStats).order_by(ModelRuntimeStats.window_end.desc())

    if model:
        query = query.filter(ModelRuntimeStats.model == model)
    if role:
        query = query.filter(ModelRuntimeStats.role == role)

    stats = query.limit(limit).all()

    return [
        {
            "window_start": stat.window_start.isoformat(),
            "window_end": stat.window_end.isoformat(),
            "provider": stat.provider,
            "model": stat.model,
            "role": stat.role,
            "calls": stat.calls,
            "total_tokens": stat.total_tokens,
            "est_cost_usd": float(stat.est_cost_usd) if stat.est_cost_usd else None,
            "p50_tokens": stat.p50_tokens,
            "p90_tokens": stat.p90_tokens,
        }
        for stat in stats
    ]
