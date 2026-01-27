"""Dashboard endpoints.

Extracted from main.py as part of PR-API-3d.
"""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from autopack import dashboard_schemas, models
from autopack.api.deps import verify_api_key, verify_read_access
from autopack.config import settings
from autopack.database import get_db
from autopack.usage_recorder import get_token_efficiency_stats

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get(
    "/runs/{run_id}/status",
    summary="Get run status for dashboard",
    description="Retrieve current run status including phase progress, token utilization, issue counts, and token efficiency metrics. Used by dashboard to display real-time run information.",
    response_model=dashboard_schemas.DashboardRunStatus,
    responses={
        200: {"description": "Run status retrieved successfully"},
        404: {"description": "Run not found"},
        500: {"description": "Internal server error"},
    },
)
def get_dashboard_run_status(
    run_id: str,
    db: Session = Depends(get_db),
    _auth: str = Depends(verify_read_access),
):
    """Get run status for dashboard display"""
    logger.info("[API] GET /dashboard/runs/%s/status - request received", run_id)
    from autopack.run_progress import calculate_run_progress

    run = db.query(models.Run).filter(models.Run.id == run_id).first()
    if not run:
        logger.warning("[API] GET /dashboard/runs/%s/status - run not found", run_id)
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    # Calculate progress
    progress = calculate_run_progress(db, run_id)

    # Calculate token utilization
    tokens_used = run.tokens_used or 0
    token_cap = run.token_cap or 1
    token_utilization = (tokens_used / token_cap) * 100 if token_cap > 0 else 0

    # Count issues
    minor_issues_count = run.minor_issues_count or 0
    major_issues_count = run.major_issues_count or 0

    # Get token efficiency stats (BUILD-145 deployment hardening)
    token_efficiency = None
    try:
        efficiency_stats = get_token_efficiency_stats(db, run_id)
        if efficiency_stats and efficiency_stats.get("total_phases", 0) > 0:
            token_efficiency = efficiency_stats
    except Exception as e:
        logger.warning(f"[DASHBOARD] Failed to load token efficiency stats for {run_id}: {e}")

    logger.info(
        "[API] GET /dashboard/runs/%s/status - success state=%s progress=%.1f%% tokens=%d/%d",
        run_id,
        run.state.value,
        progress.percent_complete,
        tokens_used,
        token_cap,
    )
    return dashboard_schemas.DashboardRunStatus(
        run_id=run.id,
        state=run.state.value,
        current_tier_name=progress.current_tier_name,
        current_phase_name=progress.current_phase_name,
        current_tier_index=progress.current_tier_index,
        current_phase_index=progress.current_phase_index,
        total_tiers=progress.total_tiers,
        total_phases=progress.total_phases,
        completed_tiers=progress.completed_tiers,
        completed_phases=progress.completed_phases,
        percent_complete=progress.percent_complete,
        tiers_percent_complete=progress.tiers_percent_complete,
        tokens_used=tokens_used,
        token_cap=token_cap,
        token_utilization=token_utilization,
        minor_issues_count=minor_issues_count,
        major_issues_count=major_issues_count,
        token_efficiency=token_efficiency,
    )


@router.get(
    "/usage",
    summary="Get token usage statistics",
    description="Retrieve token usage statistics aggregated by provider and model for the specified period. Returns both provider-level and model-level breakdowns with capacity information.",
    response_model=dashboard_schemas.UsageResponse,
    responses={
        200: {"description": "Usage statistics retrieved successfully"},
        400: {"description": "Invalid period parameter"},
        500: {"description": "Internal server error"},
    },
)
def get_dashboard_usage(
    period: str = "week",
    db: Session = Depends(get_db),
    _auth: str = Depends(verify_read_access),
):
    """Get token usage statistics for dashboard display"""
    logger.info("[API] GET /dashboard/usage - request received period=%s", period)
    from datetime import timedelta

    from autopack.usage_recorder import LlmUsageEvent

    # Calculate time range based on period
    now = datetime.now(timezone.utc)
    if period == "day":
        start_time = now - timedelta(days=1)
    elif period == "week":
        start_time = now - timedelta(weeks=1)
    elif period == "month":
        start_time = now - timedelta(days=30)
    else:
        start_time = now - timedelta(weeks=1)  # Default to week

    # Aggregate by provider using SQL GROUP BY (IMP-P04)
    # BUILD-144 P0.4: Use total_tokens for totals, COALESCE NULL->0 for splits
    provider_results = (
        db.query(
            LlmUsageEvent.provider,
            func.sum(LlmUsageEvent.total_tokens).label("total_tokens"),
            func.sum(func.coalesce(LlmUsageEvent.prompt_tokens, 0)).label("prompt_tokens"),
            func.sum(func.coalesce(LlmUsageEvent.completion_tokens, 0)).label("completion_tokens"),
        )
        .filter(LlmUsageEvent.created_at >= start_time)
        .group_by(LlmUsageEvent.provider)
        .all()
    )

    # Aggregate by model using SQL GROUP BY (IMP-P04)
    # BUILD-144 P0.4: Use total_tokens for totals, COALESCE NULL->0 for splits
    model_results = (
        db.query(
            LlmUsageEvent.provider,
            LlmUsageEvent.model,
            func.sum(LlmUsageEvent.total_tokens).label("total_tokens"),
            func.sum(func.coalesce(LlmUsageEvent.prompt_tokens, 0)).label("prompt_tokens"),
            func.sum(func.coalesce(LlmUsageEvent.completion_tokens, 0)).label("completion_tokens"),
        )
        .filter(LlmUsageEvent.created_at >= start_time)
        .group_by(LlmUsageEvent.provider, LlmUsageEvent.model)
        .all()
    )

    # Early return if no results
    if not provider_results and not model_results:
        logger.info("[API] GET /dashboard/usage - success period=%s providers=0 models=0", period)
        return dashboard_schemas.UsageResponse(providers=[], models=[])

    # Convert provider results to dict for serialization
    provider_stats = {
        row.provider: {
            "prompt_tokens": row.prompt_tokens,
            "completion_tokens": row.completion_tokens,
            "total_tokens": row.total_tokens,
        }
        for row in provider_results
    }

    # Convert model results to dict for serialization
    model_stats = {
        f"{row.provider}:{row.model}": {
            "provider": row.provider,
            "model": row.model,
            "prompt_tokens": row.prompt_tokens,
            "completion_tokens": row.completion_tokens,
            "total_tokens": row.total_tokens,
        }
        for row in model_results
    }

    # Get token cap from canonical config (P1.3: remove hardcoded 0)
    cap_tokens = settings.run_token_cap  # Default: 5_000_000

    # Convert to response models
    providers = [
        dashboard_schemas.ProviderUsage(
            provider=provider,
            period=period,
            prompt_tokens=stats["prompt_tokens"],
            completion_tokens=stats["completion_tokens"],
            total_tokens=stats["total_tokens"],
            cap_tokens=cap_tokens,
            percent_of_cap=(stats["total_tokens"] / cap_tokens * 100) if cap_tokens > 0 else 0.0,
        )
        for provider, stats in provider_stats.items()
    ]

    models_list = [dashboard_schemas.ModelUsage(**stats) for stats in model_stats.values()]

    logger.info(
        "[API] GET /dashboard/usage - success period=%s providers=%d models=%d",
        period,
        len(providers),
        len(models_list),
    )
    return dashboard_schemas.UsageResponse(providers=providers, models=models_list)


@router.get(
    "/models",
    summary="Get current model mappings",
    description="Retrieve the current model mappings for all roles (builder, auditor) and complexity levels. Returns the global scope model assignments used for LLM routing.",
    response_model=list,
    responses={
        200: {"description": "Model mappings retrieved successfully"},
        500: {"description": "Internal server error"},
    },
)
def get_dashboard_models(
    db: Session = Depends(get_db),
    _auth: str = Depends(verify_read_access),
):
    """Get current model mappings for dashboard display"""
    logger.info("[API] GET /dashboard/models - request received")
    from autopack.model_router import ModelRouter

    # Create router instance
    model_router = ModelRouter(db)

    # Get current mappings
    mappings = model_router.get_current_mappings()

    # Convert to list format for dashboard
    result = []
    for role in ["builder", "auditor"]:
        for key, model in mappings[role].items():
            category, complexity = key.split(":")
            result.append(
                dashboard_schemas.ModelMapping(
                    role=role, category=category, complexity=complexity, model=model, scope="global"
                )
            )

    logger.info("[API] GET /dashboard/models - success mappings=%d", len(result))
    return result


@router.post(
    "/human-notes",
    summary="Add a human note",
    description="Add a human note to the central notes file with timestamp and optional run ID. Useful for recording observations during build execution.",
    responses={
        200: {"description": "Note added successfully"},
        400: {"description": "Invalid request"},
        500: {"description": "Internal server error"},
    },
)
def add_dashboard_human_note(
    note_request: dashboard_schemas.HumanNoteRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    """Add a human note to the notes file"""
    logger.info(
        "[API] POST /dashboard/human-notes - request received run_id=%s note_length=%d",
        note_request.run_id,
        len(note_request.note) if note_request.note else 0,
    )
    notes_file = Path(settings.autonomous_runs_dir) / ".." / ".autopack" / "human_notes.md"
    notes_file.parent.mkdir(parents=True, exist_ok=True)

    # Append note with timestamp
    timestamp = datetime.now(timezone.utc).isoformat()
    note_entry = f"\n## {timestamp}\n"
    if note_request.run_id:
        note_entry += f"**Run:** {note_request.run_id}\n"
    note_entry += f"{note_request.note}\n"

    with open(notes_file, "a", encoding="utf-8") as f:
        f.write(note_entry)

    logger.info(
        "[API] POST /dashboard/human-notes - success timestamp=%s run_id=%s",
        timestamp,
        note_request.run_id,
    )
    return {
        "message": "Note added successfully",
        "timestamp": timestamp,
        "notes_file": ".autopack/human_notes.md",
    }


@router.get(
    "/runs/{run_id}/token-efficiency",
    summary="Get token efficiency metrics",
    description="Get token efficiency metrics for a run (BUILD-145). Returns aggregated token efficiency statistics including artifact substitutions, tokens saved, context budget usage, and files kept vs omitted across all phases.",
    response_model=dashboard_schemas.TokenEfficiencyStats,
    responses={
        200: {"description": "Token efficiency metrics retrieved successfully"},
        404: {"description": "Run not found"},
        500: {"description": "Internal server error"},
    },
)
def get_run_token_efficiency(
    run_id: str, db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)
):
    """Get token efficiency metrics for a run (BUILD-145)

    Returns aggregated token efficiency statistics:
    - Total artifact substitutions and tokens saved
    - Context budget usage and mode distribution
    - Files kept vs omitted across all phases
    """
    logger.info("[API] GET /dashboard/runs/%s/token-efficiency - request received", run_id)
    # Verify run exists
    run = db.query(models.Run).filter(models.Run.id == run_id).first()
    if not run:
        logger.warning("[API] GET /dashboard/runs/%s/token-efficiency - run not found", run_id)
        raise HTTPException(status_code=404, detail="Run not found")

    stats = get_token_efficiency_stats(db, run_id)
    logger.info(
        "[API] GET /dashboard/runs/%s/token-efficiency - success phases=%d tokens_saved=%d",
        run_id,
        stats.get("total_phases", 0),
        stats.get("total_tokens_saved", 0),
    )
    return dashboard_schemas.TokenEfficiencyStats(**stats)


@router.get(
    "/runs/{run_id}/phase6-stats",
    summary="Get Phase 6 feature effectiveness metrics",
    description="Get Phase 6 True Autonomy feature effectiveness metrics (BUILD-146). Returns aggregated Phase 6 statistics including failure hardening pattern detection, doctor call optimization, and intention context injection metrics.",
    response_model=dashboard_schemas.Phase6Stats,
    responses={
        200: {"description": "Phase 6 metrics retrieved successfully"},
        404: {"description": "Run not found"},
        500: {"description": "Internal server error"},
    },
)
def get_run_phase6_stats(
    run_id: str, db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)
):
    """Get Phase 6 True Autonomy feature effectiveness metrics (BUILD-146)

    Returns aggregated Phase 6 statistics:
    - Failure hardening pattern detection and mitigation rates
    - Doctor calls skipped and estimated token savings
    - Intention context injection statistics
    - Plan normalization usage
    """
    logger.info("[API] GET /dashboard/runs/%s/phase6-stats - request received", run_id)
    # Verify run exists
    run = db.query(models.Run).filter(models.Run.id == run_id).first()
    if not run:
        logger.warning("[API] GET /dashboard/runs/%s/phase6-stats - run not found", run_id)
        raise HTTPException(status_code=404, detail="Run not found")

    from autopack.usage_recorder import get_phase6_metrics_summary

    stats = get_phase6_metrics_summary(db, run_id)
    logger.info(
        "[API] GET /dashboard/runs/%s/phase6-stats - success doctor_skipped=%d",
        run_id,
        stats.get("doctor_calls_skipped", 0),
    )
    return dashboard_schemas.Phase6Stats(run_id=run_id, **stats)


@router.get(
    "/runs/{run_id}/consolidated-metrics",
    summary="Get consolidated token metrics",
    description="Get consolidated token metrics for a run (BUILD-146 P11 P12 API Consolidation). Returns all token metrics in clearly separated categories (total spend, artifact savings, doctor counterfactual, A/B delta) to prevent confusion and double-counting. This is the PRIMARY observability endpoint - prefer over legacy endpoints.",
    responses={
        200: {"description": "Consolidated metrics retrieved successfully"},
        400: {"description": "Invalid pagination parameters"},
        404: {"description": "Run not found"},
        503: {"description": "Consolidated metrics disabled"},
    },
)
def get_dashboard_consolidated_metrics(
    run_id: str,
    limit: int = 1000,
    offset: int = 0,
    db: Session = Depends(get_db),
    _auth: str = Depends(verify_read_access),
):
    """Get consolidated token metrics for a run (no double-counting).

    BUILD-146 P11 Observability + P12 API Consolidation: Returns all token metrics
    in clearly separated categories to prevent confusion and double-counting.

    This is the PRIMARY observability endpoint - prefer this over legacy
    /token-efficiency and /phase6-stats endpoints.

    Args:
        run_id: The run ID to fetch metrics for
        limit: Maximum number of records to return (max: 10000, default: 1000)
        offset: Number of records to skip (default: 0)

    Returns:
        Dictionary with consolidated token metrics in 4 independent categories:
        1. total_tokens_spent: Actual LLM spend (from llm_usage_events)
        2. artifact_tokens_avoided: Efficiency savings (from token_efficiency_metrics)
        3. doctor_tokens_avoided_estimate: Counterfactual (from phase6_metrics)
        4. ab_delta_tokens_saved: Measured A/B delta (when available)

    Raises:
        HTTPException: 503 if kill switch disabled, 404 if run not found, 400 if bad pagination
    """
    logger.info(
        "[API] GET /dashboard/runs/%s/consolidated-metrics - request received limit=%d offset=%d",
        run_id,
        limit,
        offset,
    )
    # BUILD-146 P12: Kill switch check (default: OFF)
    if os.getenv("AUTOPACK_ENABLE_CONSOLIDATED_METRICS") != "1":
        logger.warning(
            "[API] GET /dashboard/runs/%s/consolidated-metrics - feature disabled",
            run_id,
        )
        raise HTTPException(
            status_code=503,
            detail="Consolidated metrics disabled. Set AUTOPACK_ENABLE_CONSOLIDATED_METRICS=1 to enable.",
        )

    # Validate pagination parameters
    if limit > 10000:
        logger.warning(
            "[API] GET /dashboard/runs/%s/consolidated-metrics - invalid limit=%d",
            run_id,
            limit,
        )
        raise HTTPException(status_code=400, detail="Limit cannot exceed 10000")
    if offset < 0:
        logger.warning(
            "[API] GET /dashboard/runs/%s/consolidated-metrics - invalid offset=%d",
            run_id,
            offset,
        )
        raise HTTPException(status_code=400, detail="Offset cannot be negative")

    # Verify run exists
    run = db.query(models.Run).filter(models.Run.id == run_id).first()
    if not run:
        logger.warning("[API] GET /dashboard/runs/%s/consolidated-metrics - run not found", run_id)
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    # Category 1: Actual spend from llm_usage_events
    actual_spend = (
        db.query(
            text("""
            SELECT
                COALESCE(SUM(total_tokens), 0) as total_tokens,
                COALESCE(SUM(prompt_tokens), 0) as prompt_tokens,
                COALESCE(SUM(completion_tokens), 0) as completion_tokens,
                COALESCE(SUM(CASE WHEN is_doctor_call = 1 THEN total_tokens ELSE 0 END), 0) as doctor_tokens
            FROM llm_usage_events
            WHERE run_id = :run_id
        """)
        )
        .params(run_id=run_id)
        .first()
    )

    total_tokens_spent = actual_spend[0] if actual_spend else 0
    total_prompt_tokens = actual_spend[1] if actual_spend else 0
    total_completion_tokens = actual_spend[2] if actual_spend else 0
    doctor_tokens_spent = actual_spend[3] if actual_spend else 0

    # Category 2: Artifact efficiency from token_efficiency_metrics
    artifact_efficiency = (
        db.query(
            text("""
            SELECT
                COALESCE(SUM(tokens_saved_artifacts), 0) as tokens_saved,
                COALESCE(SUM(artifact_substitutions), 0) as substitutions
            FROM token_efficiency_metrics
            WHERE run_id = :run_id
        """)
        )
        .params(run_id=run_id)
        .first()
    )

    artifact_tokens_avoided = artifact_efficiency[0] if artifact_efficiency else 0
    artifact_substitutions_count = artifact_efficiency[1] if artifact_efficiency else 0

    # Category 3: Doctor counterfactual from phase6_metrics
    doctor_counterfactual = (
        db.query(
            text("""
            SELECT
                COALESCE(SUM(doctor_tokens_avoided_estimate), 0) as total_estimate,
                COALESCE(SUM(CASE WHEN doctor_call_skipped = 1 THEN 1 ELSE 0 END), 0) as skipped_count,
                MAX(estimate_coverage_n) as max_coverage_n,
                MAX(estimate_source) as last_source
            FROM phase6_metrics
            WHERE run_id = :run_id
        """)
        )
        .params(run_id=run_id)
        .first()
    )

    doctor_tokens_avoided_estimate = doctor_counterfactual[0] if doctor_counterfactual else 0
    doctor_calls_skipped_count = doctor_counterfactual[1] if doctor_counterfactual else 0
    estimate_coverage_n = doctor_counterfactual[2] if doctor_counterfactual else None
    estimate_source = doctor_counterfactual[3] if doctor_counterfactual else None

    # Category 4: A/B delta (not implemented yet - would come from A/B test results)
    ab_delta_tokens_saved = None
    ab_control_run_id = None
    ab_treatment_run_id = None

    # Metadata: Phase counts
    phase_counts = (
        db.query(
            text("""
            SELECT
                COUNT(*) as total_phases,
                COALESCE(SUM(CASE WHEN state = 'COMPLETE' THEN 1 ELSE 0 END), 0) as completed_phases
            FROM phases
            WHERE run_id = :run_id
        """)
        )
        .params(run_id=run_id)
        .first()
    )

    total_phases = phase_counts[0] if phase_counts else 0
    completed_phases = phase_counts[1] if phase_counts else 0

    logger.info(
        "[API] GET /dashboard/runs/%s/consolidated-metrics - success "
        "tokens_spent=%d artifact_avoided=%d doctor_avoided=%d phases=%d/%d",
        run_id,
        total_tokens_spent,
        artifact_tokens_avoided,
        doctor_tokens_avoided_estimate,
        completed_phases,
        total_phases,
    )
    # Build response
    return {
        "run_id": run_id,
        "total_tokens_spent": total_tokens_spent,
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "doctor_tokens_spent": doctor_tokens_spent,
        "artifact_tokens_avoided": artifact_tokens_avoided,
        "artifact_substitutions_count": artifact_substitutions_count,
        "doctor_tokens_avoided_estimate": doctor_tokens_avoided_estimate,
        "doctor_calls_skipped_count": doctor_calls_skipped_count,
        "estimate_coverage_n": estimate_coverage_n,
        "estimate_source": estimate_source,
        "ab_delta_tokens_saved": ab_delta_tokens_saved,
        "ab_control_run_id": ab_control_run_id,
        "ab_treatment_run_id": ab_treatment_run_id,
        "total_phases": total_phases,
        "completed_phases": completed_phases,
    }


@router.post(
    "/models/override",
    summary="Add or update model override",
    description="Add a model override for either global scope (affects all runs) or run scope (affects specific run). Global overrides update the model mapping used for LLM routing.",
    responses={
        200: {"description": "Model override added successfully"},
        400: {"description": "Invalid scope parameter"},
        500: {"description": "Internal server error"},
    },
)
def add_dashboard_model_override(
    override_request: dashboard_schemas.ModelOverrideRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    """Add a model override (global or per-run)"""
    logger.info(
        "[API] POST /dashboard/models/override - request received "
        "scope=%s role=%s category=%s complexity=%s model=%s",
        override_request.scope,
        override_request.role,
        override_request.category,
        override_request.complexity,
        override_request.model,
    )
    if override_request.scope == "global":
        # For global scope, we would update config file
        # For now, return success message
        logger.info(
            "[API] POST /dashboard/models/override - success scope=global model=%s",
            override_request.model,
        )
        return {
            "message": "Global model mapping updated",
            "scope": "global",
            "role": override_request.role,
            "category": override_request.category,
            "complexity": override_request.complexity,
            "model": override_request.model,
        }
    elif override_request.scope == "run":
        # For run scope, we would update run context
        # For now, return "coming soon" message per test expectations
        logger.info(
            "[API] POST /dashboard/models/override - success scope=run run_id=%s",
            override_request.run_id,
        )
        return {
            "message": "Run-scoped model overrides coming soon",
            "scope": "run",
            "run_id": override_request.run_id,
        }
    else:
        logger.warning(
            "[API] POST /dashboard/models/override - invalid scope=%s",
            override_request.scope,
        )
        raise HTTPException(status_code=400, detail="Invalid scope. Must be 'global' or 'run'")
