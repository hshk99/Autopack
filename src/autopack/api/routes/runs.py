"""Runs router - run management endpoints.

Extracted from main.py as part of PR-API-3i.
Provides endpoints for:
- Starting new runs (POST /runs/start)
- Getting run details (GET /runs/{run_id})
- Listing runs (GET /runs)
- Getting run progress (GET /runs/{run_id}/progress)
- Getting run issues/errors (GET /runs/{run_id}/issues/index, /errors, /errors/summary)
- Getting project backlog (GET /project/issues/backlog)
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, joinedload

from autopack import models, schemas
from autopack.api.deps import limiter, verify_api_key, verify_read_access
from autopack.database import get_db
from autopack.file_layout import RunFileLayout
from autopack.issue_tracker import IssueTracker
from autopack.strategy_engine import StrategyEngine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["runs"])


@router.post(
    "/runs/start",
    summary="Start a new autonomous build run",
    description="Start a new autonomous build run with specified tiers and phases. Returns run configuration with tier and phase details. Rate limited to 10 runs per minute.",
    response_model=schemas.RunResponse,
    status_code=201,
    dependencies=[Depends(verify_api_key)],
    responses={
        201: {"description": "Run created successfully"},
        400: {"description": "Invalid request or run already exists"},
        429: {"description": "Rate limit exceeded (10 runs/minute)"},
        503: {"description": "Database unavailable"},
    },
)
@limiter.limit("10/minute")  # Max 10 runs per minute per IP
def start_run(
    request_data: schemas.RunStartRequest, request: Request, db: Session = Depends(get_db)
):
    """Start a new autonomous build run with tiers and phases."""
    # Check if run already exists
    try:
        existing_run = db.query(models.Run).filter(models.Run.id == request_data.run.run_id).first()
    except OperationalError as e:
        logger.error(f"[API] DB OperationalError during run start: {e}")
        db.rollback()
        raise HTTPException(status_code=503, detail="Database unavailable, please retry") from e
    if existing_run:
        raise HTTPException(status_code=400, detail=f"Run {request_data.run.run_id} already exists")

    # Create run
    run = models.Run(
        id=request_data.run.run_id,
        state=models.RunState.RUN_CREATED,
        safety_profile=request_data.run.safety_profile,
        run_scope=request_data.run.run_scope,
        token_cap=request_data.run.token_cap or 5_000_000,
        max_phases=request_data.run.max_phases or 25,
        max_duration_minutes=request_data.run.max_duration_minutes or 120,
        max_minor_issues_total=None,
        started_at=datetime.now(timezone.utc),
    )

    # Compute max_minor_issues_total
    if request_data.phases:
        run.max_minor_issues_total = len(request_data.phases) * 3

    db.add(run)
    db.flush()

    # Create tiers
    tier_map = {}
    for tier_create in request_data.tiers:
        tier = models.Tier(
            tier_id=tier_create.tier_id,
            run_id=run.id,
            tier_index=tier_create.tier_index,
            name=tier_create.name,
            description=tier_create.description,
            state=models.TierState.PENDING,
        )
        db.add(tier)
        db.flush()
        tier_map[tier_create.tier_id] = tier

    # Create phases
    for phase_create in request_data.phases:
        if phase_create.tier_id not in tier_map:
            raise HTTPException(
                status_code=400,
                detail=f"Phase {phase_create.phase_id} references unknown tier {phase_create.tier_id}",
            )

        phase = models.Phase(
            phase_id=phase_create.phase_id,
            run_id=run.id,
            tier_id=tier_map[phase_create.tier_id].id,
            phase_index=phase_create.phase_index,
            name=phase_create.name,
            description=phase_create.description,
            task_category=phase_create.task_category,
            complexity=phase_create.complexity,
            builder_mode=phase_create.builder_mode,
            scope=phase_create.scope,
            state=models.PhaseState.QUEUED,
        )
        db.add(phase)

    db.commit()
    db.refresh(run)

    # Compile strategy
    strategy_engine = StrategyEngine(project_id="Autopack")
    strategy_engine.compile_strategy(
        run_id=run.id,
        phases=[
            {
                "phase_id": p.phase_id,
                "task_category": p.task_category,
                "complexity": p.complexity,
            }
            for p in run.phases
        ],
        tiers=[{"tier_id": t.tier_id} for t in run.tiers],
        safety_profile_override=run.safety_profile,
    )

    # Initialize file layout
    file_layout = RunFileLayout(run.id)
    file_layout.ensure_directories()
    file_layout.write_run_summary(
        run_id=run.id,
        state=run.state.value,
        safety_profile=run.safety_profile,
        run_scope=run.run_scope,
        created_at=run.created_at.isoformat(),
        tier_count=len(request_data.tiers),
        phase_count=len(request_data.phases),
    )

    # Write tier summaries
    for tier in run.tiers:
        phase_count = len([p for p in run.phases if p.tier_id == tier.id])
        file_layout.write_tier_summary(
            tier_index=tier.tier_index,
            tier_id=tier.tier_id,
            tier_name=tier.name,
            state=tier.state.value,
            phase_count=phase_count,
        )

    # Write phase summaries
    for phase in run.phases:
        file_layout.write_phase_summary(
            phase_index=phase.phase_index,
            phase_id=phase.phase_id,
            phase_name=phase.name,
            state=phase.state.value,
            task_category=phase.task_category,
            complexity=phase.complexity,
        )

    # Eagerly load relationships
    run_with_relationships = (
        db.query(models.Run)
        .filter(models.Run.id == run.id)
        .options(
            joinedload(models.Run.tiers).joinedload(models.Tier.phases),
            joinedload(models.Run.phases),
        )
        .first()
    )

    return run_with_relationships


@router.get(
    "/runs/{run_id}",
    summary="Get run details",
    description="Retrieve detailed information about a specific run including all tiers, phases, current status, and metadata. Includes phase states and progress information.",
    response_model=schemas.RunResponse,
    responses={
        200: {"description": "Run details retrieved successfully"},
        404: {"description": "Run not found"},
        503: {"description": "Database unavailable or misconfigured"},
    },
)
def get_run(
    run_id: str,
    db: Session = Depends(get_db),
    _auth: str = Depends(verify_read_access),
):
    """Get run details including all tiers and phases."""
    try:
        run = db.query(models.Run).filter(models.Run.id == run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        return run
    except OperationalError as e:
        # Avoid opaque 500s when the API is pointed at the wrong DB (common during local validation).
        logger.error(f"[RUNS] Database error while fetching run {run_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail=(
                "Database unavailable or misconfigured for Autopack API. "
                "Ensure the API server and executor use the same DATABASE_URL."
            ),
        )


@router.get(
    "/runs/{run_id}/issues/index",
    summary="Get run-level issue index",
    description="Retrieve the run-level issue index containing all issues detected during the run execution. Returns categorized issues with severity levels and evidence references.",
    responses={
        200: {"description": "Issue index retrieved successfully"},
        404: {"description": "Run not found"},
        500: {"description": "Internal server error"},
    },
)
def get_run_issue_index(run_id: str, _auth: str = Depends(verify_read_access)):
    """Get run-level issue index."""
    tracker = IssueTracker(run_id=run_id)
    index = tracker.load_run_issue_index()
    return index.model_dump()


@router.get(
    "/project/issues/backlog",
    summary="Get project-level issue backlog",
    description="Retrieve the project-level issue backlog containing all issues across all runs. Returns prioritized issues for project-wide tracking and analysis.",
    responses={
        200: {"description": "Project backlog retrieved successfully"},
        500: {"description": "Internal server error"},
    },
)
def get_project_backlog(_auth: str = Depends(verify_read_access)):
    """Get project-level issue backlog."""
    tracker = IssueTracker(run_id="dummy")
    backlog = tracker.load_project_backlog()
    return backlog.model_dump()


@router.get(
    "/runs/{run_id}/errors",
    summary="Get all error reports for a run",
    description="Retrieve all error reports collected during a specific run execution. Returns detailed error information including error types, messages, and context.",
    responses={
        200: {"description": "Error reports retrieved successfully"},
        404: {"description": "Run not found"},
        500: {"description": "Internal server error"},
    },
)
def get_run_errors(run_id: str, _auth: str = Depends(verify_read_access)):
    """Get all error reports for a run."""
    from autopack.error_reporter import get_error_reporter

    reporter = get_error_reporter()
    errors = reporter.get_run_errors(run_id)
    return {"run_id": run_id, "error_count": len(errors), "errors": errors}


@router.get(
    "/runs/{run_id}/errors/summary",
    summary="Get error summary for a run",
    description="Retrieve a summarized view of all errors for a run with aggregated counts and categorization. Useful for quick error overview without detailed error lists.",
    responses={
        200: {"description": "Error summary retrieved successfully"},
        404: {"description": "Run not found"},
        500: {"description": "Internal server error"},
    },
)
def get_run_error_summary(run_id: str, _auth: str = Depends(verify_read_access)):
    """Get error summary for a run."""
    from autopack.error_reporter import get_error_reporter

    reporter = get_error_reporter()
    summary = reporter.generate_run_error_summary(run_id)
    return {"run_id": run_id, "summary": summary}


@router.get(
    "/runs",
    summary="List all runs with pagination",
    description="List all runs with pagination support (GAP-8.10.2 Runs Inbox). Returns summary information for each run suitable for inbox display including current phase and token usage.",
    responses={
        200: {"description": "Runs list retrieved successfully"},
        400: {"description": "Invalid pagination parameters"},
        500: {"description": "Internal server error"},
    },
)
async def list_runs(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    _auth: str = Depends(verify_read_access),
) -> Dict[str, Any]:
    """List all runs with pagination (GAP-8.10.2 Runs Inbox).

    Returns summary information for each run suitable for inbox display.
    Auth: Required in production; dev opt-in via AUTOPACK_PUBLIC_READ=1.

    P3.2 Optimization: Uses joinedload to fetch runs and phases in a single
    query, avoiding the N+1 query problem where each run required a separate
    phases query.
    """
    # Clamp limit to reasonable bounds
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    # Get total count
    total = db.query(models.Run).count()

    # P3.2: Use joinedload to eagerly load phases in a single query
    # This avoids N+1 queries where each run would require a separate phases query
    runs = (
        db.query(models.Run)
        .options(joinedload(models.Run.phases))
        .order_by(models.Run.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    # Build summary response using prefetched phases
    run_summaries = []
    for run in runs:
        # Phases are already loaded via joinedload - no extra query needed
        phases = run.phases
        phases_total = len(phases)
        phases_completed = sum(1 for p in phases if p.state == models.PhaseState.COMPLETE)

        # Get current phase name (first non-complete phase)
        # Sort phases by phase_index to ensure consistent ordering
        sorted_phases = sorted(phases, key=lambda p: p.phase_index)
        current_phase = next(
            (
                p
                for p in sorted_phases
                if p.state not in (models.PhaseState.COMPLETE, models.PhaseState.SKIPPED)
            ),
            None,
        )

        run_summaries.append(
            {
                "id": run.id,
                "state": run.state.value,
                "created_at": run.created_at.isoformat() if run.created_at else None,
                "tokens_used": run.tokens_used or 0,
                "token_cap": run.token_cap,
                "phases_total": phases_total,
                "phases_completed": phases_completed,
                "current_phase_name": current_phase.name if current_phase else None,
            }
        )

    return {
        "runs": run_summaries,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get(
    "/runs/{run_id}/progress",
    summary="Get detailed run progress",
    description="Get detailed progress for a run (GAP-8.10.4 Progress View). Returns phase-by-phase progress with timing, token information, and status breakdown.",
    responses={
        200: {"description": "Run progress retrieved successfully"},
        404: {"description": "Run not found"},
        500: {"description": "Internal server error"},
    },
)
async def get_run_progress(
    run_id: str,
    db: Session = Depends(get_db),
    _auth: str = Depends(verify_read_access),
) -> Dict[str, Any]:
    """Get detailed progress for a run (GAP-8.10.4 Progress View).

    Returns phase-by-phase progress with timing and token information.
    Auth: Required in production; dev opt-in via AUTOPACK_PUBLIC_READ=1.
    """
    run = db.query(models.Run).filter(models.Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    # Get all phases for this run
    phases = (
        db.query(models.Phase)
        .filter(models.Phase.run_id == run_id)
        .order_by(models.Phase.phase_index)
        .all()
    )

    # Count phase states
    phases_total = len(phases)
    phases_completed = sum(1 for p in phases if p.state == models.PhaseState.COMPLETE)
    phases_in_progress = sum(1 for p in phases if p.state == models.PhaseState.EXECUTING)
    phases_pending = sum(1 for p in phases if p.state == models.PhaseState.QUEUED)

    # Calculate elapsed time
    elapsed_seconds = None
    if run.started_at:
        end_time = run.completed_at if run.completed_at else datetime.now(timezone.utc)
        started_at = run.started_at
        # Normalize timezones
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)
        elapsed_seconds = int((end_time - started_at).total_seconds())

    # Build phase details
    phase_details = []
    for p in phases:
        phase_details.append(
            {
                "phase_id": p.phase_id,
                "name": p.name,
                "state": p.state.value,
                "phase_index": p.phase_index,
                "tokens_used": p.tokens_used,
                "builder_attempts": p.builder_attempts,
            }
        )

    return {
        "run_id": run_id,
        "state": run.state.value,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "elapsed_seconds": elapsed_seconds,
        "tokens_used": run.tokens_used or 0,
        "token_cap": run.token_cap,
        "phases_total": phases_total,
        "phases_completed": phases_completed,
        "phases_in_progress": phases_in_progress,
        "phases_pending": phases_pending,
        "phases": phase_details,
    }
